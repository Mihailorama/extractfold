"""Schema-first structured data extraction for documents."""

from __future__ import annotations

from extractfold.chunking import TextChunk, chunk_json_array, chunk_rows, chunk_sections, chunk_text
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
from extractfold.schema import SchemaConversionResult, infer_schema, template_to_schema

__version__ = "0.1.0"

__all__ = [
    "BatchExtractionResult",
    "ExtractionCapabilities",
    "ExtractionEngine",
    "ExtractionResult",
    "ExtractionRouter",
    "SchemaConversionResult",
    "SchemaValidationResult",
    "TextChunk",
    "__version__",
    "chunk_json_array",
    "chunk_rows",
    "chunk_sections",
    "chunk_text",
    "infer_schema",
    "load_schema",
    "template_to_schema",
    "validate_data",
]
