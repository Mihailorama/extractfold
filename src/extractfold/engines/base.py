"""Base contract and router for structured extraction engines."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

JsonSchema = dict[str, Any]


_BUILTIN_SCHEMAS: dict[str, JsonSchema] = {
    "invoice": {
        "type": "object",
        "required": ["invoice_id"],
        "properties": {
            "invoice_id": {"type": "string"},
            "vendor": {"type": "string"},
            "date": {"type": "string"},
            "total": {"type": "number"},
            "currency": {"type": "string"},
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "quantity": {"type": "number"},
                        "amount": {"type": "number"},
                    },
                },
            },
        },
    },
    "receipt": {
        "type": "object",
        "properties": {
            "merchant": {"type": "string"},
            "date": {"type": "string"},
            "total": {"type": "number"},
            "tax": {"type": "number"},
        },
    },
}


@dataclass(frozen=True)
class ExtractionCapabilities:
    """Capabilities an extraction engine can populate in :class:`ExtractionResult`."""

    field_confidence: bool = False
    provenance: bool = False
    nested_schemas: bool = False
    batch: bool = False
    local: bool = False
    remote: bool = False

    def to_dict(self) -> dict[str, bool]:
        """Serialize capabilities to a plain dictionary."""
        return asdict(self)


@dataclass
class SchemaValidationResult:
    """Result returned by the lightweight JSON-Schema validator."""

    valid: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Unified result returned by every structured extraction engine."""

    data: dict[str, Any]
    engine_name: str
    schema: JsonSchema
    field_confidence: dict[str, float] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    valid: bool = True
    raw: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    pages: int | None = None
    processing_time_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe plain dictionary."""
        return {
            "data": self.data,
            "engine_name": self.engine_name,
            "schema": self.schema,
            "field_confidence": self.field_confidence,
            "provenance": self.provenance,
            "valid": self.valid,
            "raw": self.raw,
            "metadata": self.metadata,
            "pages": self.pages,
            "processing_time_ms": self.processing_time_ms,
        }


class ExtractionEngine(ABC):
    """Abstract base class every extraction adapter must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique lowercase engine identifier."""
        ...

    @property
    @abstractmethod
    def supported_extensions(self) -> set[str]:
        """File extensions supported by the engine, without leading dots."""
        ...

    @abstractmethod
    async def extract(
        self,
        file_path: str,
        schema: JsonSchema | str | Mapping[str, Any],
        **kwargs: Any,
    ) -> ExtractionResult:
        """Extract schema-conformant data from a document."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return whether runtime dependencies and credentials are available."""
        ...

    @property
    def capabilities(self) -> ExtractionCapabilities:
        """Declare what enrichments this engine can populate."""
        return ExtractionCapabilities()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} available={self.is_available()}>"


def load_schema(schema: JsonSchema | str | Mapping[str, Any]) -> JsonSchema:
    """Load a JSON Schema from a dict, JSON string, file path, or named reference."""
    if isinstance(schema, Mapping):
        return deepcopy(dict(schema))

    if not isinstance(schema, str):
        raise TypeError("schema must be a mapping, JSON string, path, or named reference")

    raw = schema.strip()
    if raw.startswith("{") or raw.startswith("["):
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("schema JSON must decode to an object")
        return parsed

    path = Path(raw).expanduser()
    if path.exists():
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError(f"schema file must decode to an object: {path}")
        return parsed

    if raw in _BUILTIN_SCHEMAS:
        return deepcopy(_BUILTIN_SCHEMAS[raw])

    raise ValueError(f"Unknown schema reference: {schema}")


def validate_data(
    data: Any,
    schema: JsonSchema | str | Mapping[str, Any],
) -> SchemaValidationResult:
    """Validate common JSON-Schema keywords without adding a core dependency.

    The validator intentionally supports the subset most extraction schemas need:
    ``type``, ``required``, ``properties``, and array ``items``. Complex schemas
    can still be passed to engines; unsupported keywords are ignored here.
    """
    schema_obj = load_schema(schema)
    errors: list[str] = []
    _validate_node(data, schema_obj, "$", errors)
    return SchemaValidationResult(valid=not errors, errors=errors)


def _validate_node(value: Any, schema: JsonSchema, path: str, errors: list[str]) -> None:
    expected = schema.get("type")
    if expected and not _matches_type(value, expected):
        errors.append(f"{path}: expected {expected}, got {type(value).__name__}")
        return

    if expected == "object" or "properties" in schema:
        if not isinstance(value, dict):
            errors.append(f"{path}: expected object, got {type(value).__name__}")
            return
        for required in schema.get("required", []):
            if required not in value:
                errors.append(f"{path}.{required}: required field missing")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, dict):
                    _validate_node(value[key], child_schema, f"{path}.{key}", errors)

    if expected == "array":
        if not isinstance(value, list):
            errors.append(f"{path}: expected array, got {type(value).__name__}")
            return
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_node(item, item_schema, f"{path}[{index}]", errors)


def _matches_type(value: Any, expected: str | list[str]) -> bool:
    if isinstance(expected, list):
        return any(_matches_type(value, item) for item in expected)

    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


_DEFAULT_PRIORITY = [
    "lift",
    "llm_structured",
    "docfold_llm",
    "llamaextract",
    "azure_docint",
    "google_docai",
    "textract",
    "nuextract",
    "instructor",
]

_EXTENSION_PRIORITY: dict[str, list[str]] = {
    "pdf": _DEFAULT_PRIORITY,
    "png": _DEFAULT_PRIORITY,
    "jpg": _DEFAULT_PRIORITY,
    "jpeg": _DEFAULT_PRIORITY,
    "tiff": _DEFAULT_PRIORITY,
    "tif": _DEFAULT_PRIORITY,
    "docx": _DEFAULT_PRIORITY,
    "txt": ["nuextract", "llm_structured", "docfold_llm", "instructor", "lift"],
    "md": ["nuextract", "llm_structured", "docfold_llm", "instructor", "lift"],
    "html": ["llm_structured", "docfold_llm", "instructor", "lift"],
}


@dataclass
class BatchExtractionResult:
    """Result of processing multiple files."""

    results: dict[str, ExtractionResult] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    total_time_ms: int = 0

    @property
    def success_rate(self) -> float:
        return self.succeeded / self.total if self.total else 0.0


class ExtractionRouter:
    """Selects engines via hint, environment default, priority, and fallback."""

    def __init__(
        self,
        engines: list[ExtractionEngine] | None = None,
        fallback_order: list[str] | None = None,
        allowed_engines: set[str] | None = None,
    ) -> None:
        self._engines: dict[str, ExtractionEngine] = {}
        self._fallback_order = fallback_order
        self._allowed_engines = allowed_engines
        for engine in engines or []:
            self.register(engine)

    def register(self, engine: ExtractionEngine) -> None:
        self._engines[engine.name] = engine

    def get(self, name: str) -> ExtractionEngine | None:
        return self._engines.get(name)

    def _get_priority(self, ext: str) -> list[str]:
        if self._fallback_order is not None:
            return self._fallback_order
        return _EXTENSION_PRIORITY.get(ext, _DEFAULT_PRIORITY)

    def _is_candidate(self, engine: ExtractionEngine, ext: str) -> bool:
        if self._allowed_engines and engine.name not in self._allowed_engines:
            return False
        if not engine.is_available():
            return False
        if ext and ext not in engine.supported_extensions:
            return False
        return True

    def select(
        self,
        file_path: str,
        engine_hint: str | None = None,
        **kwargs: Any,
    ) -> ExtractionEngine:
        ext = Path(file_path).suffix.lstrip(".").lower()

        if engine_hint:
            engine = self._engines.get(engine_hint)
            if engine is None:
                available = ", ".join(self._engines)
                raise ValueError(f"Unknown engine '{engine_hint}'. Available: {available}")
            if not engine.is_available():
                raise RuntimeError(f"Engine '{engine_hint}' is registered but not available.")
            return engine

        for env_name in ("EXTRACTFOLD_ENGINE", "ENGINE_DEFAULT"):
            env_default = os.getenv(env_name)
            if env_default:
                engine = self._engines.get(env_default)
                if engine and self._is_candidate(engine, ext):
                    return engine

        for name in self._get_priority(ext):
            engine = self._engines.get(name)
            if engine and self._is_candidate(engine, ext):
                return engine

        for engine in self._engines.values():
            if self._is_candidate(engine, ext):
                return engine

        raise ValueError(
            f"No available engine supports '.{ext}'. Registered: {list(self._engines.keys())}"
        )

    def _candidates(self, file_path: str) -> list[ExtractionEngine]:
        ext = Path(file_path).suffix.lstrip(".").lower()
        candidates: list[ExtractionEngine] = []
        seen: set[str] = set()
        for name in self._get_priority(ext):
            engine = self._engines.get(name)
            if engine and engine.name not in seen and self._is_candidate(engine, ext):
                candidates.append(engine)
                seen.add(engine.name)
        for engine in self._engines.values():
            if engine.name not in seen and self._is_candidate(engine, ext):
                candidates.append(engine)
                seen.add(engine.name)
        return candidates

    async def extract(
        self,
        file_path: str,
        schema: JsonSchema | str | Mapping[str, Any],
        engine_hint: str | None = None,
        **kwargs: Any,
    ) -> ExtractionResult:
        if engine_hint:
            engine = self.select(file_path, engine_hint=engine_hint, **kwargs)
            return await engine.extract(file_path, load_schema(schema), **kwargs)

        candidates = self._candidates(file_path)
        if not candidates:
            return await self.select(file_path).extract(file_path, load_schema(schema), **kwargs)

        errors: list[tuple[str, Exception]] = []
        for engine in candidates:
            try:
                return await engine.extract(file_path, load_schema(schema), **kwargs)
            except Exception as exc:
                logger.warning("Engine '%s' failed on '%s': %s", engine.name, file_path, exc)
                errors.append((engine.name, exc))

        summary = "; ".join(f"{name}: {exc}" for name, exc in errors)
        raise RuntimeError(f"All engines failed for '{file_path}'. Errors: {summary}")

    async def extract_batch(
        self,
        file_paths: list[str],
        schema: JsonSchema | str | Mapping[str, Any],
        engine_hint: str | None = None,
        concurrency: int = 3,
        on_progress: Callable[..., Any] | None = None,
        **kwargs: Any,
    ) -> BatchExtractionResult:
        start = time.perf_counter()
        batch = BatchExtractionResult(total=len(file_paths))
        semaphore = asyncio.Semaphore(concurrency)

        async def _run_one(index: int, file_path: str) -> None:
            async with semaphore:
                try:
                    result = await self.extract(
                        file_path,
                        schema,
                        engine_hint=engine_hint,
                        **kwargs,
                    )
                    batch.results[file_path] = result
                    batch.succeeded += 1
                    if on_progress:
                        on_progress(
                            current=index + 1,
                            total=batch.total,
                            file_path=file_path,
                            status="completed",
                            result=result,
                            error=None,
                        )
                except Exception as exc:
                    batch.errors[file_path] = str(exc)
                    batch.failed += 1
                    if on_progress:
                        on_progress(
                            current=index + 1,
                            total=batch.total,
                            file_path=file_path,
                            status="failed",
                            result=None,
                            error=exc,
                        )

        await asyncio.gather(*[_run_one(i, fp) for i, fp in enumerate(file_paths)])
        batch.total_time_ms = int((time.perf_counter() - start) * 1000)
        return batch

    async def compare(
        self,
        file_path: str,
        schema: JsonSchema | str | Mapping[str, Any],
        engines: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, ExtractionResult]:
        targets: list[ExtractionEngine] = []
        ext = Path(file_path).suffix.lstrip(".").lower()
        if engines:
            for name in engines:
                engine = self._engines.get(name)
                if engine and engine.is_available():
                    targets.append(engine)
        else:
            targets = [
                engine
                for engine in self._engines.values()
                if self._is_candidate(engine, ext)
            ]

        results: dict[str, ExtractionResult] = {}
        for engine in targets:
            try:
                results[engine.name] = await engine.extract(
                    file_path,
                    load_schema(schema),
                    **kwargs,
                )
            except Exception:
                logger.exception("Engine '%s' failed during compare", engine.name)
        return results

    def list_engines(self) -> list[dict[str, Any]]:
        return [
            {
                "name": engine.name,
                "available": engine.is_available(),
                "extensions": sorted(engine.supported_extensions),
                "capabilities": engine.capabilities.to_dict(),
            }
            for engine in self._engines.values()
        ]
