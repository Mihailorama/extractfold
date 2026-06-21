from __future__ import annotations

import json

import pytest

import benchmark
from extractfold.engines.base import ExtractionResult


class BenchmarkRouter:
    async def extract(self, file_path, schema, engine_hint=None, **kwargs):
        return ExtractionResult(
            data={"invoice_id": "INV-001", "total": 125.5},
            engine_name=engine_hint or "stub",
            schema=schema,
            valid=True,
            processing_time_ms=7,
            metadata={"cost_usd": 0.01},
        )


@pytest.mark.asyncio
async def test_run_benchmark_discovers_dataset_and_writes_results(tmp_path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "invoice.txt").write_text("invoice", encoding="utf-8")
    (dataset / "invoice.schema.json").write_text(json.dumps({"type": "object"}), encoding="utf-8")
    (dataset / "invoice.gold.json").write_text(
        json.dumps({"invoice_id": "INV-001", "total": 125.5}),
        encoding="utf-8",
    )
    output = tmp_path / "results.json"

    report = await benchmark.run_benchmark(
        dataset,
        engines=["stub"],
        router=BenchmarkRouter(),
        output_path=output,
    )

    assert output.exists()
    assert report.rows[0]["engine"] == "stub"
    assert report.rows[0]["field_accuracy"] == 1.0
    assert report.rows[0]["latency_ms"] == 7
    assert report.rows[0]["cost_usd"] == 0.01
    assert "Engine" in report.to_table()
