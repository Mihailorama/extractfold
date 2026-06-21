from __future__ import annotations

import pytest

from extractfold.engines.instructor_engine import InstructorEngine

from .helpers import INVOICE_SCHEMA, write_document


class DumpableResponse:
    def model_dump(self):
        return {"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5}


@pytest.mark.asyncio
async def test_instructor_engine_accepts_model_dump_response(tmp_path) -> None:
    doc = write_document(tmp_path)

    def extractor(**kwargs):
        assert kwargs["schema"] == INVOICE_SCHEMA
        return DumpableResponse()

    result = await InstructorEngine(extractor=extractor).extract(str(doc), INVOICE_SCHEMA)

    assert result.engine_name == "instructor"
    assert result.valid is True
    assert result.data["invoice_id"] == "INV-001"


def test_instructor_capabilities_are_remote_by_default() -> None:
    caps = InstructorEngine().capabilities

    assert caps.remote is True
    assert caps.nested_schemas is True


@pytest.mark.integration
@pytest.mark.skip(reason="requires instructor plus configured chat provider")
@pytest.mark.asyncio
async def test_instructor_real_integration() -> None:
    await InstructorEngine().extract("tests/fixtures/invoice.pdf", "invoice")
