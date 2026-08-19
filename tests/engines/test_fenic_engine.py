from __future__ import annotations

import pytest

from extractfold.engines.fenic_engine import FenicEngine

from .helpers import INVOICE_SCHEMA, write_document


@pytest.mark.asyncio
async def test_fenic_engine_uses_injected_extractor(tmp_path) -> None:
    doc = write_document(tmp_path)

    def extractor(**kwargs):
        assert kwargs["schema"] == INVOICE_SCHEMA
        assert "INV-001" in kwargs["text"]
        return {"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5}

    result = await FenicEngine(extractor=extractor).extract(str(doc), INVOICE_SCHEMA)

    assert result.engine_name == "fenic"
    assert result.valid is True
    assert result.data["invoice_id"] == "INV-001"
    assert result.data["total"] == 125.5


@pytest.mark.asyncio
async def test_fenic_engine_accepts_async_extractor(tmp_path) -> None:
    doc = write_document(tmp_path)

    async def extractor(**kwargs):
        return {"invoice_id": "INV-002", "total": 10}

    result = await FenicEngine(extractor=extractor).extract(str(doc), INVOICE_SCHEMA)

    assert result.data["invoice_id"] == "INV-002"


def test_fenic_engine_unavailable_without_dependency() -> None:
    assert FenicEngine().is_available() is False


def test_fenic_engine_available_with_injected_extractor() -> None:
    assert FenicEngine(extractor=lambda **kwargs: {}).is_available() is True


def test_fenic_capabilities() -> None:
    caps = FenicEngine().capabilities

    assert caps.remote is True
    assert caps.nested_schemas is True
    assert caps.batch is True


def test_fenic_supported_extensions_are_text_first() -> None:
    extensions = FenicEngine().supported_extensions

    assert {"txt", "md", "html"}.issubset(extensions)


def test_fenic_schema_to_field_specs_maps_types_and_required() -> None:
    from extractfold.engines.fenic_engine import _schema_to_field_specs

    specs = _schema_to_field_specs(INVOICE_SCHEMA)

    assert specs["invoice_id"] == ("string", True, None)
    assert specs["vendor"] == ("string", False, None)
    assert specs["total"] == ("number", True, None)
    kind, required, children = specs["line_items"]
    assert kind == "array"
    assert required is False
    item_kind, _, item_specs = children
    assert item_kind == "object"
    assert item_specs["description"] == ("string", True, None)
    assert item_specs["amount"] == ("number", True, None)


@pytest.mark.integration
@pytest.mark.skip(reason="requires fenic plus a configured model provider")
@pytest.mark.asyncio
async def test_fenic_real_integration() -> None:
    await FenicEngine().extract("tests/fixtures/invoice.txt", "invoice")
