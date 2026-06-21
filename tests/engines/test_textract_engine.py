from __future__ import annotations

import pytest

from extractfold.engines.textract_engine import TextractEngine

from .helpers import INVOICE_SCHEMA, write_document


@pytest.mark.asyncio
async def test_textract_maps_query_results(tmp_path) -> None:
    doc = write_document(tmp_path)

    def client(**kwargs):
        return {
            "Blocks": [
                {
                    "BlockType": "QUERY_RESULT",
                    "Text": "INV-001",
                    "Confidence": 98.0,
                    "Query": {"Alias": "invoice_id"},
                    "Page": 1,
                },
                {
                    "BlockType": "QUERY_RESULT",
                    "Text": "125.5",
                    "Confidence": 93.0,
                    "Query": {"Alias": "total"},
                    "Page": 1,
                },
            ],
            "DocumentMetadata": {"Pages": 1},
        }

    result = await TextractEngine(client=client).extract(str(doc), INVOICE_SCHEMA)

    assert result.engine_name == "textract"
    assert result.valid is True
    assert result.data["invoice_id"] == "INV-001"
    assert result.data["total"] == 125.5
    assert result.field_confidence["total"] == 0.93


@pytest.mark.integration
@pytest.mark.skip(reason="requires AWS Textract credentials")
@pytest.mark.asyncio
async def test_textract_real_integration() -> None:
    await TextractEngine().extract("tests/fixtures/invoice.pdf", "invoice")
