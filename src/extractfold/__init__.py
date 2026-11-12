"""Schema-first structured data extraction for documents."""

from __future__ import annotations

from extractfold.chunking import (
    TextChunk,
    chunk_budget,
    chunk_document,
    chunk_json_array,
    chunk_rows,
    chunk_sections,
    chunk_text,
)
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
from extractfold.prescan import PreScan, prescan
from extractfold.provenance import align_provenance, build_source_catalog
from extractfold.quality import check_rows
from extractfold.schema import SchemaConversionResult, infer_schema, template_to_schema
from extractfold.text import extract_rows_chunked

__version__ = "0.2.0"

__all__ = [
    "BatchExtractionResult",
    "ExtractionCapabilities",
    "ExtractionEngine",
    "ExtractionResult",
    "ExtractionRouter",
    "PreScan",
    "SchemaConversionResult",
    "SchemaValidationResult",
    "TextChunk",
    "__version__",
    "align_provenance",
    "build_source_catalog",
    "chunk_json_array",
    "chunk_rows",
    "chunk_sections",
    "check_rows",
    "chunk_budget",
    "chunk_document",
    "chunk_text",
    "extract_rows_chunked",
    "infer_schema",
    "load_schema",
    "prescan",
    "template_to_schema",
    "validate_data",
]
