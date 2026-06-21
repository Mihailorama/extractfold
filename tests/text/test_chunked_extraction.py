from __future__ import annotations

from typing import Any

import pytest

from extractfold.chunking import TextChunk
from extractfold.engines.base import ExtractionEngine, ExtractionResult, load_schema
from extractfold.text import extract_rows_chunked


class ChunkAwareEngine(ExtractionEngine):
    def __init__(self, rows_by_text: dict[str, list[dict[str, Any]]]) -> None:
        self.rows_by_text = rows_by_text
        self.calls: list[dict[str, Any]] = []
        self.schemas_seen: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "chunk_aware"

    @property
    def supported_extensions(self) -> set[str]:
        return {"txt"}

    def is_available(self) -> bool:
        return True

    async def extract(self, file_path: str, schema, **kwargs: Any) -> ExtractionResult:
        raise AssertionError("chunk tests use native text extraction")

    async def extract_text(self, text: str, schema, **kwargs: Any) -> ExtractionResult:
        schema_obj = load_schema(schema)
        self.calls.append({"text": text, "kwargs": kwargs})
        self.schemas_seen.append(schema_obj)
        return ExtractionResult(
            data=self.rows_by_text[text],
            engine_name=self.name,
            schema=schema_obj,
            metadata={"source_text": text},
        )


def _chunk(text: str, index: int, start: int, end: int) -> TextChunk:
    return TextChunk(
        text=text,
        index=index,
        start=start,
        end=end,
        strategy="text",
        overlap=0,
        metadata={"unit": "char"},
    )


@pytest.mark.asyncio
async def test_extract_rows_chunked_runs_chunks_in_order_and_dedupes_rows() -> None:
    engine = ChunkAwareEngine(
        {
            "first": [{"id": 1}, {"id": 2}],
            "second": [{"id": 2}, {"id": 3}],
        }
    )

    result = await extract_rows_chunked(
        "first second",
        [{"id": 0}],
        engine=engine,
        chunks=[_chunk("first", 0, 0, 5), _chunk("second", 1, 6, 12)],
    )

    assert [call["text"] for call in engine.calls] == ["first", "second"]
    assert result.data == {"rows": [{"id": 1}, {"id": 2}, {"id": 3}]}
    assert result.engine_name == "chunk_aware"
    assert result.valid is True
    assert result.metadata["chunking"]["total_chunks"] == 2
    assert result.metadata["chunking"]["duplicates_removed"] == 1
    assert result.metadata["chunking"]["chunks"][0]["rows_returned"] == 2
    assert result.metadata["chunking"]["chunks"][1]["rows_added"] == 1


@pytest.mark.asyncio
async def test_extract_rows_chunked_passes_previous_chunk_digest() -> None:
    engine = ChunkAwareEngine(
        {
            "first": [{"id": 1}],
            "second": [{"id": 2}],
        }
    )

    result = await extract_rows_chunked(
        "first second",
        [{"id": 0}],
        engine=engine,
        chunks=[_chunk("first", 0, 0, 5), _chunk("second", 1, 6, 12)],
    )

    assert engine.calls[0]["kwargs"]["previous_chunk_digest"] is None
    assert isinstance(engine.calls[1]["kwargs"]["previous_chunk_digest"], str)
    assert engine.calls[1]["kwargs"]["previous_chunk_digest"]
    assert (
        engine.calls[1]["kwargs"]["previous_chunk_digest"]
        == result.metadata["chunking"]["chunks"][1]["previous_chunk_digest"]
    )


@pytest.mark.asyncio
async def test_extract_rows_chunked_plans_text_chunks_when_not_supplied() -> None:
    engine = ChunkAwareEngine(
        {
            "abcde": [{"part": "a"}],
            "fghij": [{"part": "b"}],
        }
    )

    result = await extract_rows_chunked(
        "abcdefghij",
        [{"part": ""}],
        engine=engine,
        max_chars=5,
    )

    assert [call["text"] for call in engine.calls] == ["abcde", "fghij"]
    assert result.data == {"rows": [{"part": "a"}, {"part": "b"}]}


@pytest.mark.asyncio
async def test_extract_rows_chunked_preserves_template_conversion_metadata() -> None:
    engine = ChunkAwareEngine({"first": [{"sku": "A-1"}]})
    template = {
        "sku": {"type": "string"},
        "score": {"type": "number", "computed": True},
    }

    result = await extract_rows_chunked(
        "first",
        template,
        engine=engine,
        chunks=[_chunk("first", 0, 0, 5)],
    )

    assert engine.schemas_seen == [
        {
            "type": "object",
            "properties": {"sku": {"type": "string"}},
        }
    ]
    assert result.metadata["schema_conversion"] == {
        "computed_fields": {"score": {"type": "number", "computed": True}}
    }
