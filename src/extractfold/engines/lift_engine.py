"""Lift extraction engine adapter."""

from __future__ import annotations

import os
import time
from typing import Any

from extractfold.engines._common import (
    build_result,
    confidence_from_fields,
    extract_data_payload,
    maybe_await,
    provenance_from_fields,
)
from extractfold.engines.base import (
    ExtractionCapabilities,
    ExtractionEngine,
    ExtractionResult,
    load_schema,
)

_SUPPORTED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "tiff", "tif", "docx", "txt"}


class LiftEngine(ExtractionEngine):
    """Adapter for Datalab Lift-style schema extraction."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("LIFT_API_KEY") or os.getenv("DATALAB_API_KEY")
        self._endpoint = endpoint or os.getenv("LIFT_ENDPOINT", "https://api.datalab.to/v1/lift")
        self._client = client

    @property
    def name(self) -> str:
        return "lift"

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
            import requests  # noqa: F401
        except ImportError:
            return False
        return bool(self._api_key)

    async def extract(self, file_path: str, schema, **kwargs: Any) -> ExtractionResult:
        schema_obj = load_schema(schema)
        start = time.perf_counter()
        if self._client is not None:
            raw = await maybe_await(
                self._client(file_path=file_path, schema=schema_obj, engine=self.name, **kwargs)
            )
        else:
            raw = await maybe_await(self._invoke_lift(file_path, schema_obj, **kwargs))

        data = extract_data_payload(raw)
        pages = _pages_from_raw(raw)
        return build_result(
            data=data,
            engine_name=self.name,
            schema=schema_obj,
            start=start,
            raw=raw,
            field_confidence=confidence_from_fields(raw),
            provenance=provenance_from_fields(raw),
            metadata={"endpoint": self._endpoint},
            pages=pages,
        )

    def _invoke_lift(self, file_path: str, schema: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        import requests

        if not self._api_key:
            raise RuntimeError("LIFT_API_KEY or DATALAB_API_KEY is required")
        with open(file_path, "rb") as file_obj:
            response = requests.post(
                self._endpoint,
                headers={"Authorization": f"Bearer {self._api_key}"},
                files={"file": file_obj},
                data={"schema": schema},
                timeout=kwargs.get("timeout", 120),
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Lift response must be a JSON object")
        return payload


def _pages_from_raw(raw: Any) -> int | None:
    return raw.get("pages") if isinstance(raw, dict) and isinstance(raw.get("pages"), int) else None
