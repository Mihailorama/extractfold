"""Text-first extraction helpers."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol, runtime_checkable

from extractfold.chunking import TextChunk, chunk_document, chunk_text
from extractfold.engines._common import maybe_await
from extractfold.engines.base import (
    ExtractionEngine,
    ExtractionResult,
    JsonSchema,
    load_schema,
    validate_data,
)
from extractfold.prescan import PreScan
from extractfold.provenance import catalog_for_span, field_confidence
from extractfold.quality import check_rows
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
    if isinstance(result.metadata.get("error"), dict) and not result.data:
        return replace(
            result,
            data={"rows": []},
            schema=_row_result_schema(row_schema),
            valid=False,
            metadata=_merge_row_metadata(result.metadata, row_schema, conversion.metadata),
        )
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
    continue_on_error: bool = False,
    dedupe: bool = True,
    concurrency: int = 1,
    prescan: PreScan | None = None,
    rerun_below: float | None = None,
    rerun_engine: ExtractionEngine | None = None,
    input_format: str | None = None,
    max_rows: int | None = None,
    source_catalog: Sequence[Mapping[str, Any]] | None = None,
    **kwargs: Any,
) -> ExtractionResult:
    """Extract structured rows from prepared text with chunked orchestration.

    ``dedupe=False`` keeps identical rows (line items repeat legitimately; chunks without
    overlap produce no duplicates). ``concurrency > 1`` extracts up to that many chunks at
    once; rows still come back in chunk order, but engines then get no
    ``previous_chunk_digest``.

    Row-count control: a chunk's expected rows come from ``chunk.metadata["estimated_rows"]``,
    or, for a single chunk, from ``prescan.expected_rows``. A *prescan* also reaches every
    chunk call as ``context=``. With *rerun_below* (e.g. ``0.8``) a chunk returning fewer
    than that share of its expected rows is extracted again with *rerun_engine* (default
    *engine*) and the longer answer is kept.

    With *input_format* (``spreadsheet``, ``csv``, ``json``, ``html``, ``markdown``, ...)
    chunks are planned by :func:`extractfold.chunking.chunk_document` within *max_chars*
    and *max_rows* (see :func:`extractfold.chunking.chunk_budget`). A JSON array of objects
    whose keys are all schema fields is returned as is, without a model call
    (``metadata["passthrough"]``).

    With *source_catalog* (:func:`extractfold.provenance.build_source_catalog` of *text*)
    each chunk call gets the entries inside that chunk as ``source_catalog=``; the result's
    ``provenance["rows"]`` stays aligned with ``data["rows"]``.
    """
    start = time.perf_counter()
    conversion = _load_or_convert_row_schema(schema)
    row_schema = conversion.schema
    result_schema = _row_result_schema(row_schema)
    if chunks is None and input_format in (None, "json"):
        passthrough = _flat_json_rows(text, row_schema)
        if passthrough is not None:
            data = {"rows": passthrough}
            return ExtractionResult(
                data=data,
                engine_name=engine.name,
                schema=result_schema,
                valid=validate_data(data, result_schema).valid,
                metadata={
                    "row_schema": row_schema,
                    "schema_conversion": conversion.metadata,
                    "passthrough": True,
                },
                processing_time_ms=int((time.perf_counter() - start) * 1000),
            )
    if chunks is None and input_format is not None:
        if max_chars is None:
            raise ValueError("extract_rows_chunked requires max_chars with input_format")
        chunks = chunk_document(
            text, input_format=input_format, max_chars=max_chars, max_rows=max_rows
        )
    planned_chunks = _resolve_chunks(text, chunks=chunks, max_chars=max_chars, overlap=overlap)

    rows: list[Any] = []
    provenance_rows: list[Any] = []
    seen: set[str] = set()
    raw_results: list[Any] = []
    chunk_metadata: list[dict[str, Any]] = []
    total_duplicates = 0
    failed_chunks = 0
    succeeded_chunks = 0
    truncated_chunks = 0
    columns = _columns(row_schema)
    rerun_chunks = 0
    previous_digest: str | None = None
    prescan_context = prescan.context() if prescan else ""

    def _expected(chunk: TextChunk) -> int | None:
        estimate = chunk.metadata.get("estimated_rows")
        if isinstance(estimate, int):
            return estimate
        return prescan.expected_rows if prescan and len(planned_chunks) == 1 else None

    async def _call(
        chunk: TextChunk, digest: str | None, use: ExtractionEngine
    ) -> ExtractionResult:
        context = "\n\n".join(
            part for part in (prescan_context, chunk.metadata.get("context")) if part
        )
        extra: dict[str, Any] = {"context": context} if context else {}
        if source_catalog is not None:
            extra["source_catalog"] = catalog_for_span(source_catalog, chunk.start, chunk.end)
        return await extract_rows(
            chunk.text,
            row_schema,
            engine=use,
            chunk=chunk.to_dict(),
            previous_chunk_digest=digest,
            **extra,
            **kwargs,
        )

    prefetched: list[Any] | None = None
    if concurrency > 1 and len(planned_chunks) > 1:
        limit = asyncio.Semaphore(concurrency)

        async def _one(chunk: TextChunk) -> ExtractionResult:
            async with limit:
                return await _call(chunk, None, engine)

        prefetched = await asyncio.gather(
            *(_one(c) for c in planned_chunks), return_exceptions=True
        )

    for index, chunk in enumerate(planned_chunks):
        try:
            if prefetched is not None:
                outcome = prefetched[index]
                if isinstance(outcome, BaseException):
                    raise outcome
                chunk_result = outcome
            else:
                chunk_result = await _call(chunk, previous_digest, engine)
            if isinstance(chunk_result.metadata.get("error"), dict):
                raise _LLMFailureError(chunk_result.metadata["error"])
            chunk_rows = chunk_result.data.get("rows", [])
            if not isinstance(chunk_rows, list):
                raise ValueError("Chunk extraction expected an object with a 'rows' list")
        except Exception as exc:
            # The engine already chose not to raise for an LLM failure: record it.
            if not continue_on_error and not isinstance(exc, _LLMFailureError):
                raise
            error_payload = _chunk_error_payload(exc)
            chunk_metadata.append(
                {
                    **chunk.to_dict(),
                    "previous_chunk_digest": previous_digest,
                    "status": "failed",
                    "rows_returned": 0,
                    "rows_added": 0,
                    "duplicates_removed": 0,
                    "valid": False,
                    "engine_name": engine.name,
                    "processing_time_ms": 0,
                    **error_payload,
                }
            )
            raw_results.append(error_payload)
            failed_chunks += 1
            continue

        expected = _expected(chunk)
        rerun: dict[str, Any] | None = None
        if rerun_below is not None and expected and len(chunk_rows) < rerun_below * expected:
            # ponytail: re-runs go one at a time, even with concurrency; batch them if slow.
            use = rerun_engine or engine
            try:
                retry = await _call(chunk, previous_digest, use)
                retry_rows = retry.data.get("rows", [])
                if retry.metadata.get("error") or not isinstance(retry_rows, list):
                    retry_rows = []
            except Exception:
                if not continue_on_error:
                    raise
                retry_rows = []
            kept = len(retry_rows) > len(chunk_rows)
            rerun = {"engine": use.name, "rows": len(retry_rows), "kept": kept}
            rerun_chunks += 1
            if kept:
                chunk_result, chunk_rows = retry, retry_rows

        added = 0
        duplicates = 0
        chunk_provenance = chunk_result.provenance.get("rows")
        if not isinstance(chunk_provenance, list):
            chunk_provenance = []
        for position, row in enumerate(chunk_rows):
            row_key = _row_key(row)
            if dedupe and row_key in seen:
                duplicates += 1
                continue
            seen.add(row_key)
            rows.append(row)
            provenance_rows.append(
                chunk_provenance[position] if position < len(chunk_provenance) else {}
            )
            added += 1

        truncated = bool(chunk_result.metadata.get("truncated"))
        truncated_chunks += truncated
        chunk_metadata.append(
            {
                **chunk.to_dict(),
                "previous_chunk_digest": previous_digest,
                "status": "succeeded",
                "truncated": truncated,
                "checks": check_rows(chunk_rows, columns=columns, expected_rows=expected),
                "expected_rows": expected,
                **({"rerun": rerun} if rerun else {}),
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
        succeeded_chunks += 1
        previous_digest = _digest_rows(chunk_rows)

    data = {"rows": rows}
    validation = validate_data(data, result_schema)
    control: dict[str, Any] = {}
    if prescan is not None:
        control["prescan"] = prescan.to_dict()
        if prescan.expected_rows is not None:
            check = check_rows(rows, expected_rows=prescan.expected_rows)[0]
            control["row_count"] = {
                "expected": prescan.expected_rows,
                "extracted": len(rows),
                "status": check["status"],
                "message": check["message"],
            }
    provenance = {"rows": provenance_rows} if any(provenance_rows) else {}
    return ExtractionResult(
        data=data,
        engine_name=engine.name,
        schema=result_schema,
        provenance=provenance,
        field_confidence=field_confidence(provenance_rows) if provenance else {},
        valid=validation.valid and failed_chunks == 0,
        raw=raw_results,
        metadata={
            "row_schema": row_schema,
            "schema_conversion": conversion.metadata,
            "chunking": {
                "strategy": "sequential",
                "total_chunks": len(planned_chunks),
                "succeeded_chunks": succeeded_chunks,
                "failed_chunks": failed_chunks,
                "partial": failed_chunks > 0,
                "rows_extracted": len(rows),
                "duplicates_removed": total_duplicates,
                "truncated_chunks": truncated_chunks,
                "rerun_chunks": rerun_chunks,
                "chunks": chunk_metadata,
            },
            **control,
        },
        processing_time_ms=int((time.perf_counter() - start) * 1000),
    )


def _flat_json_rows(text: str, row_schema: JsonSchema) -> list[dict[str, Any]] | None:
    """Rows of a JSON array of objects that already use only the schema's fields."""
    stripped = text.lstrip()
    if not stripped.startswith("["):
        return None
    fields = set(_columns(row_schema))
    try:
        rows = json.loads(stripped)
    except ValueError:
        return None
    if not fields or not isinstance(rows, list) or not rows:
        return None
    if not all(isinstance(row, dict) and row and set(row) <= fields for row in rows):
        return None
    item_schema = row_schema.get("items", row_schema) if row_schema.get("type") == "array" else (
        row_schema
    )
    if not all(validate_data(row, item_schema).valid for row in rows):
        return None
    return rows


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


class _LLMFailureError(Exception):
    """A structured LLM failure an engine returned instead of raising."""

    def __init__(self, error: dict[str, Any]) -> None:
        super().__init__(str(error.get("message", "")))
        self.error = error


def _chunk_error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, _LLMFailureError):
        return {
            "error_type": "LLMError",
            "error": str(exc),
            "stage": exc.error.get("stage", "llm"),
            "model": exc.error.get("model"),
        }
    return {"error_type": type(exc).__name__, "error": str(exc)}


def _columns(row_schema: JsonSchema) -> list[str]:
    items = row_schema.get("items") if row_schema.get("type") == "array" else row_schema
    properties = items.get("properties") if isinstance(items, dict) else None
    return list(properties) if isinstance(properties, dict) else []
