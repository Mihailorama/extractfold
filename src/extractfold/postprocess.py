"""Row post-processing steps, each returning ``(rows, record)``.

``record`` is ``{"step", "changed", "changes"}``: what the step did, one entry per
changed, merged or dropped row. Steps never edit the rows they get; they return new
lists. Model calls go through an injected ``llm(prompt) -> str`` (sync or async).
"""

from __future__ import annotations

import difflib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from extractfold.engines._common import maybe_await
from extractfold.parsing import parse_llm_json

Rows = list[dict[str, Any]]
_EMPTY = {"", "null", "none", "n/a", "-", "no information found"}


def is_empty(value: Any) -> bool:
    """None, blank text or a placeholder such as ``N/A``."""
    return value is None or str(value).strip().lower() in _EMPTY


def _record(step: str, changes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"step": step, "changed": len(changes), "changes": changes}


def drop_rows_missing(
    rows: Sequence[Mapping[str, Any]], mandatory: Sequence[str]
) -> tuple[Rows, dict[str, Any]]:
    """Drop rows where any *mandatory* field is empty."""
    kept: Rows = []
    changes = []
    for index, row in enumerate(rows):
        missing = [name for name in mandatory if is_empty(row.get(name))]
        if missing:
            changes.append({"row": index, "action": "dropped", "missing": missing})
        else:
            kept.append(dict(row))
    return kept, _record("drop_rows_missing", changes)


async def merge_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    key: Sequence[str] | None = None,
    llm: Callable[[str], Any] | None = None,
    instructions: str = "",
) -> tuple[Rows, dict[str, Any]]:
    """Merge duplicate or partial rows into one row per group.

    Groups are rows with equal *key* fields (rows with an empty key stay alone); without
    *key* all rows form one group. Without *llm* a group merges field by field: the first
    non-empty value wins. With *llm* each group of two or more rows goes to one call that
    returns the merged row; an unusable answer falls back to the field-by-field merge.
    """
    groups: dict[Any, list[int]] = {}
    for index, row in enumerate(rows):
        if key is None:
            group: Any = ()
        elif any(is_empty(row.get(name)) for name in key):
            group = ("__alone__", index)
        else:
            group = tuple(_norm(row.get(name)) for name in key)
        groups.setdefault(group, []).append(index)

    merged: Rows = []
    changes = []
    for members in groups.values():
        part = [dict(rows[i]) for i in members]
        if len(part) == 1:
            merged.append(part[0])
            continue
        row, how = _merge_fields(part), "fields"
        if llm is not None:
            answer = await _merge_with_llm(part, llm, instructions)
            if answer is not None:
                row, how = answer, "llm"
        merged.append(row)
        changes.append({"rows": members, "action": "merged", "into": len(merged) - 1,
                        "method": how})
    return merged, _record("merge_rows", changes)


def _merge_fields(part: Rows) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in part:
        for name, value in row.items():
            if name not in out or (is_empty(out[name]) and not is_empty(value)):
                out[name] = value
    return out


async def _merge_with_llm(
    part: Rows, llm: Callable[[str], Any], instructions: str
) -> dict[str, Any] | None:
    fields = list(_merge_fields(part))
    prompt = (
        "Merge these rows, which describe the same item, into one row. Keep every field "
        "name exactly as given, one value per field, no repeats, lose no information. If "
        "the rows describe different items, keep the item of the first row. Return only "
        "the JSON object.\n\n"
        + (f"Instructions:\n{instructions}\n\n" if instructions else "")
        + f"Rows:\n{json.dumps(part, ensure_ascii=False, default=str)}"
    )
    answer = str(await maybe_await(llm(prompt)))  # call errors propagate
    try:
        data, _ = parse_llm_json(answer)
    except Exception:
        return None
    if isinstance(data, list) and len(data) == 1:
        data = data[0]
    if not isinstance(data, dict) or not set(data) <= set(fields):
        return None
    return {name: data.get(name, part[0].get(name)) for name in fields}


async def compute_fields(
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[Mapping[str, Any]],
    *,
    llm: Callable[[str], Any] | None = None,
    instructions: str = "",
) -> tuple[Rows, dict[str, Any]]:
    """Fill computed fields.

    Each field is ``{"name", "description"?, "type"?, "samples"?, "compute"?}``. A
    ``compute`` callable gets the row and returns the value; the other fields of a row are
    computed together by one *llm* call that returns a JSON object of their values. A
    value that cannot be computed is ``None``.
    """
    local = [f for f in fields if callable(f.get("compute"))]
    remote = [f for f in fields if not callable(f.get("compute"))]
    if remote and llm is None:
        raise ValueError("compute_fields needs llm= for fields without a compute callable")
    out: Rows = []
    changes = []
    for index, source in enumerate(rows):
        row = dict(source)
        values: dict[str, Any] = {}
        for spec in local:
            try:
                values[spec["name"]] = spec["compute"](row)
            except Exception:
                values[spec["name"]] = None
        if remote and llm is not None:
            values.update(await _compute_with_llm(row, remote, llm, instructions))
        for name, value in values.items():
            if row.get(name) != value:
                changes.append({"row": index, "field": name, "before": row.get(name),
                                "after": value})
            row[name] = value
        out.append(row)
    return out, _record("compute_fields", changes)


async def _compute_with_llm(
    row: dict[str, Any],
    specs: Sequence[Mapping[str, Any]],
    llm: Callable[[str], Any],
    instructions: str,
) -> dict[str, Any]:
    described = []
    for spec in specs:
        line = f"- {spec['name']} ({spec.get('type', 'text')})"
        if spec.get("description"):
            line += f": {spec['description']}"
        if spec.get("samples"):
            line += f". Examples: {'; '.join(str(s) for s in spec['samples'])}"
        described.append(line)
    prompt = (
        "Compute the fields below from the row. Return only a JSON object with exactly "
        "these field names; use null when a value cannot be computed.\n\n"
        + (f"Dataset description:\n{instructions}\n\n" if instructions else "")
        + "Fields:\n" + "\n".join(described)
        + f"\n\nRow:\n{json.dumps(row, ensure_ascii=False, default=str)}"
    )
    names = [spec["name"] for spec in specs]
    answer = str(await maybe_await(llm(prompt)))  # call errors propagate
    try:
        data, _ = parse_llm_json(answer)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {name: data.get(name) for name in names}


async def map_to_reference(
    rows: Sequence[Mapping[str, Any]],
    field: str,
    reference: Sequence[Any],
    *,
    value_key: str | None = None,
    threshold: float = 0.8,
    llm: Callable[[str], Any] | None = None,
    other: str | None = None,
) -> tuple[Rows, dict[str, Any]]:
    """Replace *field* values with entries of a reference list (classifier).

    *reference* holds strings, or dicts whose *value_key* is the canonical value. A value
    is matched exactly (case and spacing ignored), then by string similarity at
    *threshold*; still unmatched distinct values go to one *llm* call that picks from the
    list. A value nothing matches becomes *other* when given, else stays as is.
    """
    canon = [str(entry[value_key] if value_key else entry) for entry in reference]
    exact = {_norm(value): value for value in canon}
    resolved: dict[str, tuple[str | None, str]] = {}
    pending: list[str] = []
    for row in rows:
        value = row.get(field)
        if is_empty(value) or str(value) in resolved:
            continue
        text = str(value)
        if _norm(text) in exact:
            resolved[text] = (exact[_norm(text)], "exact")
            continue
        best = difflib.get_close_matches(_norm(text), list(exact), n=1, cutoff=threshold)
        if best:
            resolved[text] = (exact[best[0]], "similar")
        else:
            resolved[text] = (None, "")
            pending.append(text)
    if pending and llm is not None:
        for text, choice in (await _map_with_llm(pending, canon, llm)).items():
            resolved[text] = (choice, "llm")

    out: Rows = []
    changes = []
    for index, source in enumerate(rows):
        row = dict(source)
        value = row.get(field)
        if not is_empty(value):
            target, how = resolved.get(str(value), (None, ""))
            if target is None and other is not None:
                target, how = other, "other"
            if target is not None and target != value:
                row[field] = target
                changes.append({"row": index, "field": field, "before": value,
                                "after": target, "method": how})
        out.append(row)
    return out, _record("map_to_reference", changes)


async def _map_with_llm(
    values: list[str], canon: list[str], llm: Callable[[str], Any]
) -> dict[str, str]:
    prompt = (
        "Match each value to the entry of the reference list with the same meaning "
        "(spelling variants, abbreviations, synonyms). Return only a JSON object mapping "
        "every value to an entry copied exactly from the list, or null when none fits.\n\n"
        f"Reference list:\n{json.dumps(canon, ensure_ascii=False)}\n\n"
        f"Values:\n{json.dumps(values, ensure_ascii=False)}"
    )
    answer = str(await maybe_await(llm(prompt)))  # call errors propagate
    try:
        data, _ = parse_llm_json(answer)
    except Exception:
        return {}
    allowed = set(canon)
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if k in values and v in allowed}


def _norm(value: Any) -> str:
    return " ".join(str(value).casefold().split())
