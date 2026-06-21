"""Google Document AI extraction adapter."""

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

_SUPPORTED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "tiff", "tif", "gif", "bmp", "webp"}


class GoogleDocAIEngine(ExtractionEngine):
    """Adapter for Google Document AI custom extractor or form parser processors."""

    def __init__(
        self,
        project_id: str | None = None,
        location: str | None = None,
        processor_id: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._project_id = project_id or os.getenv("GOOGLE_DOCAI_PROJECT_ID")
        self._location = location or os.getenv("GOOGLE_DOCAI_LOCATION", "us")
        self._processor_id = processor_id or os.getenv("GOOGLE_DOCAI_PROCESSOR_ID")
        self._client = client

    @property
    def name(self) -> str:
        return "google_docai"

    @property
    def supported_extensions(self) -> set[str]:
        return _SUPPORTED_EXTENSIONS

    @property
    def capabilities(self) -> ExtractionCapabilities:
        return ExtractionCapabilities(
            field_confidence=True,
            provenance=True,
            nested_schemas=True,
            batch=False,
            local=False,
            remote=True,
        )

    def is_available(self) -> bool:
        if self._client is not None:
            return True
        try:
            from google.cloud import documentai  # noqa: F401
        except ImportError:
            return False
        return bool(self._project_id and self._processor_id)

    async def extract(self, file_path: str, schema, **kwargs: Any) -> ExtractionResult:
        schema_obj = load_schema(schema)
        start = time.perf_counter()
        if self._client is not None:
            raw = await maybe_await(
                self._client(
                    file_path=file_path,
                    schema=schema_obj,
                    processor_id=self._processor_id,
                )
            )
        else:
            raw = await maybe_await(self._call_docai(file_path, schema_obj, **kwargs))
        data, confidence, provenance = self._parse_entities(raw)
        pages = _pages_from_raw(raw)
        return build_result(
            data=data,
            engine_name=self.name,
            schema=schema_obj,
            start=start,
            raw=raw,
            field_confidence=confidence,
            provenance=provenance,
            metadata={"processor_id": self._processor_id, "location": self._location},
            pages=pages,
        )

    def _call_docai(self, file_path: str, schema: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        from google.cloud import documentai

        if not self._project_id or not self._processor_id:
            raise RuntimeError("GOOGLE_DOCAI_PROJECT_ID and GOOGLE_DOCAI_PROCESSOR_ID are required")
        client = documentai.DocumentProcessorServiceClient()
        name = client.processor_path(self._project_id, self._location, self._processor_id)
        with open(file_path, "rb") as file_obj:
            raw_document = documentai.RawDocument(
                content=file_obj.read(),
                mime_type=kwargs.get("mime_type", "application/pdf"),
            )
        response = client.process_document(
            request=documentai.ProcessRequest(name=name, raw_document=raw_document)
        )
        entities = []
        for entity in response.document.entities:
            entities.append(
                {
                    "type": entity.type_,
                    "mention_text": entity.mention_text,
                    "confidence": entity.confidence,
                }
            )
        return {"entities": entities, "pages": len(response.document.pages)}

    @staticmethod
    def _parse_entities(raw: Any) -> tuple[dict[str, Any], dict[str, float], dict[str, Any]]:
        entities = raw.get("entities", []) if isinstance(raw, dict) else []
        data: dict[str, Any] = {}
        confidence: dict[str, float] = {}
        provenance: dict[str, Any] = {}
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            name = str(entity.get("type") or entity.get("name") or "")
            if not name:
                continue
            data[name] = entity.get(
                "normalized_value",
                entity.get("mention_text", entity.get("value")),
            )
            if isinstance(entity.get("confidence"), (int, float)):
                confidence[name] = float(entity["confidence"])
            provenance[name] = {
                key: value
                for key, value in entity.items()
                if key
                not in {"type", "name", "mention_text", "normalized_value", "value", "confidence"}
            }
        return data, confidence, {key: value for key, value in provenance.items() if value}


def _pages_from_raw(raw: Any) -> int | None:
    return raw.get("pages") if isinstance(raw, dict) and isinstance(raw.get("pages"), int) else None
