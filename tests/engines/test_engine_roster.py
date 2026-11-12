from __future__ import annotations

from extractfold.cli import _build_router


def test_default_router_registers_required_engines() -> None:
    router = _build_router(llm_model="claude-haiku-5-5")
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


def test_llm_engines_need_a_model() -> None:
    names = {engine["name"] for engine in _build_router().list_engines()}
    assert "llm_structured" not in names and "docfold_llm" not in names
