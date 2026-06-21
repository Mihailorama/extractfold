from __future__ import annotations

import json

from extractfold.evaluation.runner import EvaluationRunner


def test_runner_scores_prediction_gold_dataset(tmp_path) -> None:
    predictions = tmp_path / "predictions" / "stub"
    gold = tmp_path / "gold"
    predictions.mkdir(parents=True)
    gold.mkdir()

    (predictions / "invoice.json").write_text(
        json.dumps({"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5}),
        encoding="utf-8",
    )
    (gold / "invoice.json").write_text(
        json.dumps({"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5}),
        encoding="utf-8",
    )

    report = EvaluationRunner(tmp_path).run()

    assert len(report.scores) == 1
    assert report.scores[0].field_accuracy == 1.0
    assert report.engine_summaries["stub"]["field_accuracy"] == 1.0
    assert "Engine" in report.to_table()
    assert "stub" in report.to_json()
