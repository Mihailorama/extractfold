"""Schema-less entity extraction."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

from extractfold.chunking import chunk_text
from extractfold.engines._common import maybe_await
from extractfold.parsing import parse_llm_json


async def extract_entities(
    text: str,
    *,
    llm: Callable[[str], Any],
    types: Sequence[str] | None = None,
    instructions: str = "",
    max_chars: int = 60_000,
) -> list[dict[str, Any]]:
    """Entities ``{"type", "value", "attributes"}`` found in *text*, without a schema.

    *types* narrows the entity types (any type otherwise). Long text is read in chunks of
    *max_chars*; an entity found in several chunks (same type and value, case and spacing
    ignored) is returned once, attributes merged (first value wins), with the ``chunks``
    it came from. A chunk whose answer cannot be parsed adds nothing.
    """
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for chunk in chunk_text(text, max_chars=max_chars) if text.strip() else []:
        prompt = (
            "Extract the named entities from the text: organisations, people, documents, "
            "products, places, amounts, dates and the like. Return only a JSON array of "
            '{"type": entity type, "value": the entity as written, "attributes": {other '
            "facts the text states about it}}. Do not invent entities or facts.\n\n"
            + (f"Entity types to extract: {', '.join(types)}\n\n" if types else "")
            + (f"Instructions:\n{instructions}\n\n" if instructions else "")
            + f"Text:\n{chunk.text}"
        )
        answer = str(await maybe_await(llm(prompt)))  # call errors propagate
        try:
            data, _ = parse_llm_json(answer)
        except Exception:
            continue
        if isinstance(data, dict):
            data = data.get("entities", [])
        for item in data if isinstance(data, list) else []:
            entity = _entity(item)
            if entity is None or (types and entity["type"] not in types):
                continue
            key = (_norm(entity["type"]), _norm(entity["value"]))
            if key not in found:
                found[key] = {**entity, "chunks": [chunk.index]}
                continue
            known = found[key]
            for name, value in entity["attributes"].items():
                known["attributes"].setdefault(name, value)
            if chunk.index not in known["chunks"]:
                known["chunks"].append(chunk.index)
    return list(found.values())


def _entity(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict) or not item.get("type") or item.get("value") in (None, ""):
        return None
    attributes = item.get("attributes")
    value = item["value"]
    return {
        "type": str(item["type"]),
        "value": value if isinstance(value, (str, int, float)) else json.dumps(value),
        "attributes": dict(attributes) if isinstance(attributes, dict) else {},
    }


def _norm(value: Any) -> str:
    return " ".join(str(value).casefold().split())
