from __future__ import annotations

from extractfold.quality import check_rows


def _status(checks: list[dict], name: str) -> str:
    return next(c["status"] for c in checks if c["check"] == name)


def test_check_rows_passes_a_plausible_answer() -> None:
    rows = [{"name": f"item {i}", "qty": i} for i in range(10)]
    checks = check_rows(rows, columns=["name", "qty"], expected_rows=10)

    assert [c["check"] for c in checks] == ["row_count", "schema_compliance", "suspicious_patterns"]
    assert {c["status"] for c in checks} == {"passed"}


def test_check_rows_fails_short_answers_and_warns_on_long_ones() -> None:
    rows = [{"name": "a"}, {"name": "b"}]

    assert _status(check_rows(rows, expected_rows=10), "row_count") == "failed"
    assert _status(check_rows(rows * 4, expected_rows=4), "row_count") == "warning"
    assert _status(check_rows(rows, expected_rows=3), "row_count") == "passed"
    assert [c["check"] for c in check_rows(rows)] == ["suspicious_patterns"]


def test_check_rows_schema_compliance() -> None:
    rows = [{"name": "a", "qty": 1}]

    assert _status(check_rows(rows, columns=["Name", "qty"]), "schema_compliance") == "passed"
    assert _status(check_rows(rows, columns=["name", "qty", "price"]), "schema_compliance") == (
        "warning"
    )
    assert _status(check_rows(rows, columns=["name", "x", "y"]), "schema_compliance") == "failed"


def test_check_rows_suspicious_patterns() -> None:
    empty = [{"name": "", "qty": None}, {"name": "-", "qty": "N/A"}]
    same = [{"name": "a"}] * 3
    cut = [{"a": 1, "b": 2, "c": 3, "d": 4}] + [{"a": i, "b": i, "c": i, "d": i} for i in range(3)]
    cut.append({"a": 9, "b": None, "c": None, "d": None})

    assert _status(check_rows(empty), "suspicious_patterns") == "failed"
    assert _status(check_rows(same), "suspicious_patterns") == "failed"
    assert _status(check_rows(cut), "suspicious_patterns") == "warning"
    assert _status(check_rows([]), "suspicious_patterns") == "passed"
