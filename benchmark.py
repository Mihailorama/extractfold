"""Benchmark harness for extractfold datasets."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from extractfold.cli import _build_router  # noqa: E402
from extractfold.evaluation.metrics import field_accuracy, per_field_prf, schema_compliance  # noqa: E402


@dataclass
class BenchmarkReport:
    """Rows produced by a benchmark run."""

    rows: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps({"rows": self.rows}, indent=indent, ensure_ascii=False)

    def to_table(self) -> str:
        lines = [
            "Engine          Document        FieldAcc  F1     Compliance  Latency  Cost",
            "--------------  --------------  --------  -----  ----------  -------  ----",
        ]
        for row in self.rows:
            lines.append(
                f"{row['engine']:<14}  {row['document']:<14}  "
                f"{row['field_accuracy']:.3f}     {row['f1']:.3f}  "
                f"{row['schema_compliance']:.3f}       {row['latency_ms']:>7}  "
                f"{row['cost_usd']:.4f}"
            )
        return "\n".join(lines)


async def run_benchmark(
    dataset_path: str | Path,
    *,
    engines: list[str] | None = None,
    router: Any | None = None,
    output_path: str | Path | None = None,
) -> BenchmarkReport:
    dataset = Path(dataset_path)
    active_router = router or _build_router()
    engine_names = engines or [
        engine["name"] for engine in active_router.list_engines() if engine["available"]
    ]
    report = BenchmarkReport()
    for case in discover_cases(dataset):
        schema = _load_json(case["schema"])
        gold = _load_json(case["gold"])
        for engine_name in engine_names:
            start = time.perf_counter()
            result = await active_router.extract(
                str(case["document"]),
                schema,
                engine_hint=engine_name,
            )
            latency = result.processing_time_ms or int((time.perf_counter() - start) * 1000)
            prf = per_field_prf(result.data, gold)
            report.rows.append(
                {
                    "engine": engine_name,
                    "document": case["document"].stem,
                    "field_accuracy": field_accuracy(result.data, gold),
                    "f1": prf["f1"],
                    "schema_compliance": schema_compliance(result.data, schema),
                    "latency_ms": latency,
                    "cost_usd": float(result.metadata.get("cost_usd", 0.0)),
                }
            )
    if output_path:
        Path(output_path).write_text(report.to_json(), encoding="utf-8")
    return report


def discover_cases(dataset: Path) -> list[dict[str, Path]]:
    cases: list[dict[str, Path]] = []
    for schema_path in sorted(dataset.glob("*.schema.json")):
        stem = schema_path.name.replace(".schema.json", "")
        gold_path = dataset / f"{stem}.gold.json"
        if not gold_path.exists():
            continue
        for document_path in sorted(dataset.iterdir()):
            if document_path.stem == stem and not document_path.name.endswith(
                (".schema.json", ".gold.json")
            ):
                cases.append({"document": document_path, "schema": schema_path, "gold": gold_path})
                break
    return cases


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run extractfold benchmark datasets.")
    parser.add_argument("dataset")
    parser.add_argument("--engines", help="Comma-separated engine names")
    parser.add_argument("--out", help="Write JSON report to this path")
    args = parser.parse_args(argv)
    engines = args.engines.split(",") if args.engines else None
    report = asyncio.run(run_benchmark(args.dataset, engines=engines, output_path=args.out))
    print(report.to_table())


if __name__ == "__main__":
    main()
