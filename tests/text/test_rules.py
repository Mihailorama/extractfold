from __future__ import annotations

import json

import pytest

from extractfold.rules import check_rules, suggest_rules

ACTS = [{"id": "A1", "total": "1 500,00", "contract": "C1"},
        {"id": "A2", "total": 100, "contract": "C9"}]
LINES = [
    {"act": "A1", "name": "Bricks", "qty": 2, "price": 500, "amount": 1000},
    {"act": "A1", "name": "Sand", "qty": 1, "price": 500, "amount": 500},
    {"act": "A2", "name": "Paint", "qty": 3, "price": 10, "amount": 40},
    {"act": "A2", "name": "", "qty": None, "price": 10, "amount": 10},
]
CONTRACTS = [{"number": "C1"}]
TABLES = {"acts": ACTS, "lines": LINES, "contracts": CONTRACTS}


def _by_check(checks):
    return {c["check"]: c for c in checks}


def test_field_rules() -> None:
    checks = _by_check(check_rules(TABLES, [
        {"id": "names", "type": "not_empty", "table": "lines", "fields": ["name"]},
        {"id": "ids", "type": "unique", "table": "acts", "fields": ["id"]},
        {"id": "price", "type": "range", "table": "lines", "field": "price", "min": 0,
         "max": 400, "severity": "warning"},
        {"id": "act_id", "type": "pattern", "table": "acts", "field": "id", "regex": r"A\d+"},
        {"id": "units", "type": "allowed", "table": "lines", "field": "name",
         "values": ["bricks", "sand", "paint"]},
        {"id": "row_schema", "type": "schema", "table": "lines",
         "schema": {"type": "object", "properties": {"qty": {"type": "number"}}}},
    ]))

    assert checks["names"]["status"] == "failed"
    assert checks["names"]["affected"] == [{"table": "lines", "row": 3, "field": "name"}]
    assert checks["ids"]["status"] == "passed"
    assert checks["price"]["status"] == "warning"
    assert [a["row"] for a in checks["price"]["affected"]] == [0, 1]
    assert checks["act_id"]["status"] == "passed" and checks["units"]["status"] == "passed"
    assert checks["row_schema"]["affected"][0]["row"] == 3
    assert set(checks["names"]) == {"check", "type", "status", "message", "affected", "rule"}


def test_expression_rule_skips_rows_with_missing_values() -> None:
    [check] = check_rules({"lines": LINES}, [
        {"type": "expression", "expr": "qty * price == amount"}
    ])

    assert check["status"] == "failed"
    assert [a["row"] for a in check["affected"]] == [2]
    [ok] = check_rules([{"Дата с": "1", "Дата по": "2"}],
                       [{"type": "expression", "expr": 'field("Дата с") <= field("Дата по")'}])
    assert ok["status"] == "passed"


def test_expression_rule_refuses_code() -> None:
    [check] = check_rules(LINES, [{"type": "expression", "expr": "__import__('os')"}])
    assert check["status"] == "error"


def test_cross_table_sum_and_reference() -> None:
    checks = check_rules(TABLES, [
        {"id": "act_totals", "type": "sum_equals",
         "parts": {"table": "lines", "field": "amount", "key": "act"},
         "total": {"table": "acts", "field": "total", "key": "id"}},
        {"id": "contracts", "type": "reference", "table": "acts", "field": "contract",
         "target": {"table": "contracts", "field": "number"}},
        {"id": "grand", "type": "sum_equals", "parts": {"table": "lines", "field": "amount"},
         "total": {"table": "acts", "field": "total"}},
    ])
    totals, refs, grand = checks

    assert totals["status"] == "failed"
    assert totals["affected"] == [{"table": "acts", "row": 1, "field": "total",
                                   "expected": 100.0, "sum": 50.0}]
    assert refs["affected"] == [{"table": "acts", "row": 1, "field": "contract"}]
    assert grand["status"] == "failed"  # first total row (1500) vs all parts (1550)


def test_unknown_rule_type_is_an_error_not_an_exception() -> None:
    [check] = check_rules(LINES, [{"type": "telepathy"}])
    assert check["status"] == "error" and "telepathy" in check["message"]


@pytest.mark.asyncio
async def test_suggest_rules_keeps_only_valid_rules() -> None:
    prompts: list[str] = []

    async def llm(prompt: str) -> str:
        prompts.append(prompt)
        return json.dumps([
            {"type": "expression", "table": "lines", "expr": "qty * price == amount"},
            {"type": "not_empty", "table": "nope", "fields": ["x"]},
            {"type": "magic"},
        ])

    rules = await suggest_rules(TABLES, llm=llm)

    assert rules == [{"type": "expression", "table": "lines", "expr": "qty * price == amount",
                      "source": "llm"}]
    assert "sum_equals" in prompts[0] and '"Bricks"' in prompts[0]
