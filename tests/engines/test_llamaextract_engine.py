from __future__ import annotations

import pytest

from extractfold.engines.llamaextract_engine import LlamaExtractEngine

from .helpers import INVOICE_SCHEMA, write_document


@pytest.mark.asyncio
async def test_llamaextract_engine_normalizes_result_key(tmp_path) -> None:
    doc = write_document(tmp_path)

    def client(**kwargs):
        return {"result": {"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5}}

    result = await LlamaExtractEngine(client=client).extract(str(doc), INVOICE_SCHEMA)

    assert result.engine_name == "llamaextract"
    assert result.valid is True
    assert result.data["vendor"] == "Acme"


@pytest.mark.integration
@pytest.mark.skip(reason="requires LlamaCloud credentials and network access")
@pytest.mark.asyncio
async def test_llamaextract_real_integration() -> None:
    await LlamaExtractEngine().extract("tests/fixtures/invoice.pdf", "invoice")
