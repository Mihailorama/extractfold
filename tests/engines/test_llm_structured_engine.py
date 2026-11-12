from __future__ import annotations

import pytest

from extractfold.engines.llm_structured_engine import (
    DEFAULT_ANTHROPIC_MODEL,
    LLMStructuredEngine,
    extract_json_object,
)

from .helpers import INVOICE_SCHEMA, write_document


def test_default_model_uses_latest_general_anthropic_model() -> None:
    assert DEFAULT_ANTHROPIC_MODEL == "claude-fable-5"


def test_extract_json_object_recovers_fenced_json() -> None:
    text = 'Here is the answer:\n```json\n{"invoice_id": "INV-001", "total": 125.5}\n```'

    assert extract_json_object(text)["invoice_id"] == "INV-001"


@pytest.mark.asyncio
async def test_llm_structured_anthropic_stubbed_call(tmp_path) -> None:
    doc = write_document(tmp_path)

    async def provider_call(**kwargs):
        assert kwargs["provider"] == "anthropic"
        assert kwargs["model"] == DEFAULT_ANTHROPIC_MODEL
        assert kwargs["schema"] == INVOICE_SCHEMA
        return {"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5}

    result = await LLMStructuredEngine(provider_call=provider_call).extract(
        str(doc),
        INVOICE_SCHEMA,
    )

    assert result.engine_name == "llm_structured"
    assert result.valid is True
    assert result.data["vendor"] == "Acme"
    assert result.metadata["provider"] == "anthropic"


@pytest.mark.parametrize("provider", ["openai", "gemini"])
@pytest.mark.asyncio
async def test_llm_structured_other_providers_parse_json(provider, tmp_path) -> None:
    doc = write_document(tmp_path)

    def provider_call(**kwargs):
        assert kwargs["provider"] == provider
        return '{"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5}'

    result = await LLMStructuredEngine(provider=provider, provider_call=provider_call).extract(
        str(doc),
        INVOICE_SCHEMA,
    )

    assert result.valid is True
    assert result.data["invoice_id"] == "INV-001"


@pytest.mark.integration
@pytest.mark.skip(reason="requires provider API key and network access")
@pytest.mark.asyncio
async def test_llm_structured_real_anthropic_integration() -> None:
    await LLMStructuredEngine().extract("tests/fixtures/invoice.pdf", "invoice")


class _Block:
    def __init__(self, kind: str, text: str = "") -> None:
        self.type = kind
        self.text = text


def _fake_anthropic(monkeypatch, calls: list[dict]) -> None:
    import sys
    import types

    class Messages:
        def create(self, **kwargs):
            calls.append(kwargs)
            content = [_Block("thinking"), _Block("text", '{"invoice_id": "INV-9", "total": 3}')]
            return types.SimpleNamespace(content=content)

    class Anthropic:
        def __init__(self) -> None:
            self.messages = Messages()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=Anthropic))


@pytest.mark.asyncio
async def test_anthropic_call_omits_temperature_and_reads_text_blocks(monkeypatch) -> None:
    calls: list[dict] = []
    _fake_anthropic(monkeypatch, calls)
    engine = LLMStructuredEngine(model="claude-haiku-5-5")

    result = await engine.extract_text("Invoice INV-9 total 3", INVOICE_SCHEMA)
    await engine.extract_text("Invoice INV-9 total 3", INVOICE_SCHEMA, temperature=0.2)

    assert result.data == {"invoice_id": "INV-9", "total": 3}
    assert "temperature" not in calls[0]
    assert calls[1]["temperature"] == 0.2
