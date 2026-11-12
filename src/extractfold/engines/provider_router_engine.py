"""Dependency-free provider-router extraction adapter."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
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
from extractfold.parsing import parse_json_payload, parse_llm_json
from extractfold.provenance import align_provenance, catalog_prompt, field_confidence

_SUPPORTED_EXTENSIONS = {"txt", "md", "html", "json", "csv"}
_METADATA_KEYS = ("usage", "cost", "route")
_TRUNCATED = {"length", "max_tokens"}


class ProviderRouterEngine(ExtractionEngine):
    """Schema-guided extraction through an injected provider-router callable."""

    def __init__(
        self,
        provider: str = "default",
        model: str | None = None,
        provider_call: Callable[..., Any] | None = None,
        prompt_builder: Callable[..., str] | None = None,
        models: Sequence[Any] | None = None,
        raise_on_error: bool = True,
        repair_json: bool = False,
    ) -> None:
        """*models* is an ordered fallback chain passed one by one as ``model=`` to
        *provider_call* (names, or dicts of call settings such as an API key). A model
        that raises or answers without parseable JSON hands the call to the next one.

        *provider_call* may return the payload itself (dict, list, JSON text), a chat
        completion (``choices[0].message.content`` / ``finish_reason``) or a dict with
        ``content`` and ``finish_reason``. An answer cut at the token limit is kept when
        it still parses (``metadata["truncated"]``), otherwise the next model is tried.

        With ``raise_on_error=False`` a failure of the last model returns an invalid
        result with ``metadata["error"] = {"stage": "llm", "model", "message"}``.

        With ``repair_json=True`` an answer that does not parse (cut at the token limit,
        a missing bracket) is repaired by :func:`extractfold.parsing.parse_llm_json`
        instead of moving to the next model; ``metadata["repaired"]`` says so."""
        self._provider = provider
        self._model = model
        self._models: list[Any] = list(models) if models else [model]
        self._provider_call = provider_call
        self._prompt_builder = prompt_builder
        self._raise_on_error = raise_on_error
        self._repair_json = repair_json

    @property
    def name(self) -> str:
        return "provider_router"

    @property
    def supported_extensions(self) -> set[str]:
        return _SUPPORTED_EXTENSIONS

    @property
    def capabilities(self) -> ExtractionCapabilities:
        return ExtractionCapabilities(
            field_confidence=True,
            provenance=True,
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
        catalog = kwargs.get("source_catalog")
        if catalog:
            prompt = f"{prompt}\n\n{catalog_prompt(catalog)}"
        start = time.perf_counter()
        fallbacks: list[dict[str, Any]] = []
        for index, model in enumerate(self._models):
            try:
                raw = await maybe_await(
                    self._provider_call(
                        provider=self._provider,
                        model=model,
                        schema=schema_obj,
                        text=text,
                        prompt=prompt,
                        **kwargs,
                    )
                )
                content, finish_reason, usage = _unwrap(raw)
                truncated = finish_reason in _TRUNCATED
                repaired = False
                try:
                    data = extract_data_payload(content)
                except ValueError as exc:
                    if self._repair_json and isinstance(content, str):
                        content, repaired = parse_llm_json(content)
                        data = extract_data_payload(content)
                    elif truncated:
                        raise ValueError(f"answer truncated at the token limit: {exc}") from exc
                    else:
                        raise
            except Exception as exc:
                failure = {"model": _model_name(model), "error": str(exc)[:300]}
                if index < len(self._models) - 1:
                    fallbacks.append(failure)
                    continue
                if self._raise_on_error:
                    raise
                return self._failure(schema_obj, start, failure, fallbacks)
            provenance, confidence = _provenance(content, data, catalog) if catalog else ({}, {})
            metadata = self._metadata(raw)
            metadata["model"] = _model_name(model)
            if finish_reason is not None:
                metadata["finish_reason"] = finish_reason
                metadata["truncated"] = truncated
            if repaired:
                metadata["repaired"] = True
            if usage is not None and "usage" not in metadata:
                metadata["usage"] = usage
            if fallbacks:
                metadata["fallbacks"] = fallbacks
            return build_result(
                data=data,
                engine_name=self.name,
                schema=schema_obj,
                start=start,
                raw=raw,
                metadata=metadata,
                provenance=provenance,
                field_confidence=confidence,
            )
        raise RuntimeError("provider_router has no model to call")

    def _failure(
        self,
        schema: JsonSchema,
        start: float,
        failure: dict[str, Any],
        fallbacks: list[dict[str, Any]],
    ) -> ExtractionResult:
        metadata: dict[str, Any] = {
            "provider": self._provider,
            "model": failure["model"],
            "error": {"stage": "llm", "model": failure["model"], "message": failure["error"]},
        }
        if fallbacks:
            metadata["fallbacks"] = fallbacks
        result = build_result(
            data={}, engine_name=self.name, schema=schema, start=start, raw=None, metadata=metadata
        )
        result.valid = False
        return result

    def _prompt(self, text: str, schema: JsonSchema, **kwargs: Any) -> str:
        if self._prompt_builder is not None:
            return self._prompt_builder(
                text=text,
                schema=schema,
                provider=self._provider,
                model=self._model,
                **kwargs,
            )
        context = kwargs.get("context")
        return (
            "Extract structured data from the source text. Return only JSON that conforms "
            "to this JSON Schema.\n\n"
            f"Schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
            + (f"Context:\n{context}\n\n" if context else "")
            + f"Source text:\n{text}"
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


def _model_name(model: Any) -> Any:
    """A model's name for metadata: never copy call settings (API keys) out of a dict."""
    return model.get("model") if isinstance(model, Mapping) else model


def _provenance(
    content: Any, data: dict[str, Any], catalog: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], dict[str, float]]:
    """Per-field provenance of an answer: ``{"rows": [...]}`` for rows, else field map."""
    parsed = parse_json_payload(content) if isinstance(content, str) else _model_dump(content)
    cited = parsed.get("provenance") if isinstance(parsed, dict) else None
    rows = data.get("rows")
    if isinstance(rows, list):
        aligned = align_provenance(rows, cited, catalog)
        return {"rows": aligned}, field_confidence(aligned)
    aligned = align_provenance([data], cited if isinstance(cited, list) else [cited], catalog)
    return aligned[0], field_confidence(aligned)


def _unwrap(raw: Any) -> tuple[Any, str | None, Any]:
    """(payload, finish_reason, usage) of a provider answer."""
    choices = getattr(raw, "choices", None)
    if choices:
        choice = choices[0]
        message = getattr(choice, "message", None)
        return getattr(message, "content", None) or "", choice.finish_reason, getattr(
            raw, "usage", None
        )
    if isinstance(raw, Mapping) and "finish_reason" in raw and "content" in raw:
        return raw["content"], raw["finish_reason"], raw.get("usage")
    return raw, None, None


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return dumped
    return value
