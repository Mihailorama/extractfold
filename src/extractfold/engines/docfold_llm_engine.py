"""Composite docfold plus LLM structured extraction engine."""

from __future__ import annotations

import time
from typing import Any

from extractfold.engines._common import elapsed_ms, maybe_await
from extractfold.engines.base import (
    ExtractionCapabilities,
    ExtractionEngine,
    ExtractionResult,
    load_schema,
)
from extractfold.engines.llm_structured_engine import LLMStructuredEngine

_SUPPORTED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "tiff", "tif", "docx", "txt", "md", "html"}


class DocfoldLLMEngine(ExtractionEngine):
    """Use docfold for clean text first, then run LLM structured extraction."""

    def __init__(
        self,
        docfold_runner: Any | None = None,
        llm_engine: Any | None = None,
        docfold_engine: str | None = None,
    ) -> None:
        self._docfold_runner = docfold_runner
        self._llm_engine = llm_engine
        self._docfold_engine = docfold_engine

    @property
    def name(self) -> str:
        return "docfold_llm"

    @property
    def supported_extensions(self) -> set[str]:
        return _SUPPORTED_EXTENSIONS

    @property
    def capabilities(self) -> ExtractionCapabilities:
        return ExtractionCapabilities(nested_schemas=True, batch=True, local=False, remote=True)

    def is_available(self) -> bool:
        if self._docfold_runner is not None and self._llm_engine is not None:
            return True
        try:
            import docfold  # noqa: F401
        except ImportError:
            return False
        return LLMStructuredEngine().is_available()

    async def extract(self, file_path: str, schema, **kwargs: Any) -> ExtractionResult:
        schema_obj = load_schema(schema)
        start = time.perf_counter()
        content = await maybe_await(self._run_docfold(file_path, **kwargs))
        llm_engine = self._llm_engine or LLMStructuredEngine()
        if not hasattr(llm_engine, "extract_text"):
            raise RuntimeError("llm_engine must provide extract_text(text, schema, **kwargs)")
        llm_result = await maybe_await(llm_engine.extract_text(content, schema_obj, **kwargs))
        metadata = dict(llm_result.metadata)
        metadata.update(
            {
                "docfold_engine": self._docfold_engine or "auto",
                "docfold_content_length": len(content),
                "llm_engine": getattr(llm_engine, "name", "llm_structured"),
            }
        )
        return ExtractionResult(
            data=llm_result.data,
            engine_name=self.name,
            schema=schema_obj,
            field_confidence=llm_result.field_confidence,
            provenance=llm_result.provenance,
            valid=llm_result.valid,
            raw=llm_result.raw,
            metadata=metadata,
            pages=llm_result.pages,
            processing_time_ms=elapsed_ms(start),
        )

    async def _run_docfold(self, file_path: str, **kwargs: Any) -> str:
        if self._docfold_runner is not None:
            content = await maybe_await(self._docfold_runner(file_path, **kwargs))
            return str(content)

        from docfold.engines.base import OutputFormat
        from docfold.engines.router import EngineRouter

        router = EngineRouter()
        result = await router.process(
            file_path,
            output_format=OutputFormat.MARKDOWN,
            engine_hint=self._docfold_engine,
        )
        return result.content
