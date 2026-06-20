"""Evaluation utilities for structured extraction."""

from __future__ import annotations

from extractfold.evaluation.metrics import (
    field_accuracy,
    hallucination_rate,
    nested_array_alignment,
    normalized_value_match,
    per_field_prf,
    schema_compliance,
    type_correctness,
)
from extractfold.evaluation.runner import EvaluationReport, EvaluationRunner

__all__ = [
    "EvaluationReport",
    "EvaluationRunner",
    "field_accuracy",
    "hallucination_rate",
    "nested_array_alignment",
    "normalized_value_match",
    "per_field_prf",
    "schema_compliance",
    "type_correctness",
]
