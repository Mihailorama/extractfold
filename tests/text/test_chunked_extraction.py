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


class FailingChunkEngine(ChunkAwareEngine):
    def __init__(
        self,
        rows_by_text: dict[str, list[dict[str, Any]]],
        *,
        fail_on: set[str],
    ) -> None:
        super().__init__(rows_by_text)
        self.fail_on = fail_on

    async def extract_text(self, text: str, schema, **kwargs: Any) -> ExtractionResult:
        if text in self.fail_on:
            self.calls.append({"text": text, "kwargs": kwargs})
            raise RuntimeError(f"chunk failed: {text}")
        return await super().extract_text(text, schema, **kwargs)


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


@pytest.mark.asyncio
async def test_extract_rows_chunked_raises_by_default_when_chunk_fails() -> None:
    engine = FailingChunkEngine(
        {
            "first": [{"id": 1}],
            "third": [{"id": 3}],
        },
        fail_on={"second"},
    )

    with pytest.raises(RuntimeError, match="chunk failed: second"):
        await extract_rows_chunked(
            "first second third",
            [{"id": 0}],
            engine=engine,
            chunks=[
                _chunk("first", 0, 0, 5),
                _chunk("second", 1, 6, 12),
                _chunk("third", 2, 13, 18),
            ],
        )


@pytest.mark.asyncio
async def test_extract_rows_chunked_can_continue_after_failed_chunks() -> None:
    engine = FailingChunkEngine(
        {
            "first": [{"id": 1}],
            "third": [{"id": 3}],
        },
        fail_on={"second"},
    )

    result = await extract_rows_chunked(
        "first second third",
        [{"id": 0}],
        engine=engine,
        chunks=[
            _chunk("first", 0, 0, 5),
            _chunk("second", 1, 6, 12),
            _chunk("third", 2, 13, 18),
        ],
        continue_on_error=True,
    )

    chunking = result.metadata["chunking"]

    assert result.data == {"rows": [{"id": 1}, {"id": 3}]}
    assert result.valid is False
    assert result.raw[1] == {"error_type": "RuntimeError", "error": "chunk failed: second"}
    assert chunking["total_chunks"] == 3
    assert chunking["succeeded_chunks"] == 2
    assert chunking["failed_chunks"] == 1
    assert chunking["partial"] is True
    assert chunking["chunks"][1]["status"] == "failed"
    assert chunking["chunks"][1]["error_type"] == "RuntimeError"
    assert chunking["chunks"][1]["error"] == "chunk failed: second"
    assert chunking["chunks"][1]["rows_returned"] == 0
    assert chunking["chunks"][1]["rows_added"] == 0
    assert chunking["chunks"][1]["duplicates_removed"] == 0
    assert chunking["chunks"][2]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_extract_rows_chunked_keeps_identical_rows_when_dedupe_is_off() -> None:
    line = {"name": "Radiator", "qty": 2}
    engine = ChunkAwareEngine({"a": [line, line], "b": [line]})
    result = await extract_rows_chunked(
        "ab",
        [{"name": "", "qty": 0}],
        engine=engine,
        chunks=[_chunk("a", 0, 0, 1), _chunk("b", 1, 1, 2)],
        dedupe=False,
    )
    assert result.data["rows"] == [line, line, line]
    assert result.metadata["chunking"]["duplicates_removed"] == 0


@pytest.mark.asyncio
async def test_extract_rows_chunked_runs_chunks_concurrently_in_order() -> None:
    import asyncio

    running = 0
    peak = 0

    class SlowEngine(ChunkAwareEngine):
        async def extract_text(self, text: str, schema, **kwargs: Any) -> ExtractionResult:
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1
            return await super().extract_text(text, schema, **kwargs)

    engine = SlowEngine({"a": [{"n": 1}], "b": [{"n": 2}], "c": [{"n": 3}]})
    result = await extract_rows_chunked(
        "abc",
        [{"n": 0}],
        engine=engine,
        chunks=[_chunk("a", 0, 0, 1), _chunk("b", 1, 1, 2), _chunk("c", 2, 2, 3)],
        concurrency=3,
    )
    assert peak == 3
    assert result.data["rows"] == [{"n": 1}, {"n": 2}, {"n": 3}]


@pytest.mark.asyncio
async def test_extract_rows_chunked_reports_quality_checks_and_truncation_per_chunk() -> None:
    from extractfold.engines.provider_router_engine import ProviderRouterEngine

    def provider_call(**kwargs: Any) -> dict[str, Any]:
        if kwargs["text"] == "one":
            return {"content": '{"rows": [{"name": "a"}]}', "finish_reason": "length"}
        return {"content": '{"rows": [{"name": "b"}, {"name": "c"}]}', "finish_reason": "stop"}

    chunks = [
        TextChunk(text="one", index=0, start=0, end=3, strategy="manual"),
        TextChunk(text="two", index=1, start=3, end=6, strategy="manual"),
    ]
    result = await extract_rows_chunked(
        "onetwo",
        {"type": "object", "properties": {"name": {"type": "string"}}},
        engine=ProviderRouterEngine(provider_call=provider_call),
        chunks=chunks,
    )

    chunking = result.metadata["chunking"]
    assert chunking["truncated_chunks"] == 1
    assert [c["truncated"] for c in chunking["chunks"]] == [True, False]
    checks = chunking["chunks"][1]["checks"]
    assert [c["check"] for c in checks] == ["schema_compliance", "suspicious_patterns"]
    assert all(c["status"] == "passed" for c in checks)


@pytest.mark.asyncio
async def test_extract_rows_chunked_records_a_structured_llm_failure() -> None:
    from extractfold.engines.provider_router_engine import ProviderRouterEngine

    def provider_call(**kwargs: Any) -> Any:
        if kwargs["text"] == "bad":
            raise RuntimeError("quota exceeded")
        return '[{"name": "ok"}]'

    chunks = [
        TextChunk(text="bad", index=0, start=0, end=3, strategy="manual"),
        TextChunk(text="good", index=1, start=3, end=7, strategy="manual"),
    ]
    engine = ProviderRouterEngine(models=["m1"], provider_call=provider_call, raise_on_error=False)
    result = await extract_rows_chunked("badgood", {"name": "x"}, engine=engine, chunks=chunks)

    chunking = result.metadata["chunking"]
    assert result.data["rows"] == [{"name": "ok"}]
    assert result.valid is False
    assert chunking["failed_chunks"] == 1 and chunking["partial"] is True
    assert chunking["chunks"][0]["status"] == "failed"
    failed = chunking["chunks"][0]
    assert (failed["stage"], failed["model"], failed["error"]) == ("llm", "m1", "quota exceeded")
    assert failed["error_type"] == "LLMError"
