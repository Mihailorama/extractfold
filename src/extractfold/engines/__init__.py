"""Extraction engine adapters."""

from __future__ import annotations

from extractfold.engines.azure_docint_engine import AzureDocIntEngine
from extractfold.engines.base import ExtractionEngine, ExtractionResult, ExtractionRouter
from extractfold.engines.docfold_llm_engine import DocfoldLLMEngine
from extractfold.engines.google_docai_engine import GoogleDocAIEngine
from extractfold.engines.instructor_engine import InstructorEngine
from extractfold.engines.lift_engine import LiftEngine
from extractfold.engines.llamaextract_engine import LlamaExtractEngine
from extractfold.engines.llm_structured_engine import LLMStructuredEngine
from extractfold.engines.nuextract_engine import NuExtractEngine
from extractfold.engines.textract_engine import TextractEngine

__all__ = [
    "AzureDocIntEngine",
    "DocfoldLLMEngine",
    "ExtractionEngine",
    "ExtractionResult",
    "ExtractionRouter",
    "GoogleDocAIEngine",
    "InstructorEngine",
    "LiftEngine",
    "LLMStructuredEngine",
    "LlamaExtractEngine",
    "NuExtractEngine",
    "TextractEngine",
]
