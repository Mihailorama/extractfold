"""Schema proposal, document-type classification and context shared across files.

Every function takes an injected ``llm(prompt) -> str`` (sync or async).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from extractfold.engines._common import maybe_await
from extractfold.parsing import parse_llm_json

_TYPES = {"string", "number", "integer", "boolean", "array", "object", "null"}


async def _ask(llm: Callable[[str], Any], prompt: str) -> Any:
    data, _ = parse_llm_json(str(await maybe_await(llm(prompt))))
    return data


async def propose_schema(
    *,
    llm: Callable[[str], Any],
    samples: Sequence[str] = (),
    attributes: Sequence[str] = (),
    relational: bool = False,
    instructions: str = "",
    sample_chars: int = 8000,
) -> dict[str, Any]:
    """Propose tables with a JSON Schema each, from sample documents and/or attribute names.

    Returns ``{"tables": [{"name", "description", "schema", "primary_key",
    "foreign_keys": [{"field", "table", "target_field"}]}]}``; one table unless
    *relational*. Every schema is an object schema whose properties have a JSON type;
    foreign keys must point at a field of another proposed table, others are dropped.
    """
    if not samples and not attributes:
        raise ValueError("propose_schema needs samples or attributes")
    shape = (
        "one or more linked tables (for example a document header and its line items), "
        "each with a primary key and foreign keys to the tables it belongs to"
        if relational else "exactly one table, one row per item the documents list"
    )
    parts = [
        "Design the tables to extract from documents like these: " + shape + ". Return only "
        'JSON: {"tables": [{"name", "description", "schema": JSON Schema of one row with '
        '"type": "object" and "properties" (each with "type" and "description"), '
        '"primary_key": field or null, "foreign_keys": [{"field", "table", "target_field"}]}]}.'
    ]
    if instructions:
        parts.append(f"Instructions:\n{instructions}")
    if attributes:
        parts.append("Attributes to cover:\n" + "\n".join(f"- {a}" for a in attributes))
    for number, sample in enumerate(samples, start=1):
        parts.append(f"Sample document {number}:\n{sample[:sample_chars]}")
    data = await _ask(llm, "\n\n".join(parts))
    tables = data.get("tables") if isinstance(data, dict) else None
    if not isinstance(tables, list):
        raise ValueError("the model did not return a list of tables")
    clean = [_table(t) for t in tables if isinstance(t, dict) and t.get("name")]
    clean = [t for t in clean if t["schema"]["properties"]]
    if not relational:
        clean = clean[:1]
    fields = {t["name"]: set(t["schema"]["properties"]) for t in clean}
    for table in clean:
        table["foreign_keys"] = [
            fk for fk in table["foreign_keys"]
            if fk["field"] in fields[table["name"]] and fk["target_field"] in fields.get(
                fk["table"], set()) and fk["table"] != table["name"]
        ]
        if table["primary_key"] not in fields[table["name"]]:
            table["primary_key"] = None
    if not clean:
        raise ValueError("the model proposed no usable table")
    return {"tables": clean}


def _table(raw: Mapping[str, Any]) -> dict[str, Any]:
    schema = _dict(raw.get("schema"))
    properties = _dict(schema.get("properties"))
    clean_props = {}
    for name, prop in properties.items():
        prop = dict(prop) if isinstance(prop, dict) else {}
        kinds = prop.get("type", "string")
        kinds = [k for k in (kinds if isinstance(kinds, list) else [kinds]) if k in _TYPES]
        prop["type"] = (kinds[0] if len(kinds) == 1 else kinds) if kinds else "string"
        clean_props[str(name)] = prop
    keys = _list(raw.get("foreign_keys"))
    return {
        "name": str(raw["name"]),
        "description": str(raw.get("description") or ""),
        "schema": {"type": "object", "properties": clean_props},
        "primary_key": raw.get("primary_key"),
        "foreign_keys": [
            {"field": str(k.get("field")), "table": str(k.get("table")),
             "target_field": str(k.get("target_field") or k.get("field"))}
            for k in keys if isinstance(k, dict)
        ],
    }


async def classify_document(
    text: str,
    profiles: Sequence[Mapping[str, Any]],
    *,
    llm: Callable[[str], Any],
    sample_chars: int = 6000,
) -> dict[str, Any]:
    """Name the document type and match it to one of *profiles* (``{"id", "description"}``).

    Returns ``{"document_type", "profile", "confidence", "rationale"}``; ``profile`` is
    a known profile id or ``None`` when none fits.
    """
    catalog = [{"id": p["id"], "description": p.get("description", "")} for p in profiles]
    prompt = (
        "Classify the document: name its type and pick the profile that fits it, or null "
        'when none does. Return only JSON: {"document_type", "profile": profile id or '
        'null, "confidence": 0-1, "rationale": short reason}.\n\n'
        f"Profiles:\n{json.dumps(catalog, ensure_ascii=False)}\n\n"
        f"Document (start):\n{text[:sample_chars]}"
    )
    data = await _ask(llm, prompt)
    data = _dict(data)
    ids = {str(p["id"]) for p in profiles}
    profile = data.get("profile")
    profile = str(profile) if profile is not None and str(profile) in ids else None
    try:
        confidence = min(max(float(data.get("confidence") or 0), 0.0), 1.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "document_type": str(data.get("document_type") or ""),
        "profile": profile,
        "confidence": confidence if profile else min(confidence, 0.5),
        "rationale": str(data.get("rationale") or ""),
    }


async def shared_context(
    files: Mapping[str, str],
    attributes: Sequence[str],
    *,
    llm: Callable[[str], Any],
    file_chars: int = 6000,
) -> dict[str, Any]:
    """Attribute defaults stated once for several files (a cover letter, a contract).

    Returns ``{"defaults": {attribute: value}, "sources": {attribute: file name},
    "context": prompt text}``. Only *attributes* found with a non-empty value and a
    known source file are kept. ``context`` tells an extraction prompt to use them when
    a document does not give its own value, and never to extract rows from them.
    """
    parts = [
        "These files were uploaded together. Find values of the attributes that apply to "
        "all of them (stated once, e.g. in a cover letter or contract). Return only JSON: "
        '{"defaults": {attribute: value}, "sources": {attribute: file name}}. Leave out '
        "attributes the files do not state.",
        "Attributes:\n" + "\n".join(f"- {a}" for a in attributes),
    ]
    for name, text in files.items():
        parts.append(f"File {name}:\n{text[:file_chars]}")
    data = await _ask(llm, "\n\n".join(parts))
    data = _dict(data)
    raw_defaults = _dict(data.get("defaults"))
    raw_sources = _dict(data.get("sources"))
    defaults, sources = {}, {}
    for name in attributes:
        value = raw_defaults.get(name)
        source = raw_sources.get(name)
        if value in (None, "") or source not in files:
            continue
        defaults[name], sources[name] = value, source
    context = ""
    if defaults:
        lines = "\n".join(f"- {k}: {v}" for k, v in defaults.items())
        context = (
            "DEFAULT VALUES from companion files. Use a default only when the document "
            "does not give its own value for that attribute; never extract rows from "
            f"them.\n{lines}"
        )
    return {"defaults": defaults, "sources": sources, "context": context}



def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
