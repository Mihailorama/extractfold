"""Evaluation runner for predictions-vs-gold extraction datasets."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from extractfold.evaluation.metrics import (
    field_accuracy,
    hallucination_rate,
    per_field_prf,
    type_correctness,
)


@dataclass
class DocumentScore:
    """Scores for one engine/document prediction."""

    document_id: str
    engine_name: str
    field_accuracy: float
    precision: float
    recall: float
    f1: float
    hallucination_rate: float
    type_correctness: float | None = None
    error: str | None = None


@dataclass
class EvaluationReport:
    """Aggregated evaluation report."""

    timestamp: str
    scores: list[DocumentScore] = field(default_factory=list)
    engine_summaries: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "scores": [asdict(score) for score in self.scores],
            "engine_summaries": self.engine_summaries,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_table(self) -> str:
        lines = [
            "Engine          Docs  FieldAcc  Precision  Recall  F1     Hallucination",
            "--------------  ----  --------  ---------  ------  -----  -------------",
        ]
        for engine, summary in sorted(self.engine_summaries.items()):
            lines.append(
                f"{engine:<14}  {int(summary['documents']):>4}  "
                f"{summary['field_accuracy']:.3f}     {summary['precision']:.3f}      "
                f"{summary['recall']:.3f}   {summary['f1']:.3f}  "
                f"{summary['hallucination_rate']:.3f}"
            )
        return "\n".join(lines)


class EvaluationRunner:
    """Score ``predictions/<engine>/*.json`` against ``gold/*.json``."""

    def __init__(self, dataset_path: str | Path) -> None:
        self.dataset_path = Path(dataset_path)

    def run(self, engines: list[str] | None = None) -> EvaluationReport:
        report = EvaluationReport(timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"))
        for engine_name, prediction_path, gold_path in self._discover_pairs(engines):
            prediction = self._load_json(prediction_path)
            gold = self._load_json(gold_path)
            schema = self._load_schema_for(gold_path)
            prf = per_field_prf(prediction, gold)
            report.scores.append(
                DocumentScore(
                    document_id=gold_path.stem,
                    engine_name=engine_name,
                    field_accuracy=field_accuracy(prediction, gold),
                    precision=prf["precision"],
                    recall=prf["recall"],
                    f1=prf["f1"],
                    hallucination_rate=hallucination_rate(prediction, gold),
                    type_correctness=type_correctness(prediction, schema) if schema else None,
                )
            )
        report.engine_summaries = self._summaries(report.scores)
        return report

    def _discover_pairs(
        self, engines: list[str] | None
    ) -> list[tuple[str, Path, Path]]:
        pairs: list[tuple[str, Path, Path]] = []
        predictions_dir = self.dataset_path / "predictions"
        gold_dir = self.dataset_path / "gold"
        if not predictions_dir.exists() or not gold_dir.exists():
            return pairs
        for engine_dir in sorted(path for path in predictions_dir.iterdir() if path.is_dir()):
            if engines and engine_dir.name not in engines:
                continue
            for prediction_path in sorted(engine_dir.glob("*.json")):
                gold_path = gold_dir / prediction_path.name
                if gold_path.exists():
                    pairs.append((engine_dir.name, prediction_path, gold_path))
        return pairs

    def _load_schema_for(self, gold_path: Path) -> dict[str, Any] | None:
        schema_path = gold_path.with_suffix(".schema.json")
        if schema_path.exists():
            return self._load_json(schema_path)
        return None

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a JSON object")
        return data

    @staticmethod
    def _summaries(scores: list[DocumentScore]) -> dict[str, dict[str, float]]:
        grouped: dict[str, list[DocumentScore]] = {}
        for score in scores:
            grouped.setdefault(score.engine_name, []).append(score)
        summaries: dict[str, dict[str, float]] = {}
        for engine, items in grouped.items():
            summaries[engine] = {
                "documents": float(len(items)),
                "field_accuracy": _avg([item.field_accuracy for item in items]),
                "precision": _avg([item.precision for item in items]),
                "recall": _avg([item.recall for item in items]),
                "f1": _avg([item.f1 for item in items]),
                "hallucination_rate": _avg([item.hallucination_rate for item in items]),
            }
        return summaries


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
