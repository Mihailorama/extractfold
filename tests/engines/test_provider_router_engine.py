from __future__ import annotations

from typing import Any

import pytest

from extractfold.engines.provider_router_engine import ProviderRouterEngine

from .helpers import INVOICE_SCHEMA, write_document


def test_provider_router_requires_injected_call() -> None:
    unavailable = ProviderRouterEngine()
    available = ProviderRouterEngine(provider_call=lambda **kwargs: {})

    assert unavailable.name == "provider_router"
    assert unavailable.is_available() is False
    assert available.is_available() is True


def test_provider_router_declares_remote_text_capabilities() -> None:
    capabilities = ProviderRouterEngine(provider_call=lambda **kwargs: {}).capabilities

    assert capabilities.remote is True
    assert capabilities.local is False
    assert capabilities.nested_schemas is True
    assert capabilities.batch is True
    assert "txt" in ProviderRouterEngine(provider_call=lambda **kwargs: {}).supported_extensions


@pytest.mark.asyncio
async def test_provider_router_calls_injected_provider_and_copies_metadata(tmp_path) -> None:
    doc = write_document(tmp_path, "Invoice INV-001 from Acme total 125.50")
    seen: dict[str, Any] = {}

    async def provider_call(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {
            "data": {"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5},
            "usage": {"input_tokens": 25, "output_tokens": 14},
            "cost": {"total": 0.002},
            "route": {"provider": "primary"},
        }

    result = await ProviderRouterEngine(
        provider="gateway",
        model="extract-small",
        provider_call=provider_call,
    ).extract(str(doc), INVOICE_SCHEMA, tenant="demo")

    assert seen["provider"] == "gateway"
    assert seen["model"] == "extract-small"
    assert seen["schema"] == INVOICE_SCHEMA
    assert seen["text"] == "Invoice INV-001 from Acme total 125.50"
    assert "Return only JSON" in seen["prompt"]
    assert seen["tenant"] == "demo"

    assert result.engine_name == "provider_router"
    assert result.valid is True
    assert result.data["vendor"] == "Acme"
    assert result.metadata["provider"] == "gateway"
    assert result.metadata["model"] == "extract-small"
    assert result.metadata["usage"] == {"input_tokens": 25, "output_tokens": 14}
    assert result.metadata["cost"] == {"total": 0.002}
    assert result.metadata["route"] == {"provider": "primary"}


@pytest.mark.asyncio
async def test_provider_router_parses_raw_json_string(tmp_path) -> None:
    doc = write_document(tmp_path)

    def provider_call(**kwargs: Any) -> str:
        return (
            '```json\n'
            '{"invoice_id": "INV-001", "vendor": "Acme", "total": "$125.50"}\n'
            "```"
        )

    result = await ProviderRouterEngine(provider_call=provider_call).extract(
        str(doc),
        INVOICE_SCHEMA,
    )

    assert result.valid is True
    assert result.data == {"invoice_id": "INV-001", "vendor": "Acme", "total": 125.5}


@pytest.mark.asyncio
async def test_provider_router_uses_direct_text_override(tmp_path) -> None:
    doc = write_document(tmp_path, "ignored")

    def provider_call(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["text"] == "direct prepared text"
        return {"invoice_id": "INV-002", "total": 99}

    result = await ProviderRouterEngine(provider_call=provider_call).extract(
        str(doc),
        INVOICE_SCHEMA,
        text="direct prepared text",
    )

    assert result.valid is True
    assert result.data["invoice_id"] == "INV-002"


@pytest.mark.integration
@pytest.mark.skip(reason="requires a configured provider-router callable")
@pytest.mark.asyncio
async def test_provider_router_real_integration() -> None:
    await ProviderRouterEngine().extract("tests/fixtures/invoice.txt", "invoice")
