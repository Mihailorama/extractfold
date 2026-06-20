from __future__ import annotations

import pytest

from extractfold.engines.base import ExtractionResult
from extractfold.engines.docfold_llm_engine import DocfoldLLMEngine

from .helpers import INVOICE_SCHEMA, write_document


class StubLLMEngine:
    name = "llm_structured"

    async def extract_text(self, text, schema, **kwargs):
        assert "Invoice" in text
        return ExtractionResult(
            data={"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5},
            engine_name=self.name,
            schema=schema,
            valid=True,
        )


@pytest.mark.asyncio
async def test_docfold_llm_runs_docfold_then_llm(tmp_path) -> None:
    doc = write_document(tmp_path)

    async def docfold_runner(file_path, **kwargs):
        assert file_path == str(doc)
        return "Invoice INV-001 vendor Acme total 125.50"

    engine = DocfoldLLMEngine(docfold_runner=docfold_runner, llm_engine=StubLLMEngine())
    result = await engine.extract(str(doc), INVOICE_SCHEMA)

    assert result.engine_name == "docfold_llm"
    assert result.valid is True
    assert result.data["invoice_id"] == "INV-001"
    assert result.metadata["docfold_content_length"] > 0
    assert result.metadata["llm_engine"] == "llm_structured"


@pytest.mark.integration
@pytest.mark.skip(reason="requires docfold plus provider credentials")
@pytest.mark.asyncio
async def test_docfold_llm_real_integration() -> None:
    await DocfoldLLMEngine().extract("tests/fixtures/invoice.pdf", "invoice")
