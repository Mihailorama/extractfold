"""Dependency-free parsing helpers for extraction payloads."""

from __future__ import annotations

import json
import re
from typing import Any


def parse_json_payload(text: str) -> Any:
    """Parse a JSON object or array from model text."""
    stripped = _strip_fence(text.strip())
    parsed = _try_json_loads(stripped)
    if parsed is not _NO_MATCH:
        return parsed

    for candidate in _json_candidates(stripped):
        parsed = _try_json_loads(candidate)
        if parsed is not _NO_MATCH:
            return parsed

    raise ValueError("Could not parse JSON payload")


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from model text."""
    parsed = parse_json_payload(text)
    if not isinstance(parsed, dict):
        raise ValueError("JSON payload must be an object")
    return parsed


def parse_json_array(text: str) -> list[Any]:
    """Parse a JSON array from model text."""
    parsed = parse_json_payload(text)
    if not isinstance(parsed, list):
        raise ValueError("JSON payload must be an array")
    return parsed


def normalize_data_payload(payload: Any) -> dict[str, Any]:
    """Normalize provider payloads into the ExtractionResult data object."""
    if isinstance(payload, str):
        payload = parse_json_payload(payload)

    if isinstance(payload, list):
        return {"rows": payload}

    if not isinstance(payload, dict):
        actual = type(payload).__name__
        raise ValueError(f"Expected extraction payload to be an object or array, got {actual}")

    rows = payload.get("rows")
    if isinstance(rows, list):
        return {"rows": rows}

    fields = payload.get("fields")
    if isinstance(fields, dict):
        field_values = fields.values()
        if all(isinstance(value, dict) and "value" in value for value in field_values):
            return {name: value.get("value") for name, value in fields.items()}

    for key in ("data", "result", "extraction"):
        nested = payload.get(key)
        if isinstance(nested, list):
            return {"rows": nested}
        if isinstance(nested, dict):
            nested_rows = nested.get("rows")
            if isinstance(nested_rows, list):
                return {"rows": nested_rows}
            return nested

    return payload


_NO_MATCH = object()


def _strip_fence(text: str) -> str:
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return text


def _try_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _NO_MATCH


def _json_candidates(text: str) -> list[str]:
    candidates: list[tuple[int, int, str]] = []
    for open_char, close_char in (("{", "}"), ("[", "]")):
        start = text.find(open_char)
        end = text.rfind(close_char)
        if start != -1 and end != -1 and end > start:
            candidates.append((start, end, text[start : end + 1]))
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    return [candidate for _, _, candidate in candidates]
