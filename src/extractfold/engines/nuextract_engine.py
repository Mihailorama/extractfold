"""NuExtract open-model extraction adapter."""

from __future__ import annotations

import time
from typing import Any

from extractfold.engines._common import (
    build_result,
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

_SUPPORTED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "tiff", "tif", "docx", "txt", "md"}


class NuExtractEngine(ExtractionEngine):
    """Adapter for NuExtract via Hugging Face or vLLM backends."""

    def __init__(
        self,
        model: str = "numind/NuExtract-2.0-8B",
        backend: str = "hf",
        backend_runner: Any | None = None,
    ) -> None:
        self._model = model
        self._backend = backend
        self._backend_runner = backend_runner

    @property
    def name(self) -> str:
        return "nuextract"

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
            local=True,
            remote=False,
        )

    def is_available(self) -> bool:
        if self._backend_runner is not None:
            return True
        try:
            if self._backend == "vllm":
                import vllm  # noqa: F401
            else:
                import transformers  # noqa: F401
        except ImportError:
            return False
        return True

    async def extract(self, file_path: str, schema, **kwargs: Any) -> ExtractionResult:
        schema_obj = load_schema(schema)
        text = kwargs.pop("text", None) or read_document_text(file_path)
        start = time.perf_counter()
        if self._backend_runner is not None:
            raw = await maybe_await(
                self._backend_runner(
                    text=text,
                    schema=schema_obj,
                    model=self._model,
                    backend=self._backend,
                    **kwargs,
                )
            )
        else:
            raw = await maybe_await(self._run_backend(text=text, schema=schema_obj, **kwargs))
        data = parse_json_object(raw) if isinstance(raw, str) else dict(raw)
        return build_result(
            data=data,
            engine_name=self.name,
            schema=schema_obj,
            start=start,
            raw=raw,
            metadata={"model": self._model, "backend": self._backend},
        )

    def _run_backend(self, *, text: str, schema: dict[str, Any], **kwargs: Any) -> str:
        if self._backend == "vllm":
            from vllm import LLM, SamplingParams

            llm = LLM(model=self._model)
            result = llm.generate([self._prompt(text, schema)], SamplingParams(temperature=0))
            return result[0].outputs[0].text

        from transformers import AutoModelForCausalLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(self._model)
        model = AutoModelForCausalLM.from_pretrained(self._model)
        inputs = tokenizer(self._prompt(text, schema), return_tensors="pt")
        output = model.generate(**inputs, max_new_tokens=kwargs.get("max_new_tokens", 2048))
        return str(tokenizer.decode(output[0], skip_special_tokens=True))

    @staticmethod
    def _prompt(text: str, schema: dict[str, Any]) -> str:
        return (
            "Extract the document into JSON matching this schema.\n"
            f"Schema:\n{schema}\n\nDocument:\n{text}\n\nJSON:"
        )
