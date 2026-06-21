from __future__ import annotations

import pytest

from extractfold.engines.azure_docint_engine import AzureDocIntEngine

from .helpers import INVOICE_SCHEMA, write_document


@pytest.mark.asyncio
async def test_azure_docint_maps_query_fields(tmp_path) -> None:
    doc = write_document(tmp_path)

    def client(**kwargs):
        return {
            "fields": {
                "invoice_id": {"value": "INV-001", "confidence": 0.98, "page": 1},
                "vendor": {"value": "Acme", "confidence": 0.87, "page": 1},
                "total": {"value": 125.5, "confidence": 0.93, "page": 1},
            },
            "pages": 1,
        }

    result = await AzureDocIntEngine(client=client).extract(str(doc), INVOICE_SCHEMA)

    assert result.engine_name == "azure_docint"
    assert result.valid is True
    assert result.data["total"] == 125.5
    assert result.field_confidence["invoice_id"] == 0.98
    assert result.provenance["vendor"]["page"] == 1


@pytest.mark.integration
@pytest.mark.skip(reason="requires Azure Document Intelligence credentials")
@pytest.mark.asyncio
async def test_azure_docint_real_integration() -> None:
    await AzureDocIntEngine().extract("tests/fixtures/invoice.pdf", "invoice")
