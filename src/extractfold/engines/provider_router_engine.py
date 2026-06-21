"""Dependency-free provider-router extraction adapter."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
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
    JsonSchema,
    load_schema,
)

_SUPPORTED_EXTENSIONS = {"txt", "md", "html", "json", "csv"}
_METADATA_KEYS = ("usage", "cost", "route")


class ProviderRouterEngine(ExtractionEngine):
    """Schema-guided extraction through an injected provider-router callable."""

    def __init__(
        self,
        provider: str = "default",
        model: str | None = None,
        provider_call: Callable[..., Any] | None = None,
        prompt_builder: Callable[..., str] | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._provider_call = provider_call
        self._prompt_builder = prompt_builder

    @property
    def name(self) -> str:
        return "provider_router"

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
        return self._provider_call is not None

    async def extract(self, file_path: str, schema, **kwargs: Any) -> ExtractionResult:
        text = kwargs.pop("text", None) or read_document_text(file_path)
        return await self.extract_text(text, schema, **kwargs)

    async def extract_text(
        self,
        text: str,
        schema: JsonSchema | str | Mapping[str, Any],
        **kwargs: Any,
    ) -> ExtractionResult:
        """Extract schema-conformant data from prepared text."""
        if self._provider_call is None:
            raise RuntimeError("provider_router requires an injected provider_call")

        schema_obj = load_schema(schema)
        prompt = self._prompt(text, schema_obj, **kwargs)
        start = time.perf_counter()
        raw = await maybe_await(
            self._provider_call(
                provider=self._provider,
                model=self._model,
                schema=schema_obj,
                text=text,
                prompt=prompt,
                **kwargs,
            )
        )
        return build_result(
            data=extract_data_payload(raw),
            engine_name=self.name,
            schema=schema_obj,
            start=start,
            raw=raw,
            metadata=self._metadata(raw),
        )

    def _prompt(self, text: str, schema: JsonSchema, **kwargs: Any) -> str:
        if self._prompt_builder is not None:
            return self._prompt_builder(
                text=text,
                schema=schema,
                provider=self._provider,
                model=self._model,
                **kwargs,
            )
        return (
            "Extract structured data from the source text. Return only JSON that conforms "
            "to this JSON Schema.\n\n"
            f"Schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
            f"Source text:\n{text}"
        )

    def _metadata(self, raw: Any) -> dict[str, Any]:
        metadata: dict[str, Any] = {"provider": self._provider, "model": self._model}
        payload = _model_dump(raw)
        if isinstance(payload, dict):
            nested_metadata = payload.get("metadata")
            if isinstance(nested_metadata, dict):
                metadata.update(nested_metadata)
            for key in _METADATA_KEYS:
                if key in payload:
                    metadata[key] = payload[key]
        return metadata


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return dumped
    return value
