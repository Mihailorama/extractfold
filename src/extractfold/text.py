"""Text-first extraction helpers."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol, runtime_checkable

from extractfold.chunking import TextChunk, chunk_text
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


async def extract_rows_chunked(
    text: str,
    schema: Any,
    *,
    engine: ExtractionEngine,
    chunks: Sequence[TextChunk] | None = None,
    max_chars: int | None = None,
    overlap: int = 0,
    **kwargs: Any,
) -> ExtractionResult:
    """Extract structured rows from prepared text with chunked orchestration."""
    start = time.perf_counter()
    conversion = _load_or_convert_row_schema(schema)
    row_schema = conversion.schema
    result_schema = _row_result_schema(row_schema)
    planned_chunks = _resolve_chunks(text, chunks=chunks, max_chars=max_chars, overlap=overlap)

    rows: list[Any] = []
    seen: set[str] = set()
    raw_results: list[Any] = []
    chunk_metadata: list[dict[str, Any]] = []
    total_duplicates = 0
    previous_digest: str | None = None

    for chunk in planned_chunks:
        chunk_result = await extract_rows(
            chunk.text,
            row_schema,
            engine=engine,
            chunk=chunk.to_dict(),
            previous_chunk_digest=previous_digest,
            **kwargs,
        )
        chunk_rows = chunk_result.data.get("rows", [])
        if not isinstance(chunk_rows, list):
            raise ValueError("Chunk extraction expected an object with a 'rows' list")

        added = 0
        duplicates = 0
        for row in chunk_rows:
            row_key = _row_key(row)
            if row_key in seen:
                duplicates += 1
                continue
            seen.add(row_key)
            rows.append(row)
            added += 1

        chunk_metadata.append(
            {
                **chunk.to_dict(),
                "previous_chunk_digest": previous_digest,
                "rows_returned": len(chunk_rows),
                "rows_added": added,
                "duplicates_removed": duplicates,
                "valid": chunk_result.valid,
                "engine_name": chunk_result.engine_name,
                "processing_time_ms": chunk_result.processing_time_ms,
            }
        )
        raw_results.append(chunk_result.raw)
        total_duplicates += duplicates
        previous_digest = _digest_rows(chunk_rows)

    data = {"rows": rows}
    validation = validate_data(data, result_schema)
    return ExtractionResult(
        data=data,
        engine_name=engine.name,
        schema=result_schema,
        valid=validation.valid,
        raw=raw_results,
        metadata={
            "row_schema": row_schema,
            "schema_conversion": conversion.metadata,
            "chunking": {
                "strategy": "sequential",
                "total_chunks": len(planned_chunks),
                "rows_extracted": len(rows),
                "duplicates_removed": total_duplicates,
                "chunks": chunk_metadata,
            },
        },
        processing_time_ms=int((time.perf_counter() - start) * 1000),
    )


def _resolve_chunks(
    text: str,
    *,
    chunks: Sequence[TextChunk] | None,
    max_chars: int | None,
    overlap: int,
) -> list[TextChunk]:
    if chunks is not None:
        return list(chunks)
    if max_chars is None:
        raise ValueError("extract_rows_chunked requires chunks or max_chars")
    return chunk_text(text, max_chars=max_chars, overlap=overlap)


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


def _row_key(row: Any) -> str:
    try:
        return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return repr(row)


def _digest_rows(rows: Sequence[Any]) -> str:
    payload = json.dumps(list(rows), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
