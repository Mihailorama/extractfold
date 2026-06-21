from __future__ import annotations

import json

import pytest

from extractfold.engines.base import (
    ExtractionCapabilities,
    ExtractionEngine,
    ExtractionResult,
    load_schema,
    validate_data,
)


class TestExtractionResult:
    def test_minimal_creation_defaults_optional_maps(self) -> None:
        schema = {"type": "object"}
        result = ExtractionResult(data={"name": "Acme"}, engine_name="stub", schema=schema)

        assert result.data == {"name": "Acme"}
        assert result.engine_name == "stub"
        assert result.schema == schema
        assert result.field_confidence == {}
        assert result.provenance == {}
        assert result.valid is True
        assert result.raw is None
        assert result.metadata == {}
        assert result.pages is None
        assert result.processing_time_ms == 0

    def test_full_creation_preserves_contract_fields(self) -> None:
        result = ExtractionResult(
            data={"invoice_id": "INV-001"},
            engine_name="lift",
            schema={"type": "object"},
            field_confidence={"invoice_id": 0.97},
            provenance={"invoice_id": {"page": 1, "text": "INV-001"}},
            valid=True,
            raw={"provider": "payload"},
            metadata={"model": "x"},
            pages=2,
            processing_time_ms=123,
        )

        assert result.field_confidence["invoice_id"] == 0.97
        assert result.provenance["invoice_id"]["page"] == 1
        assert result.raw == {"provider": "payload"}
        assert result.pages == 2
        assert result.processing_time_ms == 123


class TestExtractionCapabilities:
    def test_defaults_are_conservative(self) -> None:
        caps = ExtractionCapabilities()

        assert caps.field_confidence is False
        assert caps.provenance is False
        assert caps.nested_schemas is False
        assert caps.batch is False
        assert caps.local is False
        assert caps.remote is False

    def test_to_dict(self) -> None:
        caps = ExtractionCapabilities(field_confidence=True, remote=True)

        assert caps.to_dict()["field_confidence"] is True
        assert caps.to_dict()["remote"] is True


class TestExtractionEngineInterface:
    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            ExtractionEngine()  # type: ignore[abstract]

    def test_concrete_implementation(self, tmp_path) -> None:
        class DummyEngine(ExtractionEngine):
            @property
            def name(self) -> str:
                return "dummy"

            @property
            def supported_extensions(self) -> set[str]:
                return {"txt"}

            def is_available(self) -> bool:
                return True

            async def extract(self, file_path: str, schema, **kwargs):
                return ExtractionResult(
                    data={"ok": True},
                    engine_name=self.name,
                    schema=load_schema(schema),
                )

        engine = DummyEngine()
        assert engine.name == "dummy"
        assert engine.is_available()
        assert "txt" in engine.supported_extensions
        assert repr(engine) == "<DummyEngine name='dummy' available=True>"


class TestLoadSchema:
    def test_accepts_dict(self) -> None:
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        assert load_schema(schema) == schema

    def test_accepts_json_string(self) -> None:
        schema = {"type": "object", "properties": {"total": {"type": "number"}}}

        assert load_schema(json.dumps(schema)) == schema

    def test_accepts_file_path(self, tmp_path) -> None:
        schema = {"type": "object", "properties": {"date": {"type": "string"}}}
        path = tmp_path / "schema.json"
        path.write_text(json.dumps(schema), encoding="utf-8")

        assert load_schema(str(path)) == schema

    def test_accepts_named_ref(self) -> None:
        schema = load_schema("invoice")

        assert schema["type"] == "object"
        assert "properties" in schema
        assert "invoice_id" in schema["properties"]

    def test_unknown_named_ref_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown schema"):
            load_schema("does-not-exist")


class TestValidateData:
    def test_validates_required_and_types(self) -> None:
        schema = {
            "type": "object",
            "required": ["invoice_id", "total"],
            "properties": {
                "invoice_id": {"type": "string"},
                "total": {"type": "number"},
            },
        }

        valid = validate_data({"invoice_id": "INV-001", "total": 12.5}, schema)
        invalid = validate_data({"invoice_id": "INV-001", "total": "12.5"}, schema)

        assert valid.valid is True
        assert valid.errors == []
        assert invalid.valid is False
        assert any("total" in error for error in invalid.errors)
