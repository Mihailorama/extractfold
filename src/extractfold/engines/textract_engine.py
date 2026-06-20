"""AWS Textract extraction adapter."""

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

_SUPPORTED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "tiff", "tif"}


class TextractEngine(ExtractionEngine):
    """Adapter for AWS Textract AnalyzeDocument QUERIES/FORMS."""

    def __init__(self, region_name: str | None = None, client: Any | None = None) -> None:
        self._region_name = region_name or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self._client = client

    @property
    def name(self) -> str:
        return "textract"

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
            import boto3

            return boto3.Session().get_credentials() is not None
        except Exception:
            return False

    async def extract(self, file_path: str, schema, **kwargs: Any) -> ExtractionResult:
        schema_obj = load_schema(schema)
        start = time.perf_counter()
        if self._client is not None:
            raw = await maybe_await(self._client(file_path=file_path, schema=schema_obj, **kwargs))
        else:
            raw = await maybe_await(self._call_textract(file_path, schema_obj, **kwargs))
        data, confidence, provenance = self._parse_blocks(raw)
        pages = None
        if isinstance(raw, dict):
            pages = raw.get("DocumentMetadata", {}).get("Pages")
        return build_result(
            data=data,
            engine_name=self.name,
            schema=schema_obj,
            start=start,
            raw=raw,
            field_confidence=confidence,
            provenance=provenance,
            metadata={"region": self._region_name},
            pages=pages if isinstance(pages, int) else None,
        )

    def _call_textract(
        self,
        file_path: str,
        schema: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        import boto3

        client = boto3.client("textract", region_name=self._region_name)
        queries = [
            {"Text": f"What is the {name}?", "Alias": name}
            for name in schema.get("properties", {})
        ]
        with open(file_path, "rb") as file_obj:
            request: dict[str, Any] = {
                "Document": {"Bytes": file_obj.read()},
                "FeatureTypes": ["FORMS", "QUERIES"],
            }
        if queries:
            request["QueriesConfig"] = {"Queries": queries}
        return client.analyze_document(**request)

    @staticmethod
    def _parse_blocks(raw: Any) -> tuple[dict[str, Any], dict[str, float], dict[str, Any]]:
        blocks = raw.get("Blocks", []) if isinstance(raw, dict) else []
        data: dict[str, Any] = {}
        confidence: dict[str, float] = {}
        provenance: dict[str, Any] = {}
        for block in blocks:
            if not isinstance(block, dict) or block.get("BlockType") != "QUERY_RESULT":
                continue
            query_raw = block.get("Query")
            query: dict[str, Any] = query_raw if isinstance(query_raw, dict) else {}
            alias = query.get("Alias") or block.get("Alias")
            if not alias:
                continue
            text = block.get("Text", "")
            data[str(alias)] = text
            if isinstance(block.get("Confidence"), (int, float)):
                confidence[str(alias)] = round(float(block["Confidence"]) / 100.0, 4)
            provenance[str(alias)] = {"page": block.get("Page"), "block_id": block.get("Id")}
        return data, confidence, provenance
