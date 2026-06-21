"""Azure Document Intelligence extraction adapter."""

from __future__ import annotations

import os
import time
from typing import Any

from extractfold.engines._common import build_result, maybe_await
from extractfold.engines.base import (
    ExtractionCapabilities,
    ExtractionEngine,
    ExtractionResult,
    load_schema,
)

_SUPPORTED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "tiff", "tif", "bmp", "docx"}


class AzureDocIntEngine(ExtractionEngine):
    """Adapter for Azure Document Intelligence prebuilt/query-field extraction."""

    def __init__(
        self,
        endpoint: str | None = None,
        key: str | None = None,
        model_id: str = "prebuilt-layout",
        client: Any | None = None,
    ) -> None:
        self._endpoint = endpoint or os.getenv("AZURE_DOCINT_ENDPOINT")
        self._key = key or os.getenv("AZURE_DOCINT_KEY")
        self._model_id = model_id
        self._client = client

    @property
    def name(self) -> str:
        return "azure_docint"

    @property
    def supported_extensions(self) -> set[str]:
        return _SUPPORTED_EXTENSIONS

    @property
    def capabilities(self) -> ExtractionCapabilities:
        return ExtractionCapabilities(
            field_confidence=True,
            provenance=True,
            nested_schemas=False,
            batch=False,
            local=False,
            remote=True,
        )

    def is_available(self) -> bool:
        if self._client is not None:
            return True
        try:
            import azure.ai.documentintelligence  # noqa: F401
        except ImportError:
            return False
        return bool(self._endpoint and self._key)

    async def extract(self, file_path: str, schema, **kwargs: Any) -> ExtractionResult:
        schema_obj = load_schema(schema)
        start = time.perf_counter()
        if self._client is not None:
            raw = await maybe_await(
                self._client(
                    file_path=file_path,
                    schema=schema_obj,
                    model_id=self._model_id,
                    **kwargs,
                )
            )
        else:
            raw = await maybe_await(self._call_azure(file_path, schema_obj, **kwargs))
        data, confidence, provenance = self._parse_fields(raw)
        pages = _pages_from_raw(raw)
        return build_result(
            data=data,
            engine_name=self.name,
            schema=schema_obj,
            start=start,
            raw=raw,
            field_confidence=confidence,
            provenance=provenance,
            metadata={"model_id": self._model_id},
            pages=pages,
        )

    def _call_azure(self, file_path: str, schema: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
        from azure.core.credentials import AzureKeyCredential

        if not self._endpoint or not self._key:
            raise RuntimeError("AZURE_DOCINT_ENDPOINT and AZURE_DOCINT_KEY are required")
        client = DocumentIntelligenceClient(
            endpoint=self._endpoint,
            credential=AzureKeyCredential(self._key),
        )
        with open(file_path, "rb") as file_obj:
            poller = client.begin_analyze_document(
                self._model_id,
                AnalyzeDocumentRequest(bytes_source=file_obj.read()),
            )
        result = poller.result()
        fields: dict[str, Any] = {}
        for name in schema.get("properties", {}):
            fields[name] = {"value": getattr(result, "content", ""), "confidence": None}
        return {"fields": fields, "pages": len(getattr(result, "pages", []) or [])}

    @staticmethod
    def _parse_fields(raw: Any) -> tuple[dict[str, Any], dict[str, float], dict[str, Any]]:
        fields = raw.get("fields", {}) if isinstance(raw, dict) else {}
        data: dict[str, Any] = {}
        confidence: dict[str, float] = {}
        provenance: dict[str, Any] = {}
        for name, item in fields.items():
            if isinstance(item, dict):
                data[name] = item.get("value")
                if isinstance(item.get("confidence"), (int, float)):
                    confidence[name] = float(item["confidence"])
                provenance[name] = {
                    key: value
                    for key, value in item.items()
                    if key not in {"value", "confidence"}
                }
            else:
                data[name] = item
        return data, confidence, {key: value for key, value in provenance.items() if value}


def _pages_from_raw(raw: Any) -> int | None:
    return raw.get("pages") if isinstance(raw, dict) and isinstance(raw.get("pages"), int) else None
