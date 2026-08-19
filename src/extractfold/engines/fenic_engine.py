"""typedef-ai fenic `semantic.extract` adapter."""

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
    JsonSchema,
    load_schema,
)

_SUPPORTED_EXTENSIONS = {"txt", "md", "html", "json", "csv"}

FieldSpec = tuple[str, bool, Any]


def _schema_to_field_specs(schema: JsonSchema) -> dict[str, FieldSpec]:
    """Flatten a JSON Schema object into ``{name: (kind, required, children)}``.

    ``children`` is ``None`` for scalars, a nested spec mapping for objects,
    and a single ``(kind, required, children)`` item spec for arrays.
    """
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    specs: dict[str, FieldSpec] = {}
    if not isinstance(properties, dict):
        return specs
    for name, field_schema in properties.items():
        if isinstance(field_schema, dict):
            specs[str(name)] = _field_spec(field_schema, str(name) in required)
    return specs


def _field_spec(field_schema: JsonSchema, required: bool) -> FieldSpec:
    kind = field_schema.get("type")
    if isinstance(kind, list):
        kind = next((item for item in kind if item != "null"), "string")
    if kind == "object" or "properties" in field_schema:
        return ("object", required, _schema_to_field_specs(field_schema))
    if kind == "array":
        items = field_schema.get("items")
        item_spec = _field_spec(items, True) if isinstance(items, dict) else ("string", True, None)
        return ("array", required, item_spec)
    return (str(kind or "string"), required, None)


class FenicEngine(ExtractionEngine):
    """Adapter for fenic's `semantic.extract` dataframe operator."""

    def __init__(
        self,
        model: str | None = None,
        session: Any | None = None,
        extractor: Any | None = None,
    ) -> None:
        self._model = model
        self._session = session
        self._extractor = extractor

    @property
    def name(self) -> str:
        return "fenic"

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
            import fenic  # noqa: F401
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
            raw = self._call_fenic(text=text, schema=schema_obj, **kwargs)
        data = extract_data_payload(raw)
        return build_result(
            data=data,
            engine_name=self.name,
            schema=schema_obj,
            start=start,
            raw=raw,
            metadata={"model": self._model},
        )

    def _call_fenic(self, *, text: str, schema: JsonSchema, **kwargs: Any) -> Any:
        import fenic as fc

        model_cls = _build_pydantic_model(schema, "ExtractfoldSchema")
        session = self._session or fc.Session.get_or_create(
            fc.SessionConfig(app_name="extractfold", semantic=self._semantic_config(fc))
        )
        df = session.create_dataframe([{"text": text}])
        rows = df.select(
            fc.semantic.extract("text", model_cls).alias("extracted")
        ).to_pylist()
        extracted = rows[0].get("extracted") if rows else {}
        if hasattr(extracted, "model_dump"):
            extracted = extracted.model_dump()
        if isinstance(extracted, dict):
            return {key: value for key, value in extracted.items() if value is not None}
        return extracted

    def _semantic_config(self, fc: Any) -> Any:
        # fenic requires per-provider rate limits; keep conservative defaults.
        if os.getenv("OPENAI_API_KEY"):
            language_model = fc.OpenAILanguageModel(
                model_name=self._model or "gpt-4o-mini", rpm=100, tpm=100_000
            )
        elif os.getenv("ANTHROPIC_API_KEY"):
            language_model = fc.AnthropicLanguageModel(
                model_name=self._model or "claude-haiku-4-5",
                rpm=100,
                input_tpm=100_000,
                output_tpm=100_000,
            )
        elif os.getenv("GOOGLE_API_KEY"):
            language_model = fc.GoogleDeveloperLanguageModel(
                model_name=self._model or "gemini-2.5-flash", rpm=100, tpm=100_000
            )
        else:
            raise RuntimeError(
                "fenic engine requires OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY"
            )
        return fc.SemanticConfig(
            language_models={"default": language_model},
            default_language_model="default",
        )


def _build_pydantic_model(schema: JsonSchema, name: str) -> Any:
    from pydantic import create_model

    fields: dict[str, Any] = {}
    for field_name, spec in _schema_to_field_specs(schema).items():
        annotation = _spec_to_annotation(spec, f"{name}_{field_name}")
        if spec[1]:
            fields[field_name] = (annotation, ...)
        else:
            fields[field_name] = (annotation | None, None)
    return create_model(name, **fields)


def _spec_to_annotation(spec: FieldSpec, name: str) -> Any:
    kind, _, children = spec
    if kind == "object" and isinstance(children, dict):
        from pydantic import create_model

        fields: dict[str, Any] = {}
        for field_name, child in children.items():
            annotation = _spec_to_annotation(child, f"{name}_{field_name}")
            fields[field_name] = (annotation, ...) if child[1] else (annotation | None, None)
        return create_model(name, **fields)
    if kind == "array":
        item = children if isinstance(children, tuple) else ("string", True, None)
        return list[_spec_to_annotation(item, f"{name}_item")]  # type: ignore[misc]
    return {
        "string": str,
        "number": float,
        "integer": int,
        "boolean": bool,
        "null": type(None),
    }.get(kind, str)
