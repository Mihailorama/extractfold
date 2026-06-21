from __future__ import annotations

import pytest

from extractfold.evaluation.metrics import (
    field_accuracy,
    hallucination_rate,
    nested_array_alignment,
    normalized_value_match,
    per_field_prf,
    schema_compliance,
    type_correctness,
)


def test_field_accuracy_counts_matching_gold_fields_only() -> None:
    predicted = {"invoice_id": "INV-001", "vendor": "Wrong", "total": 125.5, "extra": "x"}
    gold = {"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5}

    assert field_accuracy(predicted, gold) == pytest.approx(2 / 3)


def test_per_field_precision_recall_f1_counts_extras_and_missing() -> None:
    predicted = {"invoice_id": "INV-001", "vendor": "Wrong", "extra": "x"}
    gold = {"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5}

    scores = per_field_prf(predicted, gold)

    assert scores["precision"] == pytest.approx(1 / 3)
    assert scores["recall"] == pytest.approx(1 / 3)
    assert scores["f1"] == pytest.approx(1 / 3)


def test_hallucination_rate_counts_extra_fields() -> None:
    predicted = {"invoice_id": "INV-001", "unexpected": "x"}
    gold = {"invoice_id": "INV-001"}

    assert hallucination_rate(predicted, gold) == pytest.approx(0.5)


def test_type_correctness_uses_json_schema_properties() -> None:
    schema = {
        "type": "object",
        "properties": {
            "invoice_id": {"type": "string"},
            "total": {"type": "number"},
            "paid": {"type": "boolean"},
        },
    }

    assert type_correctness(
        {"invoice_id": "INV-001", "total": 125.5, "paid": "yes"},
        schema,
    ) == pytest.approx(2 / 3)


def test_schema_compliance_returns_one_for_valid_and_zero_for_invalid() -> None:
    schema = {
        "type": "object",
        "required": ["invoice_id"],
        "properties": {"invoice_id": {"type": "string"}},
    }

    assert schema_compliance({"invoice_id": "INV-001"}, schema) == 1.0
    assert schema_compliance({"invoice_id": 123}, schema) == 0.0


@pytest.mark.parametrize(
    ("predicted", "gold"),
    [
        ("2024-01-15", "January 15, 2024"),
        ("$1,250.00", "1250"),
        (" Acme  Corporation ", "acme corporation"),
    ],
)
def test_normalized_value_match_dates_numbers_currency_and_text(predicted, gold) -> None:
    assert normalized_value_match(predicted, gold) is True


def test_nested_array_alignment_averages_item_field_matches() -> None:
    predicted = [
        {"description": "Hosting", "amount": 100},
        {"description": "Support", "amount": 25},
    ]
    gold = [
        {"description": "Hosting", "amount": 100},
        {"description": "Support", "amount": 30},
    ]

    assert nested_array_alignment(predicted, gold) == pytest.approx(0.75)
