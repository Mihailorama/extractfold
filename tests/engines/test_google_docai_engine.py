from __future__ import annotations

import pytest

from extractfold.engines.google_docai_engine import GoogleDocAIEngine

from .helpers import INVOICE_SCHEMA, write_document


@pytest.mark.asyncio
async def test_google_docai_maps_entities(tmp_path) -> None:
    doc = write_document(tmp_path)

    def client(**kwargs):
        return {
            "entities": [
                {"type": "invoice_id", "mention_text": "INV-001", "confidence": 0.98, "page": 1},
                {"type": "vendor", "mention_text": "Acme", "confidence": 0.91, "page": 1},
                {"type": "total", "normalized_value": 125.5, "confidence": 0.94, "page": 1},
            ],
            "pages": 1,
        }

    result = await GoogleDocAIEngine(client=client).extract(str(doc), INVOICE_SCHEMA)

    assert result.engine_name == "google_docai"
    assert result.valid is True
    assert result.data["total"] == 125.5
    assert result.field_confidence["vendor"] == 0.91


@pytest.mark.integration
@pytest.mark.skip(reason="requires Google Document AI credentials and processor")
@pytest.mark.asyncio
async def test_google_docai_real_integration() -> None:
    await GoogleDocAIEngine().extract("tests/fixtures/invoice.pdf", "invoice")
