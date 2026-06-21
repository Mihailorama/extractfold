from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from extractfold.engines.base import ExtractionEngine, ExtractionResult, load_schema
from extractfold.text import extract_rows, extract_text


class NativeTextEngine(ExtractionEngine):
    def __init__(self, data: Any) -> None:
        self.data = data
        self.extract_called = False
        self.text_seen: str | None = None
        self.kwargs_seen: dict[str, Any] | None = None
        self.schema_seen: dict[str, Any] | None = None

    @property
    def name(self) -> str:
        return "native_text"

    @property
    def supported_extensions(self) -> set[str]:
        return {"txt"}

    def is_available(self) -> bool:
        return True

    async def extract(self, file_path: str, schema, **kwargs: Any) -> ExtractionResult:
        self.extract_called = True
        raise AssertionError("native text engines should not be routed through file extraction")

    async def extract_text(self, text: str, schema, **kwargs: Any) -> ExtractionResult:
        self.text_seen = text
        self.kwargs_seen = kwargs
        self.schema_seen = load_schema(schema)
        return ExtractionResult(
            data=self.data,
            engine_name=self.name,
            schema=self.schema_seen,
            metadata={"native": True},
        )


class FileOnlyTextEngine(ExtractionEngine):
    def __init__(self) -> None:
        self.file_path_seen: str | None = None
        self.file_text_seen: str | None = None
        self.kwargs_seen: dict[str, Any] | None = None

    @property
    def name(self) -> str:
        return "file_only_text"

    @property
    def supported_extensions(self) -> set[str]:
        return {"txt"}

    def is_available(self) -> bool:
        return True

    async def extract(self, file_path: str, schema, **kwargs: Any) -> ExtractionResult:
        self.file_path_seen = file_path
        self.file_text_seen = Path(file_path).read_text(encoding="utf-8")
        self.kwargs_seen = kwargs
        return ExtractionResult(
            data={"source": "file", "flag": kwargs["flag"]},
            engine_name=self.name,
            schema=load_schema(schema),
        )


@pytest.mark.asyncio
async def test_extract_text_uses_native_text_engine() -> None:
    schema = {"type": "object", "properties": {"vendor": {"type": "string"}}}
    engine = NativeTextEngine({"vendor": "Acme"})

    result = await extract_text("Vendor: Acme", schema, engine=engine, trace_id="abc")

    assert result.data == {"vendor": "Acme"}
    assert result.engine_name == "native_text"
    assert result.metadata == {"native": True}
    assert engine.text_seen == "Vendor: Acme"
    assert engine.kwargs_seen == {"trace_id": "abc"}
    assert engine.extract_called is False


@pytest.mark.asyncio
async def test_extract_text_falls_back_to_file_engine_for_txt() -> None:
    schema = {"type": "object", "properties": {"source": {"type": "string"}}}
    engine = FileOnlyTextEngine()

    result = await extract_text("prepared text", schema, engine=engine, flag="ok")

    assert result.data == {"source": "file", "flag": "ok"}
    assert result.engine_name == "file_only_text"
    assert engine.file_path_seen is not None
    assert engine.file_path_seen.endswith(".txt")
    assert engine.file_text_seen == "prepared text"
    assert engine.kwargs_seen == {"flag": "ok"}


@pytest.mark.asyncio
async def test_extract_rows_wraps_native_array_payload() -> None:
    row_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"sku": {"type": "string"}},
        },
    }
    engine = NativeTextEngine([{"sku": "A-1"}, {"sku": "B-2"}])

    result = await extract_rows("SKU A-1\nSKU B-2", row_schema, engine=engine)

    assert result.data == {"rows": [{"sku": "A-1"}, {"sku": "B-2"}]}
    assert result.engine_name == "native_text"
    assert result.valid is True


@pytest.mark.asyncio
async def test_extract_rows_preserves_existing_rows_wrapper() -> None:
    row_schema = {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            }
        },
    }
    engine = NativeTextEngine({"rows": [{"name": "Ada"}]})

    result = await extract_rows("name: Ada", row_schema, engine=engine)

    assert result.data == {"rows": [{"name": "Ada"}]}
    assert result.valid is True


@pytest.mark.asyncio
async def test_extract_rows_accepts_sample_array_template() -> None:
    template = [{"sku": "", "quantity": 0}]
    engine = NativeTextEngine([{"sku": "A-1", "quantity": 2}])

    result = await extract_rows("SKU A-1 quantity 2", template, engine=engine)

    assert engine.schema_seen == {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "quantity": {"type": "integer"},
            },
        },
    }
    assert result.data == {"rows": [{"sku": "A-1", "quantity": 2}]}
    assert result.metadata["row_schema"] == engine.schema_seen


@pytest.mark.asyncio
async def test_extract_rows_accepts_field_descriptor_template() -> None:
    template = {
        "sku": {"type": "string", "required": True},
        "quantity": {"type": "integer"},
    }
    engine = NativeTextEngine([{"sku": "A-1", "quantity": 2}])

    result = await extract_rows("SKU A-1 quantity 2", template, engine=engine)

    assert engine.schema_seen == {
        "type": "object",
        "required": ["sku"],
        "properties": {
            "sku": {"type": "string"},
            "quantity": {"type": "integer"},
        },
    }
    assert result.schema == {
        "type": "object",
        "required": ["rows"],
        "properties": {
            "rows": {
                "type": "array",
                "items": engine.schema_seen,
            }
        },
    }


@pytest.mark.asyncio
async def test_extract_rows_preserves_computed_field_metadata() -> None:
    template = {
        "sku": {"type": "string"},
        "score": {"type": "number", "computed": True},
    }
    engine = NativeTextEngine([{"sku": "A-1"}])

    result = await extract_rows("SKU A-1", template, engine=engine)

    assert engine.schema_seen == {
        "type": "object",
        "properties": {
            "sku": {"type": "string"},
        },
    }
    assert result.metadata["schema_conversion"] == {
        "computed_fields": {
            "score": {"type": "number", "computed": True},
        }
    }
