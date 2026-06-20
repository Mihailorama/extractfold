from __future__ import annotations

import pytest

from extractfold.engines.lift_engine import LiftEngine

from .helpers import INVOICE_SCHEMA, write_document


@pytest.mark.asyncio
async def test_lift_engine_normalizes_stubbed_response(tmp_path) -> None:
    doc = write_document(tmp_path)

    async def client(**kwargs):
        return {
            "data": {"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5},
            "field_confidence": {"invoice_id": 0.98, "total": 0.93},
            "provenance": {"invoice_id": {"page": 1, "text": "INV-001"}},
            "pages": 1,
        }

    result = await LiftEngine(client=client).extract(str(doc), INVOICE_SCHEMA)

    assert result.engine_name == "lift"
    assert result.valid is True
    assert result.data["invoice_id"] == "INV-001"
    assert result.field_confidence["total"] == 0.93
    assert result.provenance["invoice_id"]["page"] == 1
    assert result.raw is not None


def test_lift_capabilities_are_honest() -> None:
    caps = LiftEngine().capabilities

    assert caps.remote is True
    assert caps.field_confidence is True
    assert caps.provenance is True
    assert caps.nested_schemas is True


@pytest.mark.integration
@pytest.mark.skip(reason="requires Lift credentials and network access")
@pytest.mark.asyncio
async def test_lift_real_integration() -> None:
    await LiftEngine().extract("tests/fixtures/invoice.pdf", "invoice")
