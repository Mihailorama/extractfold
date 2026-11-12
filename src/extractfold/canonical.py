"""Canonical document profile: header fields, sections, line items, quality metrics."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from extractfold.chunking import chunk_text
from extractfold.engines._common import maybe_await
from extractfold.parsing import parse_llm_json
from extractfold.postprocess import is_empty
from extractfold.quality import check_rows

_PROMPT = (
    "Read this part of a document and return only JSON:\n"
    '{"document_type": short type name,\n'
    ' "proposed_schema": {"header": JSON Schema of the document-level fields, '
    '"line_item": JSON Schema of one line item or null},\n'
    ' "header_fields": {field: value} (numbers as numbers, dates YYYY-MM-DD),\n'
    ' "sections": [{"title", "summary"}],\n'
    ' "line_items": [{field: value}] for every table row or listed item}.\n'
    "Copy values as written; do not invent values; use null when absent."
)


async def canonical_extract(
    text: str,
    *,
    llm: Callable[[str], Any],
    schema: Mapping[str, Any] | None = None,
    max_chars: int = 60_000,
    on_progress: Callable[[int, int], Any] | None = None,
) -> dict[str, Any]:
    """Extract *text* into a canonical profile.

    *schema* (``{"header": ..., "line_item": ...}`` JSON Schemas) fixes the fields; without
    it the model proposes them from the first chunk. Long text is read in chunks of
    *max_chars*: header fields keep the first non-empty value, sections and line items
    are concatenated in order. *on_progress(done, total)* is called after each chunk.

    Returns ``{"document_type", "proposed_schema", "header_fields", "sections",
    "line_items", "quality", "errors"}``; ``quality`` holds fill rates, counts and the
    line-item checks of :func:`extractfold.quality.check_rows`; ``errors`` lists chunks
    whose answer could not be used.
    """
    chunks = chunk_text(text, max_chars=max_chars) if text.strip() else []
    profile: dict[str, Any] = {
        "document_type": "",
        "proposed_schema": dict(schema) if schema else {},
        "header_fields": {},
        "sections": [],
        "line_items": [],
        "errors": [],
    }
    for chunk in chunks:
        prompt = _PROMPT
        if profile["proposed_schema"]:
            prompt += "\nUse exactly these fields:\n" + json.dumps(
                profile["proposed_schema"], ensure_ascii=False)
        if len(chunks) > 1:
            prompt += f"\nThis is part {chunk.index + 1} of {len(chunks)}."
        try:
            answer = await maybe_await(llm(f"{prompt}\n\nDocument:\n{chunk.text}"))
            data, _ = parse_llm_json(str(answer))
            if not isinstance(data, dict):
                raise ValueError("answer is not an object")
        except Exception as exc:
            profile["errors"].append({"chunk": chunk.index, "error": str(exc)[:300]})
        else:
            _merge(profile, data)
        if on_progress is not None:
            await maybe_await(on_progress(chunk.index + 1, len(chunks)))
    profile["quality"] = _quality(profile)
    return profile


def _merge(profile: dict[str, Any], data: Mapping[str, Any]) -> None:
    if not profile["document_type"] and data.get("document_type"):
        profile["document_type"] = str(data["document_type"])
    proposed = data.get("proposed_schema")
    if not profile["proposed_schema"] and isinstance(proposed, dict):
        profile["proposed_schema"] = proposed
    header = data.get("header_fields")
    for name, value in (header.items() if isinstance(header, dict) else []):
        if is_empty(profile["header_fields"].get(name)):
            profile["header_fields"][name] = value
    for key in ("sections", "line_items"):
        items = data.get(key)
        profile[key].extend(i for i in (items if isinstance(items, list) else [])
                            if isinstance(i, dict))


def _fill(values: list[Any]) -> float:
    return round(sum(not is_empty(v) for v in values) / len(values), 3) if values else 0.0


def _quality(profile: Mapping[str, Any]) -> dict[str, Any]:
    header = profile["header_fields"]
    items = profile["line_items"]
    item_schema = (profile["proposed_schema"] or {}).get("line_item") or {}
    columns = list(item_schema.get("properties") or {}) if isinstance(item_schema, dict) else []
    columns = columns or sorted({k for item in items for k in item})
    return {
        "header_fields": len(header),
        "header_fill": _fill(list(header.values())),
        "sections": len(profile["sections"]),
        "line_items": len(items),
        "line_item_fill": _fill([item.get(c) for item in items for c in columns]),
        "checks": check_rows(items, columns=columns) if items else [],
        "failed_chunks": len(profile["errors"]),
    }
