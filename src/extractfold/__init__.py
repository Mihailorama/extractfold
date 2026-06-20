"""Schema-first structured data extraction for documents."""

from __future__ import annotations

from extractfold.engines.base import (
    BatchExtractionResult,
    ExtractionCapabilities,
    ExtractionEngine,
    ExtractionResult,
    ExtractionRouter,
    SchemaValidationResult,
    load_schema,
    validate_data,
)

__version__ = "0.1.0"

__all__ = [
    "BatchExtractionResult",
    "ExtractionCapabilities",
    "ExtractionEngine",
    "ExtractionResult",
    "ExtractionRouter",
    "SchemaValidationResult",
    "__version__",
    "load_schema",
    "validate_data",
]
