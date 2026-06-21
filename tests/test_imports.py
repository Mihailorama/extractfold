from __future__ import annotations

import ast
from pathlib import Path

HEAVY_IMPORT_NAMES = {
    "anthropic",
    "openai",
    "google",
    "boto3",
    "azure",
    "instructor",
    "torch",
    "transformers",
    "vllm",
    "llama_cloud",
    "docfold",
}


def test_core_imports_without_optional_dependencies() -> None:
    import extractfold
    from extractfold import (
        SchemaConversionResult,
        TextChunk,
        chunk_text,
        extract_rows_chunked,
        infer_schema,
        template_to_schema,
    )
    from extractfold.engines.base import ExtractionEngine, ExtractionResult

    assert extractfold.__version__
    assert ExtractionEngine
    assert ExtractionResult
    assert TextChunk
    assert extract_rows_chunked
    assert chunk_text("abcdef", max_chars=3)[0].text == "abc"
    assert SchemaConversionResult
    assert infer_schema({"name": "Acme"}) == {
        "type": "object",
        "properties": {"name": {"type": "string"}},
    }
    assert template_to_schema({"name": {"type": "string"}}).schema["type"] == "object"


def test_engine_modules_do_not_import_heavy_dependencies_at_top_level() -> None:
    engine_dir = Path("src/extractfold/engines")
    offenders: list[str] = []
    for path in engine_dir.glob("*_engine.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in HEAVY_IMPORT_NAMES:
                        offenders.append(f"{path}:{alias.name}")
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in HEAVY_IMPORT_NAMES:
                    offenders.append(f"{path}:{node.module}")

    assert offenders == []
