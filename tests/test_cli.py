from __future__ import annotations

import json

import pytest

from extractfold import cli
from extractfold.engines.base import ExtractionCapabilities, ExtractionResult


class StubRouter:
    def list_engines(self):
        return [
            {
                "name": "stub",
                "available": True,
                "extensions": ["pdf", "txt"],
                "capabilities": ExtractionCapabilities(
                    field_confidence=True,
                    provenance=True,
                    nested_schemas=True,
                    remote=False,
                    local=True,
                ).to_dict(),
            }
        ]

    async def extract(self, file_path, schema, engine_hint=None, **kwargs):
        return ExtractionResult(
            data={"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5},
            engine_name=engine_hint or "stub",
            schema=schema,
            valid=True,
            field_confidence={"invoice_id": 0.98},
        )

    async def compare(self, file_path, schema, engines=None, **kwargs):
        return {
            "stub": ExtractionResult(
                data={"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5},
                engine_name="stub",
                schema=schema,
                valid=True,
            ),
            "other": ExtractionResult(
                data={"invoice_id": "INV-001", "vendor": "Acme", "total": 120.0},
                engine_name="other",
                schema=schema,
                valid=True,
            ),
        }


def test_no_args_prints_help(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main([])

    assert exc.value.code == 0
    assert "extractfold" in capsys.readouterr().out


def test_list_engines_prints_table(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "_build_router", lambda: StubRouter())

    cli.main(["list-engines"])

    out = capsys.readouterr().out
    assert "Engine" in out
    assert "stub" in out
    assert "Conf" in out


def test_extract_prints_json(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(cli, "_build_router", lambda: StubRouter())
    doc = tmp_path / "invoice.txt"
    doc.write_text("invoice", encoding="utf-8")
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"type": "object"}), encoding="utf-8")

    cli.main(["extract", str(doc), "--schema", str(schema), "--engine", "stub"])

    data = json.loads(capsys.readouterr().out)
    assert data["data"]["invoice_id"] == "INV-001"
    assert data["engine_name"] == "stub"


def test_extract_writes_output_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "_build_router", lambda: StubRouter())
    doc = tmp_path / "invoice.txt"
    doc.write_text("invoice", encoding="utf-8")
    out = tmp_path / "result.json"

    cli.main(["extract", str(doc), "--schema", '{"type":"object"}', "--out", str(out)])

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["data"]["vendor"] == "Acme"


def test_compare_prints_field_agreement(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(cli, "_build_router", lambda: StubRouter())
    doc = tmp_path / "invoice.txt"
    doc.write_text("invoice", encoding="utf-8")

    cli.main(["compare", str(doc), "--schema", '{"type":"object"}', "--engines", "stub,other"])

    out = capsys.readouterr().out
    assert "Field agreement" in out
    assert "invoice_id" in out
    assert "stub" in out


def test_benchmark_delegates_to_harness(monkeypatch, tmp_path, capsys) -> None:
    def fake_run_cli(args):
        print(f"benchmark:{args.dataset}")

    monkeypatch.setattr(cli, "_run_benchmark_cli", fake_run_cli)

    cli.main(["benchmark", str(tmp_path)])

    assert f"benchmark:{tmp_path}" in capsys.readouterr().out
