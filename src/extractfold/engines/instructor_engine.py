"""Instructor library extraction adapter."""

from __future__ import annotations

import os
import time
from typing import Any

from extractfold.engines._common import (
    build_result,
    extract_data_payload,
    maybe_await,
    read_document_text,
)
from extractfold.engines.base import (
    ExtractionCapabilities,
    ExtractionEngine,
    ExtractionResult,
    load_schema,
)

_SUPPORTED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "tiff", "tif", "docx", "txt", "md"}


class InstructorEngine(ExtractionEngine):
    """Adapter for the `instructor` structured extraction library."""

    def __init__(
        self,
        provider: str = "openai",
        model: str | None = None,
        extractor: Any | None = None,
    ) -> None:
        self._provider = provider
        self._model = model or os.getenv("INSTRUCTOR_MODEL", "gpt-4.1")
        self._extractor = extractor

    @property
    def name(self) -> str:
        return "instructor"

    @property
    def supported_extensions(self) -> set[str]:
        return _SUPPORTED_EXTENSIONS

    @property
    def capabilities(self) -> ExtractionCapabilities:
        return ExtractionCapabilities(nested_schemas=True, batch=True, local=False, remote=True)

    def is_available(self) -> bool:
        if self._extractor is not None:
            return True
        try:
            import instructor  # noqa: F401
        except ImportError:
            return False
        return True

    async def extract(self, file_path: str, schema, **kwargs: Any) -> ExtractionResult:
        schema_obj = load_schema(schema)
        text = kwargs.pop("text", None) or read_document_text(file_path)
        start = time.perf_counter()
        if self._extractor is not None:
            raw = await maybe_await(
                self._extractor(text=text, schema=schema_obj, model=self._model, **kwargs)
            )
        else:
            raw = await maybe_await(self._call_instructor(text=text, schema=schema_obj, **kwargs))
        data = extract_data_payload(raw)
        return build_result(
            data=data,
            engine_name=self.name,
            schema=schema_obj,
            start=start,
            raw=raw,
            metadata={"provider": self._provider, "model": self._model},
        )

    def _call_instructor(self, *, text: str, schema: dict[str, Any], **kwargs: Any) -> Any:
        import instructor
        from openai import OpenAI

        client = instructor.from_openai(OpenAI())
        return client.chat.completions.create(
            model=self._model,
            response_model=dict,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract JSON conforming to this schema:\n"
                        f"{schema}\n\nDocument:\n{text}"
                    ),
                }
            ],
        )
