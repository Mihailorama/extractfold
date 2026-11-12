"""Data-quality rules over extracted tables, with cross-table checks.

:func:`check_rules` runs rules over ``{table: rows}`` (or one list of rows, table
``"rows"``) and returns one check per rule, the same shape as
:func:`extractfold.quality.check_rows`:
``{"check", "type", "status", "message", "affected", "rule"}``, where ``status`` is
``passed``, ``failed``, ``warning`` (a failed rule with ``"severity": "warning"``) or
``error`` (the rule itself is broken), and ``affected`` lists ``{"table", "row",
"field"}``.

Rule types (``table`` defaults to the first table):

- ``not_empty``: ``fields``; ``unique``: ``fields`` (together); ``range``: ``field``,
  ``min`` / ``max``; ``pattern``: ``field``, ``regex``; ``allowed``: ``field``, ``values``;
  ``schema``: ``schema`` (JSON Schema of one row);
- ``expression``: ``expr`` over a row, e.g. ``qty * price == amount`` or
  ``date_from <= date_to`` (``field("Name with spaces")`` for other names); ``==`` on
  numbers allows ``tolerance`` (default 0.01); rows missing a used value are skipped;
- ``sum_equals``: ``parts`` ``{table, field, key?}`` and ``total`` ``{table, field, key?}``:
  per key (or overall) the parts add up to the total;
- ``reference``: ``field`` and ``target`` ``{table, field}``: every value exists there.

:func:`suggest_rules` asks an injected ``llm(prompt) -> str`` for rules of these types.
"""

from __future__ import annotations

import ast
import json
import operator
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from extractfold.engines._common import maybe_await
from extractfold.engines.base import validate_data
from extractfold.parsing import parse_llm_json
from extractfold.postprocess import is_empty

Tables = Mapping[str, Sequence[Mapping[str, Any]]]
RULE_TYPES = ("not_empty", "unique", "range", "pattern", "allowed", "schema", "expression",
              "sum_equals", "reference")


def check_rules(
    data: Tables | Sequence[Mapping[str, Any]], rules: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """One check per rule (see the module docstring)."""
    tables: dict[str, Sequence[Mapping[str, Any]]] = (
        dict(data) if isinstance(data, Mapping) else {"rows": list(data)}
    )
    default = next(iter(tables), "rows")
    return [_run(rule, tables, default) for rule in rules]


def _run(rule: Mapping[str, Any], tables: dict, default: str) -> dict[str, Any]:
    kind = str(rule.get("type", ""))
    name = str(rule.get("id") or rule.get("name") or kind)
    try:
        if kind not in _RULES:
            raise ValueError(f"unknown rule type {kind!r}")
        affected, detail = _RULES[kind](rule, tables, default)
    except Exception as exc:
        return {"check": name, "type": kind, "status": "error", "message": str(exc)[:300],
                "affected": [], "rule": dict(rule)}
    if not affected:
        status, message = "passed", detail or "ok"
    else:
        status = "warning" if rule.get("severity") == "warning" else "failed"
        message = str(rule.get("message") or detail or f"{len(affected)} rows fail")
    return {"check": name, "type": kind, "status": status, "message": message,
            "affected": affected, "rule": dict(rule)}


def _rows(tables: dict, table: str) -> Sequence[Mapping[str, Any]]:
    if table not in tables:
        raise ValueError(f"unknown table {table!r}")
    return tables[table]


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[\s ]", "", str(value or "")).replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _hits(table: str, indexes: Sequence[int], field: str | None) -> list[dict[str, Any]]:
    return [{"table": table, "row": i, **({"field": field} if field else {})} for i in indexes]


def _not_empty(rule, tables, default):
    table = rule.get("table", default)
    fields = rule.get("fields") or [rule["field"]]
    affected = [
        {"table": table, "row": i, "field": f}
        for i, row in enumerate(_rows(tables, table))
        for f in fields
        if is_empty(row.get(f))
    ]
    return affected, f"{len(affected)} empty values" if affected else ""


def _unique(rule, tables, default):
    table = rule.get("table", default)
    fields = rule.get("fields") or [rule["field"]]
    seen: dict[tuple, int] = {}
    affected = []
    for i, row in enumerate(_rows(tables, table)):
        key = tuple(str(row.get(f, "")).strip().casefold() for f in fields)
        if all(not part for part in key):
            continue
        if key in seen:
            affected.append({"table": table, "row": i, "field": ",".join(fields),
                             "duplicate_of": seen[key]})
        else:
            seen[key] = i
    return affected, f"{len(affected)} duplicates" if affected else ""


def _range(rule, tables, default):
    table, field = rule.get("table", default), rule["field"]
    low, high = rule.get("min"), rule.get("max")
    bad = []
    for i, row in enumerate(_rows(tables, table)):
        if is_empty(row.get(field)):
            continue
        value = _num(row.get(field))
        if value is None or (low is not None and value < low) or (
            high is not None and value > high
        ):
            bad.append(i)
    return _hits(table, bad, field), f"{len(bad)} values out of [{low}, {high}]" if bad else ""


def _pattern(rule, tables, default):
    table, field = rule.get("table", default), rule["field"]
    regex = re.compile(rule["regex"])
    bad = [i for i, row in enumerate(_rows(tables, table))
           if not is_empty(row.get(field)) and not regex.fullmatch(str(row.get(field)).strip())]
    return _hits(table, bad, field), f"{len(bad)} values do not match" if bad else ""


def _allowed(rule, tables, default):
    table, field = rule.get("table", default), rule["field"]
    allowed = {str(v).strip().casefold() for v in rule["values"]}
    bad = [i for i, row in enumerate(_rows(tables, table))
           if not is_empty(row.get(field)) and _fold(row.get(field)) not in allowed]
    return _hits(table, bad, field), f"{len(bad)} values not allowed" if bad else ""


def _schema(rule, tables, default):
    table = rule.get("table", default)
    affected = []
    for i, row in enumerate(_rows(tables, table)):
        for error in validate_data(row, rule["schema"]).errors:
            affected.append({"table": table, "row": i, "error": error})
    return affected, f"{len(affected)} schema errors" if affected else ""


def _expression(rule, tables, default):
    table = rule.get("table", default)
    tree = ast.parse(rule["expr"], mode="eval")
    tolerance = float(rule.get("tolerance", 0.01))
    bad = []
    for i, row in enumerate(_rows(tables, table)):
        try:
            ok = _eval(tree.body, row, tolerance)
        except _Skip:
            continue
        if not ok:
            bad.append(i)
    return _hits(table, bad, None), f"{len(bad)} rows break {rule['expr']}" if bad else ""


def _sum_equals(rule, tables, default):
    parts, total = rule["parts"], rule["total"]
    tolerance = float(rule.get("tolerance", 0.01))
    part_table, total_table = parts.get("table", default), total.get("table", default)
    sums: dict[Any, float] = {}
    for row in _rows(tables, part_table):
        value = _num(row.get(parts["field"]))
        if value is not None:
            group = _key(row, parts.get("key"))
            sums[group] = sums.get(group, 0.0) + value
    affected = []
    messages = []
    for i, row in enumerate(_rows(tables, total_table)):
        expected = _num(row.get(total["field"]))
        if expected is None:
            continue
        group = _key(row, total.get("key"))
        actual = sums.get(group, 0.0)
        if abs(actual - expected) > tolerance:
            affected.append({"table": total_table, "row": i, "field": total["field"],
                             "expected": expected, "sum": round(actual, 6)})
            messages.append(f"{total['field']}={expected:g} but parts sum to {actual:g}")
        if total.get("key") is None:
            break
    return affected, "; ".join(messages[:3])


def _fold(value: Any) -> str:
    return str(value).strip().casefold()


def _key(row: Mapping[str, Any], key: str | None) -> Any:
    return None if key is None else str(row.get(key, "")).strip().casefold()


def _reference(rule, tables, default):
    table, field = rule.get("table", default), rule["field"]
    target = rule["target"]
    known = {str(row.get(target["field"], "")).strip().casefold()
             for row in _rows(tables, target["table"])}
    bad = [i for i, row in enumerate(_rows(tables, table))
           if not is_empty(row.get(field)) and str(row.get(field)).strip().casefold() not in known]
    message = f"{len(bad)} values missing from {target['table']}.{target['field']}"
    return _hits(table, bad, field), message if bad else ""


_RULES: dict[str, Callable[..., tuple[list[dict[str, Any]], str]]] = {
    "not_empty": _not_empty, "unique": _unique, "range": _range, "pattern": _pattern,
    "allowed": _allowed, "schema": _schema, "expression": _expression,
    "sum_equals": _sum_equals, "reference": _reference,
}


class _Skip(Exception):  # noqa: N818 - control flow, not an error
    """A value the expression needs is empty: the row is not checked."""


_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv}
_COMPARE = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
            ast.GtE: operator.ge}


def _eval(node: ast.AST, row: Mapping[str, Any], tolerance: float) -> Any:
    """Arithmetic, comparisons and and/or/not over row fields; nothing else."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)):
        return node.value
    if isinstance(node, ast.Name):
        return _value(row, node.id)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        args = [_eval(arg, row, tolerance) for arg in node.args]
        if node.func.id == "field" and len(args) == 1:
            return _value(row, str(args[0]))
        if node.func.id == "abs" and len(args) == 1:
            return abs(args[0])
        if node.func.id == "round" and len(args) in (1, 2):
            return round(*args)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        return _BINARY[type(node.op)](_eval(node.left, row, tolerance),
                                      _eval(node.right, row, tolerance))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval(node.operand, row, tolerance)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval(node.operand, row, tolerance)
    if isinstance(node, ast.BoolOp):
        values = [_eval(v, row, tolerance) for v in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, row, tolerance)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval(comparator, row, tolerance)
            if isinstance(op, (ast.Eq, ast.NotEq)):
                equal = (abs(left - right) <= tolerance
                         if isinstance(left, float) and isinstance(right, float)
                         else left == right)
                ok = equal if isinstance(op, ast.Eq) else not equal
            elif type(op) in _COMPARE:
                ok = _COMPARE[type(op)](left, right)
            else:
                raise ValueError(f"operator {type(op).__name__} is not allowed")
            if not ok:
                return False
            left = right
        return True
    raise ValueError(f"{type(node).__name__} is not allowed in a rule expression")


def _value(row: Mapping[str, Any], name: str) -> Any:
    if name not in row:
        raise ValueError(f"unknown field {name!r}")
    value = row[name]
    if is_empty(value):
        raise _Skip
    number = _num(value)
    return number if number is not None else str(value).strip()


async def suggest_rules(
    data: Tables | Sequence[Mapping[str, Any]],
    *,
    llm: Callable[[str], Any],
    instructions: str = "",
    sample_rows: int = 20,
) -> list[dict[str, Any]]:
    """Rules an injected ``llm(prompt) -> str`` proposes from sample rows.

    Only rules of a known type whose tables and fields exist are kept; each gets
    ``"source": "llm"``.
    """
    tables = dict(data) if isinstance(data, Mapping) else {"rows": list(data)}
    samples = {name: list(rows)[:sample_rows] for name, rows in tables.items()}
    prompt = (
        "Propose data-quality rules for these tables: field checks and logical rules "
        "across rows and tables (a total equals the sum of its parts, references between "
        "tables). Return only a JSON array of rules. Rule types and their keys:\n"
        + __doc__.split("Rule types (``table`` defaults to the first table):")[1].split(
            ":func:`suggest_rules`")[0]
        + (f"\nContext:\n{instructions}\n" if instructions else "")
        + f"\nTables (sample rows):\n{json.dumps(samples, ensure_ascii=False, default=str)}"
    )
    try:
        proposed, _ = parse_llm_json(str(await maybe_await(llm(prompt))))
    except Exception:
        return []
    if isinstance(proposed, dict):
        proposed = proposed.get("rules", [])
    kept = []
    for rule in proposed if isinstance(proposed, list) else []:
        if isinstance(rule, dict) and rule.get("type") in RULE_TYPES:
            candidate = {**rule, "source": "llm"}
            if check_rules(tables, [candidate])[0]["status"] != "error":
                kept.append(candidate)
    return kept
