from __future__ import annotations

import pytest

from extractfold.engines.nuextract_engine import NuExtractEngine

from .helpers import INVOICE_SCHEMA, write_document


@pytest.mark.asyncio
async def test_nuextract_engine_uses_stubbed_backend(tmp_path) -> None:
    doc = write_document(tmp_path)

    def backend(*, text, schema, model, backend):
        assert "Invoice" in text
        assert model
        assert backend == "hf"
        return '{"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5}'

    result = await NuExtractEngine(backend_runner=backend).extract(str(doc), INVOICE_SCHEMA)

    assert result.engine_name == "nuextract"
    assert result.valid is True
    assert result.data["total"] == 125.5


def test_nuextract_capabilities_are_local() -> None:
    caps = NuExtractEngine().capabilities

    assert caps.local is True
    assert caps.remote is False
    assert caps.nested_schemas is True


@pytest.mark.integration
@pytest.mark.skip(reason="requires NuExtract model weights and HF/vLLM runtime")
@pytest.mark.asyncio
async def test_nuextract_real_integration() -> None:
    await NuExtractEngine().extract("tests/fixtures/invoice.pdf", "invoice")
