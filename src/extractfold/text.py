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
from extractfold.schema import SchemaConversionResult, template_to_schema


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
    schema: Any,
    *,
    engine: ExtractionEngine,
    **kwargs: Any,
) -> ExtractionResult:
    """Extract structured rows from already-prepared text."""
    conversion = _load_or_convert_row_schema(schema)
    row_schema = conversion.schema
    result = await extract_text(text, row_schema, engine=engine, **kwargs)
    if isinstance(result.data, dict) and isinstance(result.data.get("rows"), list):
        wrapped_schema = _row_result_schema(row_schema)
        validation = validate_data(result.data, wrapped_schema)
        return replace(
            result,
            schema=wrapped_schema,
            valid=validation.valid,
            metadata=_merge_row_metadata(result.metadata, row_schema, conversion.metadata),
        )
    if isinstance(result.data, list):
        wrapped_schema = _row_result_schema(row_schema)
        wrapped_data = {"rows": result.data}
        validation = validate_data(wrapped_data, wrapped_schema)
        return replace(
            result,
            data=wrapped_data,
            schema=wrapped_schema,
            valid=validation.valid,
            metadata=_merge_row_metadata(result.metadata, row_schema, conversion.metadata),
        )
    raise ValueError("Row extraction expected a list payload or an object with a 'rows' list")


def _load_or_convert_row_schema(schema: Any) -> SchemaConversionResult:
    if isinstance(schema, list):
        return template_to_schema(schema)
    if isinstance(schema, Mapping) and not _looks_like_json_schema(schema):
        return template_to_schema(schema)
    return SchemaConversionResult(schema=load_schema(schema), metadata={"computed_fields": {}})


def _looks_like_json_schema(schema: Mapping[str, Any]) -> bool:
    return any(key in schema for key in ("$schema", "type", "properties", "items", "required"))


def _row_result_schema(schema: JsonSchema) -> JsonSchema:
    return schema if _is_rows_wrapper_schema(schema) else _rows_wrapper_schema(schema)


def _rows_wrapper_schema(schema: JsonSchema) -> JsonSchema:
    return {
        "type": "object",
        "required": ["rows"],
        "properties": {
            "rows": schema if schema.get("type") == "array" else {"type": "array", "items": schema}
        },
    }


def _is_rows_wrapper_schema(schema: JsonSchema) -> bool:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return False
    rows_schema = properties.get("rows")
    return isinstance(rows_schema, dict) and rows_schema.get("type") == "array"


def _merge_row_metadata(
    metadata: dict[str, Any],
    row_schema: JsonSchema,
    conversion_metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        **metadata,
        "row_schema": row_schema,
        "schema_conversion": conversion_metadata,
    }
