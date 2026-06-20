"""LlamaCloud Extract adapter."""

from __future__ import annotations

import os
import time
from typing import Any

from extractfold.engines._common import build_result, extract_data_payload, maybe_await
from extractfold.engines.base import (
    ExtractionCapabilities,
    ExtractionEngine,
    ExtractionResult,
    load_schema,
)

_SUPPORTED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "tiff", "tif", "docx", "txt"}


class LlamaExtractEngine(ExtractionEngine):
    """Adapter for LlamaCloud Extract SaaS."""

    def __init__(self, api_key: str | None = None, client: Any | None = None) -> None:
        self._api_key = api_key or os.getenv("LLAMA_CLOUD_API_KEY")
        self._client = client

    @property
    def name(self) -> str:
        return "llamaextract"

    @property
    def supported_extensions(self) -> set[str]:
        return _SUPPORTED_EXTENSIONS

    @property
    def capabilities(self) -> ExtractionCapabilities:
        return ExtractionCapabilities(
            field_confidence=False,
            provenance=False,
            nested_schemas=True,
            batch=True,
            local=False,
            remote=True,
        )

    def is_available(self) -> bool:
        if self._client is not None:
            return True
        try:
            import llama_cloud_services  # noqa: F401
        except ImportError:
            return False
        return bool(self._api_key)

    async def extract(self, file_path: str, schema, **kwargs: Any) -> ExtractionResult:
        schema_obj = load_schema(schema)
        start = time.perf_counter()
        if self._client is not None:
            raw = await maybe_await(
                self._client(
                    file_path=file_path,
                    schema=schema_obj,
                    api_key=self._api_key,
                    **kwargs,
                )
            )
        else:
            raw = await maybe_await(self._call_llamaextract(file_path, schema_obj, **kwargs))
        data = extract_data_payload(raw)
        pages = _pages_from_raw(raw)
        return build_result(
            data=data,
            engine_name=self.name,
            schema=schema_obj,
            start=start,
            raw=raw,
            metadata={"service": "llama_cloud_extract"},
            pages=pages,
        )

    def _call_llamaextract(self, file_path: str, schema: dict[str, Any], **kwargs: Any) -> Any:
        from llama_cloud_services import LlamaExtract

        if not self._api_key:
            raise RuntimeError("LLAMA_CLOUD_API_KEY is required")
        extractor = LlamaExtract(api_key=self._api_key)
        agent = extractor.create_agent(
            name=kwargs.get("agent_name", "extractfold"),
            data_schema=schema,
        )
        return agent.extract(file_path)


def _pages_from_raw(raw: Any) -> int | None:
    return raw.get("pages") if isinstance(raw, dict) and isinstance(raw.get("pages"), int) else None
