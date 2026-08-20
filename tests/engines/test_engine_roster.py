from __future__ import annotations

from extractfold.cli import _build_router


def test_default_router_registers_required_engines() -> None:
    router = _build_router()
    names = {engine["name"] for engine in router.list_engines()}

    assert {
        "lift",
        "nuextract",
        "provider_router",
        "llm_structured",
        "instructor",
        "fenic",
        "llamaextract",
        "azure_docint",
        "google_docai",
        "textract",
        "docfold_llm",
    }.issubset(names)
