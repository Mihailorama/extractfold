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


def parse_llm_json(text: str) -> tuple[Any, bool]:
    """Parse a model answer; repair it only when plain parsing fails.

    Returns ``(data, repaired)``. Plain parsing uses ``orjson`` when installed (the
    ``fast_json`` extra), then the stdlib, also inside code fences or surrounding prose.
    A truncated answer is cut back to its last complete element and closed (built in,
    5-10x faster than ``json_repair`` on large answers); other damage (unquoted keys,
    trailing commas) goes to ``json_repair`` when installed.
    """
    stripped = _strip_fence(text.strip())
    start = min((i for i in (stripped.find("{"), stripped.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("Could not parse JSON payload")
    # Prose around the JSON is fine; a candidate that skips its opening bracket is not.
    candidates = [c for c in _json_candidates(stripped) if stripped.startswith(c, start)]
    for candidate in (stripped, *candidates):
        parsed = _fast_loads(candidate)
        if parsed is not _NO_MATCH:
            return parsed, False
    repaired = _close_truncated(stripped[start:])
    if repaired is _NO_MATCH or repaired in ({}, []):
        try:
            import json_repair  # type: ignore[import-not-found]
        except ImportError:
            pass
        else:
            fixed = json_repair.loads(stripped[start:])
            if isinstance(fixed, (dict, list)) and fixed not in ({}, []):
                repaired = fixed
    if repaired is _NO_MATCH:
        raise ValueError("Could not parse or repair JSON payload")
    return repaired, True


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


def _fast_loads(text: str) -> Any:
    try:
        import orjson  # type: ignore[import-not-found]
    except ImportError:
        return _try_json_loads(text)
    try:
        return orjson.loads(text)
    except orjson.JSONDecodeError:
        return _NO_MATCH


def _close_truncated(text: str) -> Any:
    """Cut *text* (starting at ``{`` or ``[``) back to its last complete element, close it.

    Cuts only after a closed object/array or at a top-level comma, so a half-written
    last row is dropped rather than kept with missing fields.
    """
    stack: list[str] = []
    checkpoints: list[tuple[int, str]] = []  # (cut position, closers)
    in_string = escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]":
            if not stack:
                break
            stack.pop()
            checkpoints.append((index + 1, "".join(reversed(stack))))
            if not stack:
                break
        elif char == "," and len(stack) == 1:
            checkpoints.append((index, stack[0]))
        if len(stack) == 1 and char in "{[":
            checkpoints.append((index + 1, stack[0]))
    for position, closers in reversed(checkpoints[-50:]):
        parsed = _try_json_loads(text[:position] + closers)
        if parsed is not _NO_MATCH:
            return parsed
    return _NO_MATCH


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
