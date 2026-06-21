from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from extractfold.engines.base import (
    ExtractionCapabilities,
    ExtractionEngine,
    ExtractionResult,
    ExtractionRouter,
)


class FakeEngine(ExtractionEngine):
    def __init__(
        self,
        name: str,
        extensions: set[str],
        *,
        available: bool = True,
        fail: bool = False,
        data: dict | None = None,
        capabilities: ExtractionCapabilities | None = None,
    ) -> None:
        self._name = name
        self._extensions = extensions
        self._available = available
        self._fail = fail
        self._data = data or {"engine": name}
        self._capabilities = capabilities or ExtractionCapabilities()

    @property
    def name(self) -> str:
        return self._name

    @property
    def supported_extensions(self) -> set[str]:
        return self._extensions

    @property
    def capabilities(self) -> ExtractionCapabilities:
        return self._capabilities

    def is_available(self) -> bool:
        return self._available

    async def extract(self, file_path: str, schema, **kwargs):
        if self._fail:
            raise RuntimeError(f"{self._name} failed")
        return ExtractionResult(data=self._data, engine_name=self._name, schema=schema)


@pytest.fixture
def router() -> ExtractionRouter:
    return ExtractionRouter(
        [
            FakeEngine("llm_structured", {"pdf", "txt"}, available=True),
            FakeEngine("lift", {"pdf"}, available=True),
            FakeEngine("nuextract", {"pdf", "txt"}, available=True),
        ]
    )


class TestSelection:
    def test_explicit_hint(self, router: ExtractionRouter) -> None:
        engine = router.select("invoice.pdf", engine_hint="lift")

        assert engine.name == "lift"

    def test_unknown_hint_raises(self, router: ExtractionRouter) -> None:
        with pytest.raises(ValueError, match="Unknown engine"):
            router.select("invoice.pdf", engine_hint="missing")

    def test_unavailable_hint_raises(self) -> None:
        router = ExtractionRouter([FakeEngine("lift", {"pdf"}, available=False)])

        with pytest.raises(RuntimeError, match="not available"):
            router.select("invoice.pdf", engine_hint="lift")

    def test_env_default(self, router: ExtractionRouter) -> None:
        with patch.dict(os.environ, {"EXTRACTFOLD_ENGINE": "nuextract"}):
            assert router.select("invoice.txt").name == "nuextract"

    def test_text_priority_prefers_provider_router_when_available(self) -> None:
        router = ExtractionRouter(
            [
                FakeEngine("llm_structured", {"txt"}, available=True),
                FakeEngine("provider_router", {"txt"}, available=True),
                FakeEngine("nuextract", {"txt"}, available=True),
            ]
        )

        assert router.select("invoice.txt").name == "provider_router"

    def test_legacy_engine_default_env_is_supported(self, router: ExtractionRouter) -> None:
        with patch.dict(os.environ, {"ENGINE_DEFAULT": "lift"}, clear=True):
            assert router.select("invoice.pdf").name == "lift"

    def test_allowed_engines_restricts_selection(self) -> None:
        router = ExtractionRouter(
            [
                FakeEngine("llm_structured", {"pdf"}),
                FakeEngine("lift", {"pdf"}),
            ],
            allowed_engines={"lift"},
        )

        assert router.select("invoice.pdf").name == "lift"

    def test_no_available_engine_raises(self) -> None:
        router = ExtractionRouter([FakeEngine("pdf_only", {"pdf"})])

        with pytest.raises(ValueError, match="No available engine"):
            router.select("invoice.xlsx")


class TestExtract:
    @pytest.mark.asyncio
    async def test_delegates_to_selected_engine(self, router: ExtractionRouter) -> None:
        result = await router.extract("invoice.pdf", {"type": "object"}, engine_hint="lift")

        assert result.engine_name == "lift"
        assert result.data == {"engine": "lift"}

    @pytest.mark.asyncio
    async def test_falls_back_when_priority_engine_fails(self) -> None:
        router = ExtractionRouter(
            [
                FakeEngine("llm_structured", {"pdf"}, fail=True),
                FakeEngine("lift", {"pdf"}, data={"ok": True}),
            ],
            fallback_order=["llm_structured", "lift"],
        )

        result = await router.extract("invoice.pdf", {"type": "object"})

        assert result.engine_name == "lift"
        assert result.data == {"ok": True}

    @pytest.mark.asyncio
    async def test_explicit_hint_does_not_fallback(self) -> None:
        router = ExtractionRouter(
            [
                FakeEngine("llm_structured", {"pdf"}, fail=True),
                FakeEngine("lift", {"pdf"}),
            ]
        )

        with pytest.raises(RuntimeError, match="llm_structured failed"):
            await router.extract("invoice.pdf", {"type": "object"}, engine_hint="llm_structured")


class TestBatchCompareIntrospection:
    @pytest.mark.asyncio
    async def test_extract_batch_returns_success_and_error_counts(self) -> None:
        router = ExtractionRouter([FakeEngine("lift", {"pdf"})])

        batch = await router.extract_batch(
            ["a.pdf", "b.pdf"],
            {"type": "object"},
            engine_hint="lift",
        )

        assert batch.total == 2
        assert batch.succeeded == 2
        assert batch.failed == 0
        assert batch.success_rate == 1.0

    @pytest.mark.asyncio
    async def test_compare_runs_named_engines(self, router: ExtractionRouter) -> None:
        results = await router.compare(
            "invoice.pdf",
            {"type": "object"},
            engines=["lift", "llm_structured"],
        )

        assert set(results) == {"lift", "llm_structured"}
        assert results["lift"].engine_name == "lift"

    def test_list_engines_includes_capabilities(self, router: ExtractionRouter) -> None:
        engines = router.list_engines()
        names = {engine["name"] for engine in engines}

        assert names == {"llm_structured", "lift", "nuextract"}
        assert "capabilities" in engines[0]
        assert "field_confidence" in engines[0]["capabilities"]
