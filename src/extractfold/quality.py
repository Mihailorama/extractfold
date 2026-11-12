"""Response quality checks for extracted rows.

Each check is a plain dict ``{"check", "status", "message"}`` with status ``passed``,
``warning`` or ``failed``, so callers can show every check the same way.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

_EMPTY = {"", "null", "none", "n/a", "-"}


def check_rows(
    rows: Sequence[Any],
    *,
    columns: Sequence[str] | None = None,
    expected_rows: int | None = None,
    tolerance: float = 0.5,
) -> list[dict[str, str]]:
    """Check one answer's rows.

    - ``row_count`` (only with *expected_rows*): fewer than ``1 - tolerance`` of the
      expected rows fails, more than ``1 + tolerance`` warns.
    - ``schema_compliance`` (only with *columns*): the first row carries under half of the
      columns fails, some missing warns (names compared case-insensitively).
    - ``suspicious_patterns``: every value empty, under 10% filled, or every row identical
      fails; a last row much emptier than the rest (cut off) warns.
    """
    dict_rows = [row for row in rows if isinstance(row, dict)]
    checks: list[dict[str, str]] = []
    if expected_rows is not None:
        checks.append(_row_count(len(rows), expected_rows, tolerance))
    if columns:
        checks.append(_schema_compliance(dict_rows, columns))
    checks.append(_suspicious_patterns(dict_rows))
    return checks


def _check(name: str, status: str, message: str = "") -> dict[str, str]:
    return {"check": name, "status": status, "message": message}


def _row_count(actual: int, expected: int, tolerance: float) -> dict[str, str]:
    if expected <= 0:
        return _check("row_count", "passed", f"{actual} rows")
    ratio = actual / expected
    message = f"got {actual} rows, expected ~{expected}"
    if ratio < 1 - tolerance:
        return _check("row_count", "failed", message)
    if ratio > 1 + tolerance:
        return _check("row_count", "warning", message)
    return _check("row_count", "passed", message)


def _schema_compliance(rows: list[dict[str, Any]], columns: Sequence[str]) -> dict[str, str]:
    if not rows:
        return _check("schema_compliance", "passed", "no rows")
    present = {str(key).strip().lower() for key in rows[0]}
    wanted = {str(name).strip().lower() for name in columns}
    missing = sorted(wanted - present)
    coverage = 1 - len(missing) / len(wanted)
    if not missing:
        return _check("schema_compliance", "passed", "all columns present")
    message = f"{coverage:.0%} of columns present, missing: {', '.join(missing[:5])}"
    return _check("schema_compliance", "failed" if coverage < 0.5 else "warning", message)


def _filled(value: Any) -> bool:
    return value is not None and str(value).strip().lower() not in _EMPTY


def _suspicious_patterns(rows: list[dict[str, Any]]) -> dict[str, str]:
    if not rows:
        return _check("suspicious_patterns", "passed", "no rows")
    issues: list[str] = []
    values = [value for row in rows for value in row.values()]
    filled = sum(1 for value in values if _filled(value))
    if values and filled == 0:
        issues.append("all values empty")
    elif values and filled / len(values) < 0.1:
        issues.append(f"only {filled}/{len(values)} values filled")
    if len(rows) > 2:
        first = json.dumps(rows[0], sort_keys=True, default=str)
        if all(json.dumps(row, sort_keys=True, default=str) == first for row in rows[1:]):
            issues.append(f"all {len(rows)} rows identical")
    if issues:
        return _check("suspicious_patterns", "failed", "; ".join(issues))
    if len(rows) >= 3:
        counts = [sum(1 for v in row.values() if v is not None and str(v).strip()) for row in rows]
        average = sum(counts[:-1]) / (len(counts) - 1)
        if average > 0 and counts[-1] / average < 0.3:
            message = f"last row looks cut off ({counts[-1]} vs ~{average:.0f} values)"
            return _check("suspicious_patterns", "warning", message)
    return _check("suspicious_patterns", "passed", "")
