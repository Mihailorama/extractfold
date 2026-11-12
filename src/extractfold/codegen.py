"""Table extraction by generated code, run only in a caller-supplied sandbox.

Four model roles work in turn: a *scout* describes the tables, a *worker* writes a
pandas function that turns them into rows, a *validator* checks the rows (JSON Schema
and :func:`extractfold.quality.check_rows`) and sends failures back to the worker, and
an optional *schema enricher* proposes fields the tables hold but the schema lacks.

extractfold never executes generated code itself. The ``sandbox`` callable must run it
isolated — no host process ``exec``, no network, no file system, with time and memory
limits — and is called as ``sandbox(code, inputs, timeout_s=, memory_mb=)``. The code
defines ``extract(tables)`` where ``tables`` is ``{name: list of rows (lists of cells)}``;
the sandbox returns ``{"rows": [...]}`` or ``{"error": "..."}``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from extractfold.engines._common import maybe_await
from extractfold.engines.base import JsonSchema, validate_data
from extractfold.parsing import parse_llm_json
from extractfold.quality import check_rows

Grid = Sequence[Sequence[Any]]


async def extract_tables_with_code(
    tables: Mapping[str, Grid],
    schema: JsonSchema,
    *,
    llm: Callable[[str], Any],
    sandbox: Callable[..., Any] | None,
    instructions: str = "",
    max_attempts: int = 3,
    timeout_s: float = 30.0,
    memory_mb: int = 512,
    enrich_schema: bool = False,
    preview_rows: int = 30,
) -> dict[str, Any]:
    """Rows of *tables* for the row *schema*, extracted by generated pandas code.

    Raises ``ValueError`` without a *sandbox*. Returns ``{"rows", "valid", "plan",
    "code", "attempts", "schema_suggestions"}``; ``attempts`` records each run's error or
    failed checks.
    """
    if sandbox is None:
        raise ValueError("code-generation extraction refuses to run without a sandbox")
    preview = {name: [list(r) for r in rows[:preview_rows]] for name, rows in tables.items()}
    shapes = {name: {"rows": len(rows), "preview": preview[name]} for name, rows in tables.items()}
    common = (
        (f"Instructions:\n{instructions}\n\n" if instructions else "")
        + f"Row JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
        + f"Tables:\n{json.dumps(shapes, ensure_ascii=False, default=str)}"
    )
    plan = await _json(llm, (
        "You are the scout. Describe how to turn these tables into rows of the schema: "
        "which table and header rows hold the items, which column feeds which field, rows "
        'to skip (titles, totals, section headers). Return only JSON: {"tables": [...], '
        '"header_rows": {...}, "columns": {field: column}, "skip": [...], "notes": "..."}.'
        f"\n\n{common}"
    ))
    columns = list((schema.get("properties") or {}) if isinstance(schema, dict) else [])
    attempts: list[dict[str, Any]] = []
    rows: list[Any] = []
    code = ""
    feedback = ""
    for _ in range(max(max_attempts, 1)):
        answer = await maybe_await(llm(
            "You are the worker. Write Python that defines `def extract(tables):` returning "
            "a list of dicts that follow the schema. `tables` maps a table name to a list of "
            "rows (lists of cells). You may import pandas, re, datetime, decimal; nothing "
            "else, no I/O. Return only the code in one ```python block.\n\n"
            f"Plan:\n{json.dumps(plan, ensure_ascii=False)}\n\n{common}"
            + (f"\n\nYour previous code failed:\n{feedback}\nFix it." if feedback else "")
        ))
        code = _code(str(answer))
        result = await maybe_await(sandbox(code, {"tables": {k: [list(r) for r in v]
                                                              for k, v in tables.items()}},
                                           timeout_s=timeout_s, memory_mb=memory_mb))
        result = result if isinstance(result, dict) else {"error": "sandbox returned no dict"}
        if result.get("error") or not isinstance(result.get("rows"), list):
            feedback = str(result.get("error") or "no rows list returned")[:2000]
            attempts.append({"code": code, "error": feedback})
            continue
        rows = result["rows"]
        problems = validate_data({"rows": rows}, {"type": "object", "properties": {
            "rows": {"type": "array", "items": schema}}}).errors[:20]
        checks = check_rows(rows, columns=columns)
        failed = [c for c in checks if c["status"] == "failed"]
        attempts.append({"code": code, "rows": len(rows), "schema_errors": problems,
                         "checks": checks})
        if not problems and not failed:
            break
        feedback = "\n".join(problems + [f"{c['check']}: {c['message']}" for c in failed])
    last = attempts[-1]
    valid = "error" not in last and not last["schema_errors"] and not any(
        c["status"] == "failed" for c in last["checks"])
    suggestions: list[Any] = []
    if enrich_schema:
        proposed = await _json(llm, (
            "You are the schema enricher. List fields these tables hold that the schema "
            'lacks. Return only JSON: [{"name", "type", "description"}].\n\n' + common
        ))
        suggestions = [s for s in proposed if isinstance(s, dict) and s.get("name")
                       and s["name"] not in columns] if isinstance(proposed, list) else []
    return {"rows": rows if "error" not in last else [], "valid": valid, "plan": plan,
            "code": code, "attempts": attempts, "schema_suggestions": suggestions}


async def _json(llm: Callable[[str], Any], prompt: str) -> Any:
    answer = str(await maybe_await(llm(prompt)))  # call errors propagate
    try:
        data, _ = parse_llm_json(answer)
    except Exception:
        return {}
    return data


def _code(answer: str) -> str:
    match = re.search(r"```(?:python)?\s*\n(.*?)```", answer, re.DOTALL)
    return (match.group(1) if match else answer).strip()
