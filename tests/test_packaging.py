from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python < 3.11
    import tomli as tomllib


def test_pyproject_declares_required_extras_and_console_script() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert data["project"]["dependencies"] == []
    assert data["project"]["scripts"]["extractfold"] == "extractfold.cli:main"

    extras = data["project"]["optional-dependencies"]
    assert any(item.startswith("tomli") for item in extras["test"])
    for name in [
        "lift",
        "nuextract",
        "provider_router",
        "llm_structured",
        "instructor",
        "llamaextract",
        "azure_docint",
        "google_docai",
        "textract",
        "docfold_llm",
        "evaluation",
        "test",
        "dev",
        "all",
    ]:
        assert name in extras
