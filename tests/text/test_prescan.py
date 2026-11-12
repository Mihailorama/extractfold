from __future__ import annotations

import json
from typing import Any

import pytest

from extractfold.chunking import TextChunk
from extractfold.engines.base import ExtractionEngine, ExtractionResult, load_schema
from extractfold.prescan import PreScan, prescan
from extractfold.text import extract_rows_chunked

_ANSWER = {
    "detected_columns": ["name", "qty"],
    "column_types": {"name": "text", "qty": "integer"},
    "document_structure": "table",
    "control_values": [
        {"label": "Total", "value": "1 250", "parsed_value": 1250, "value_type": "sum",
         "target_column": "qty", "location": "footer", "confidence": 0.9},
        {"label": "Items", "value": "4", "parsed_value": 4, "value_type": "row_count",
         "target_column": None, "location": "footer", "confidence": 0.95},
    ],
    "suggested_chunk_boundaries": ["Section B"],
}


@pytest.mark.asyncio
async def test_prescan_reads_head_and_tail_and_parses_the_answer() -> None:
    prompts: list[str] = []

    async def llm(prompt: str) -> str:
        prompts.append(prompt)
        return "```json\n" + json.dumps(_ANSWER) + "\n```"

    text = "HEAD" + "x" * 10_000 + "TAIL"
    result = await prescan(text, llm=llm, columns=["name", "qty"], instructions="line items")

    assert "HEAD" in prompts[0] and "TAIL" in prompts[0] and "x" * 7000 not in prompts[0]
    assert "line items" in prompts[0] and "name, qty" in prompts[0]
    assert result.columns == ["name", "qty"]
    assert result.structure == "table"
    assert result.expected_rows == 4
    assert result.error is None
    context = result.context()
    assert "columns [name, qty]" in context and "Total=1 250 (column: qty)" in context


@pytest.mark.asyncio
async def test_prescan_failure_returns_an_empty_result_with_the_error() -> None:
    def llm(prompt: str) -> str:
        raise RuntimeError("model down")

    result = await prescan("text", llm=llm)

    assert result.expected_rows is None
    assert result.context() == ""
    assert result.error == "model down"


def test_prescan_expected_rows_needs_a_confident_row_count() -> None:
    weak = PreScan(control_values=[{"value_type": "row_count", "parsed_value": 9,
                                    "confidence": 0.5}])
    assert weak.expected_rows is None


class _CountingEngine(ExtractionEngine):
    """Returns ``answers[text]`` in turn: first call, then the re-run."""

    def __init__(self, name: str, answers: dict[str, list[list[dict[str, Any]]]]) -> None:
        self._name = name
        self.answers = answers
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def supported_extensions(self) -> set[str]:
        return {"txt"}

    def is_available(self) -> bool:
        return True

    async def extract(self, file_path: str, schema, **kwargs: Any) -> ExtractionResult:
        raise AssertionError

    async def extract_text(self, text: str, schema, **kwargs: Any) -> ExtractionResult:
        self.calls.append({"text": text, **kwargs})
        return ExtractionResult(
            data=self.answers[text].pop(0), engine_name=self.name, schema=load_schema(schema)
        )


def _rows(n: int) -> list[dict[str, Any]]:
    return [{"name": f"r{i}"} for i in range(n)]


@pytest.mark.asyncio
async def test_short_chunks_are_rerun_and_the_longer_answer_kept() -> None:
    first = _CountingEngine("first", {"a": [_rows(2)], "b": [_rows(5)]})
    second = _CountingEngine("second", {"a": [_rows(4)]})
    chunks = [
        TextChunk(text="a", index=0, start=0, end=1, strategy="m",
                  metadata={"estimated_rows": 5}),
        TextChunk(text="b", index=1, start=1, end=2, strategy="m",
                  metadata={"estimated_rows": 5}),
    ]
    pre = PreScan(structure="table", control_values=[
        {"label": "Items", "value": "10", "parsed_value": 10, "value_type": "row_count",
         "confidence": 0.9}])

    result = await extract_rows_chunked(
        "ab", {"name": "x"}, engine=first, chunks=chunks, dedupe=False,
        prescan=pre, rerun_below=0.8, rerun_engine=second,
    )

    assert len(result.data["rows"]) == 9
    assert "Document structure: table" in first.calls[0]["context"]
    assert [c["text"] for c in second.calls] == ["a"]
    chunking = result.metadata["chunking"]
    assert chunking["rerun_chunks"] == 1
    assert chunking["chunks"][0]["expected_rows"] == 5
    assert chunking["chunks"][0]["rerun"] == {"engine": "second", "rows": 4, "kept": True}
    assert chunking["chunks"][0]["rows_returned"] == 4
    assert "rerun" not in chunking["chunks"][1]
    assert result.metadata["row_count"] == {
        "expected": 10, "extracted": 9, "status": "passed", "message": "got 9 rows, expected ~10"
    }
    assert result.metadata["prescan"]["structure"] == "table"


@pytest.mark.asyncio
async def test_rerun_keeps_the_first_answer_when_the_rerun_is_not_longer() -> None:
    engine = _CountingEngine("e", {"only": [_rows(1), _rows(1)]})
    pre = PreScan(control_values=[{"value_type": "row_count", "parsed_value": 6,
                                   "confidence": 1.0}])

    result = await extract_rows_chunked(
        "only", {"name": "x"}, engine=engine, max_chars=100, prescan=pre, rerun_below=0.8
    )

    chunk = result.metadata["chunking"]["chunks"][0]
    assert chunk["expected_rows"] == 6  # one chunk: the document's row count applies
    assert chunk["rerun"] == {"engine": "e", "rows": 1, "kept": False}
    assert [c["status"] for c in chunk["checks"] if c["check"] == "row_count"] == ["failed"]
    assert result.metadata["row_count"]["status"] == "failed"


@pytest.mark.asyncio
async def test_prescan_keeps_the_complete_part_of_a_truncated_answer() -> None:
    answer = json.dumps(_ANSWER)
    cut = answer[: answer.index('"suggested_chunk_boundaries"') - 40]

    result = await prescan("text", llm=lambda prompt: cut)

    assert result.error is None and result.repaired is True
    assert result.columns == ["name", "qty"] and result.structure == "table"
    assert len(result.control_values) == 1  # the half-written second value is dropped
    assert result.to_dict()["repaired"] is True
    assert (await prescan("text", llm=lambda p: json.dumps(_ANSWER))).repaired is False
async def test_expected_rows_overrides_format_estimates() -> None:
    chunks = [
        TextChunk(text="a", index=0, start=0, end=1, strategy="m",
                  metadata={"estimated_rows": 40}),
        TextChunk(text="b", index=1, start=1, end=2, strategy="m",
                  metadata={"estimated_rows": 40}),
    ]
    header = _CountingEngine("e", {"a": [_rows(1)], "b": [_rows(1)]})

    result = await extract_rows_chunked(
        "ab", {"name": "x"}, engine=header, chunks=chunks, dedupe=False,
        rerun_below=0.8, expected_rows=lambda chunk: None,
    )

    assert len(header.calls) == 2  # no re-run for a one-row-per-document schema
    assert result.metadata["chunking"]["rerun_chunks"] == 0
    assert [c["expected_rows"] for c in result.metadata["chunking"]["chunks"]] == [None, None]

    total = _CountingEngine("e", {"a": [_rows(1)], "b": [_rows(1)]})
    result = await extract_rows_chunked(
        "ab", {"name": "x"}, engine=total, chunks=chunks, dedupe=False,
        rerun_below=0.8, expected_rows=2,
    )
    assert len(total.calls) == 2
    assert result.metadata["row_count"]["expected"] == 2
    assert result.metadata["row_count"]["status"] == "passed"
