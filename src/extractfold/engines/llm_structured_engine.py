"""Provider-agnostic LLM structured-output extraction."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from extractfold.engines._common import (
    build_result,
    extract_data_payload,
    maybe_await,
    parse_json_object,
    read_document_text,
)
from extractfold.engines.base import (
    ExtractionCapabilities,
    ExtractionEngine,
    ExtractionResult,
    load_schema,
)

DEFAULT_ANTHROPIC_MODEL = "claude-fable-5"
_SUPPORTED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "tiff", "tif", "docx", "txt", "md", "html"}


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract a JSON object from raw model text."""
    return parse_json_object(text)


class LLMStructuredEngine(ExtractionEngine):
    """Schema-guided extraction through Anthropic, OpenAI, or Gemini."""

    def __init__(
        self,
        provider: str = "anthropic",
        model: str | None = None,
        provider_call: Any | None = None,
    ) -> None:
        self._provider = provider
        self._model = model or self._default_model(provider)
        self._provider_call = provider_call

    @property
    def name(self) -> str:
        return "llm_structured"

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
        if self._provider_call is not None:
            return True
        try:
            if self._provider == "anthropic":
                import anthropic  # noqa: F401

                return bool(os.getenv("ANTHROPIC_API_KEY"))
            if self._provider == "openai":
                import openai  # noqa: F401

                return bool(os.getenv("OPENAI_API_KEY"))
            if self._provider == "gemini":
                import google.genai  # noqa: F401

                return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        except ImportError:
            return False
        return False

    async def extract(self, file_path: str, schema, **kwargs: Any) -> ExtractionResult:
        text = kwargs.pop("text", None) or read_document_text(file_path)
        return await self.extract_text(text, schema, **kwargs)

    async def extract_text(self, text: str, schema, **kwargs: Any) -> ExtractionResult:
        schema_obj = load_schema(schema)
        start = time.perf_counter()
        if self._provider_call is not None:
            raw = await maybe_await(
                self._provider_call(
                    provider=self._provider,
                    model=self._model,
                    schema=schema_obj,
                    text=text,
                    **kwargs,
                )
            )
        else:
            raw = await maybe_await(self._call_provider(text=text, schema=schema_obj, **kwargs))
        data = extract_data_payload(raw)
        return build_result(
            data=data,
            engine_name=self.name,
            schema=schema_obj,
            start=start,
            raw=raw,
            metadata={"provider": self._provider, "model": self._model},
        )

    def _call_provider(self, *, text: str, schema: dict[str, Any], **kwargs: Any) -> Any:
        prompt = self._prompt(text, schema)
        if self._provider == "anthropic":
            return self._call_anthropic(prompt, schema, **kwargs)
        if self._provider == "openai":
            return self._call_openai(prompt, schema, **kwargs)
        if self._provider == "gemini":
            return self._call_gemini(prompt, schema, **kwargs)
        raise ValueError(f"Unsupported LLM provider: {self._provider}")

    def _call_anthropic(self, prompt: str, schema: dict[str, Any], **kwargs: Any) -> Any:
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=self._model,
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 0),
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(getattr(block, "text", "") for block in response.content)
        return extract_json_object(text)

    def _call_openai(self, prompt: str, schema: dict[str, Any], **kwargs: Any) -> Any:
        from openai import OpenAI

        client = OpenAI()
        response = client.responses.create(
            model=self._model,
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "extractfold_schema",
                    "schema": schema,
                    "strict": False,
                }
            },
            temperature=kwargs.get("temperature", 0),
        )
        return extract_json_object(response.output_text)

    def _call_gemini(self, prompt: str, schema: dict[str, Any], **kwargs: Any) -> Any:
        from google import genai

        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        response = client.models.generate_content(
            model=self._model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": schema,
                "temperature": kwargs.get("temperature", 0),
            },
        )
        return extract_json_object(response.text)

    @staticmethod
    def _default_model(provider: str) -> str:
        if provider == "anthropic":
            return os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
        if provider == "openai":
            return os.getenv("OPENAI_MODEL", "gpt-4.1")
        if provider == "gemini":
            return os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
        return "unknown"

    @staticmethod
    def _prompt(text: str, schema: dict[str, Any]) -> str:
        return (
            "Extract structured data from the document. Return only JSON that conforms "
            "to this JSON Schema.\n\n"
            f"Schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
            f"Document:\n{text}"
        )
