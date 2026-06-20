"""Shared helpers for extraction engine adapters."""

from __future__ import annotations

import inspect
import json
import re
import time
from pathlib import Path
from typing import Any

from extractfold.engines.base import ExtractionResult, JsonSchema, validate_data


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def read_document_text(file_path: str) -> str:
    path = Path(file_path)
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_bytes().decode("utf-8", errors="ignore")


def elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def extract_data_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, ExtractionResult):
        return payload.data
    if hasattr(payload, "model_dump"):
        dumped = payload.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if isinstance(payload, str):
        payload = parse_json_object(payload)
    if not isinstance(payload, dict):
        actual = type(payload).__name__
        raise ValueError(f"Expected extraction payload to be an object, got {actual}")
    for key in ("data", "result", "extraction", "fields"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            field_values = nested.values()
            if key == "fields" and all(isinstance(v, dict) and "value" in v for v in field_values):
                return {name: item.get("value") for name, item in nested.items()}
            return nested
    return payload


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("JSON payload must be an object")
    return parsed


def coerce_data_to_schema(data: dict[str, Any], schema: JsonSchema) -> dict[str, Any]:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return data
    coerced = dict(data)
    for key, field_schema in properties.items():
        if key not in coerced or not isinstance(field_schema, dict):
            continue
        expected = field_schema.get("type")
        if expected in {"number", "integer"} and isinstance(coerced[key], str):
            coerced[key] = _coerce_number(coerced[key], integer=expected == "integer")
        elif expected == "boolean" and isinstance(coerced[key], str):
            lowered = coerced[key].strip().lower()
            if lowered in {"true", "yes", "1"}:
                coerced[key] = True
            elif lowered in {"false", "no", "0"}:
                coerced[key] = False
    return coerced


def _coerce_number(value: str, *, integer: bool) -> float | int | str:
    cleaned = re.sub(r"[^0-9.\-]", "", value)
    if cleaned in {"", "-", "."}:
        return value
    try:
        number = float(cleaned)
    except ValueError:
        return value
    return int(number) if integer else number


def confidence_from_fields(payload: Any) -> dict[str, float]:
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("field_confidence"), dict):
        return {
            str(key): float(value)
            for key, value in payload["field_confidence"].items()
            if isinstance(value, (int, float))
        }
    fields = payload.get("fields")
    if isinstance(fields, dict):
        out: dict[str, float] = {}
        for name, item in fields.items():
            if isinstance(item, dict) and isinstance(item.get("confidence"), (int, float)):
                out[str(name)] = float(item["confidence"])
        return out
    return {}


def provenance_from_fields(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("provenance"), dict):
        return payload["provenance"]
    fields = payload.get("fields")
    if isinstance(fields, dict):
        out: dict[str, Any] = {}
        for name, item in fields.items():
            if isinstance(item, dict):
                out[str(name)] = {
                    key: value
                    for key, value in item.items()
                    if key not in {"value", "confidence"}
                }
        return {key: value for key, value in out.items() if value}
    return {}


def build_result(
    *,
    data: dict[str, Any],
    engine_name: str,
    schema: JsonSchema,
    start: float,
    raw: Any,
    field_confidence: dict[str, float] | None = None,
    provenance: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    pages: int | None = None,
) -> ExtractionResult:
    data = coerce_data_to_schema(data, schema)
    validation = validate_data(data, schema)
    return ExtractionResult(
        data=data,
        engine_name=engine_name,
        schema=schema,
        field_confidence=field_confidence or {},
        provenance=provenance or {},
        valid=validation.valid,
        raw=raw,
        metadata=metadata or {},
        pages=pages,
        processing_time_ms=elapsed_ms(start),
    )
