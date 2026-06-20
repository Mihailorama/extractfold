"""Metrics for schema-guided structured extraction."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from extractfold.engines.base import validate_data


def field_accuracy(predicted: dict[str, Any], gold: dict[str, Any]) -> float:
    """Share of gold fields exactly matched after normalization."""
    if not gold:
        return 1.0 if not predicted else 0.0
    matches = 0
    for key, gold_value in gold.items():
        if key in predicted and _values_match(predicted[key], gold_value):
            matches += 1
    return matches / len(gold)


def schema_compliance(predicted: dict[str, Any], schema: dict[str, Any]) -> float:
    """Return 1.0 when predicted data validates against schema, else 0.0."""
    return 1.0 if validate_data(predicted, schema).valid else 0.0


def per_field_prf(predicted: dict[str, Any], gold: dict[str, Any]) -> dict[str, float]:
    """Per-field precision, recall, and F1 based on matching field values."""
    if not predicted and not gold:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    true_positive = sum(
        1
        for key, value in predicted.items()
        if key in gold and _values_match(value, gold[key])
    )
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def hallucination_rate(predicted: dict[str, Any], gold: dict[str, Any]) -> float:
    """Fraction of predicted top-level fields not present in gold/source support."""
    if not predicted:
        return 0.0
    extras = set(predicted) - set(gold)
    return len(extras) / len(predicted)


def type_correctness(predicted: dict[str, Any], schema: dict[str, Any]) -> float:
    """Share of present schema fields whose value has the expected JSON type."""
    properties = schema.get("properties", {})
    if not isinstance(properties, dict) or not properties:
        return 1.0
    checked = 0
    correct = 0
    for key, field_schema in properties.items():
        if key not in predicted or not isinstance(field_schema, dict):
            continue
        checked += 1
        if _matches_type(predicted[key], field_schema.get("type")):
            correct += 1
    return correct / checked if checked else 1.0


def nested_array_alignment(predicted: list[Any], gold: list[Any]) -> float:
    """Average nested object field matches across aligned array positions."""
    if not predicted and not gold:
        return 1.0
    if not predicted or not gold:
        return 0.0

    total = 0
    matches = 0
    for index in range(max(len(predicted), len(gold))):
        pred_item = predicted[index] if index < len(predicted) else {}
        gold_item = gold[index] if index < len(gold) else {}
        if isinstance(pred_item, dict) and isinstance(gold_item, dict):
            keys = set(gold_item)
            total += len(keys)
            for key in keys:
                if key in pred_item and _values_match(pred_item[key], gold_item[key]):
                    matches += 1
        else:
            total += 1
            if _values_match(pred_item, gold_item):
                matches += 1
    return matches / total if total else 1.0


def normalized_value_match(predicted: Any, gold: Any) -> bool:
    """Compare dates, numbers, currency, and text with practical normalization."""
    return _values_match(predicted, gold)


def _values_match(predicted: Any, gold: Any) -> bool:
    if isinstance(predicted, dict) and isinstance(gold, dict):
        return field_accuracy(predicted, gold) == 1.0 and set(predicted) >= set(gold)
    if isinstance(predicted, list) and isinstance(gold, list):
        return nested_array_alignment(predicted, gold) == 1.0 and len(predicted) == len(gold)

    pred_date = _parse_date(predicted)
    gold_date = _parse_date(gold)
    if pred_date and gold_date:
        return pred_date == gold_date

    pred_number = _parse_number(predicted)
    gold_number = _parse_number(gold)
    if pred_number is not None and gold_number is not None:
        return abs(pred_number - gold_number) < 0.000001

    return _normalize_text(predicted) == _normalize_text(gold)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value).strip().lower().split())


def _parse_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not re.search(r"\d", text):
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if cleaned in {"", "-", "."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(value: Any) -> str | None:
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _matches_type(value: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_matches_type(value, item) for item in expected)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True
