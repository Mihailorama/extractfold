"""Text-first extraction helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol, runtime_checkable

from extractfold.engines._common import maybe_await
from extractfold.engines.base import (
    ExtractionEngine,
    ExtractionResult,
    JsonSchema,
    load_schema,
    validate_data,
)


@runtime_checkable
class TextExtractionEngine(Protocol):
    """Protocol for engines that can extract directly from prepared text."""

    async def extract_text(
        self,
        text: str,
        schema: JsonSchema | str | Mapping[str, Any],
        **kwargs: Any,
    ) -> ExtractionResult:
        """Extract schema-conformant data from prepared text."""
        ...


async def extract_text(
    text: str,
    schema: JsonSchema | str | Mapping[str, Any],
    *,
    engine: ExtractionEngine,
    **kwargs: Any,
) -> ExtractionResult:
    """Extract structured data from already-prepared text."""
    if isinstance(engine, TextExtractionEngine):
        return await engine.extract_text(text, schema, **kwargs)

    if "txt" not in engine.supported_extensions:
        raise ValueError(f"Engine {engine.name!r} does not support prepared text extraction")

    schema_obj = load_schema(schema)
    with TemporaryDirectory(prefix="extractfold-text-") as directory:
        path = Path(directory) / "input.txt"
        path.write_text(text, encoding="utf-8")
        return await maybe_await(engine.extract(str(path), schema_obj, **kwargs))


async def extract_rows(
    text: str,
    schema: JsonSchema | str | Mapping[str, Any],
    *,
    engine: ExtractionEngine,
    **kwargs: Any,
) -> ExtractionResult:
    """Extract structured rows from already-prepared text."""
    result = await extract_text(text, schema, engine=engine, **kwargs)
    if isinstance(result.data, dict) and isinstance(result.data.get("rows"), list):
        return result
    if isinstance(result.data, list):
        wrapped_schema = _rows_wrapper_schema(load_schema(schema))
        wrapped_data = {"rows": result.data}
        validation = validate_data(wrapped_data, wrapped_schema)
        return replace(
            result,
            data=wrapped_data,
            schema=wrapped_schema,
            valid=validation.valid,
            metadata={**result.metadata, "row_schema": load_schema(schema)},
        )
    raise ValueError("Row extraction expected a list payload or an object with a 'rows' list")


def _rows_wrapper_schema(schema: JsonSchema) -> JsonSchema:
    return {
        "type": "object",
        "required": ["rows"],
        "properties": {
            "rows": schema if schema.get("type") == "array" else {"type": "array", "items": schema}
        },
    }
