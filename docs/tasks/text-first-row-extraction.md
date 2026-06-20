---
purpose: "Text-first row extraction and production-grade structured output utilities"
status: "OPEN"
priority: "P0"
created: "2026-06-20"
---

# Feature: text-first row extraction

## Problem
`extractfold` currently presents a document-first public contract:
`extract(file_path, schema) -> ExtractionResult`. That is the right stable
engine API, but production extraction systems often have already-prepared text,
Markdown, HTML, CSV, or JSON rows before schema-guided extraction begins.

Those workflows need a first-class text extraction layer, robust row-array
normalization, chunk planning, provenance, source catalogs, and evaluation
fixtures that measure structured arrays instead of only single objects.

## Proposed Solution
Add a source-neutral text-first layer without breaking the existing engine
contract. File engines keep implementing `ExtractionEngine.extract(...)`; engines
that can operate directly on prepared text also expose a documented
`TextExtractionEngine` protocol and helper functions.

The first milestone should make `extractfold` dependable for:

- prepared text -> schema-conformant object
- prepared text -> schema-conformant row array
- JSON template/sample -> JSON Schema conversion
- chunked extraction for long text and row-like inputs
- per-field and per-row provenance metadata
- source catalog construction from plain text, Markdown, HTML, CSV, and JSON
- benchmark fixtures for text/template/gold datasets

## Public API Shape

Keep the current public API intact:

```python
result = await engine.extract("document.pdf", schema)
```

Add text-first helpers:

```python
from extractfold.text import extract_text, extract_rows

result = await extract_text(text, schema, engine="llm_structured")
rows = await extract_rows(text, template, engine="llm_structured")
```

Add an optional protocol for engines with native text support:

```python
from typing import Any, Protocol

from extractfold.engines.base import ExtractionResult, JsonSchema


class TextExtractionEngine(Protocol):
    async def extract_text(
        self,
        text: str,
        schema: JsonSchema | str,
        **kwargs: Any,
    ) -> ExtractionResult:
        ...
```

Row extraction should preserve the existing `ExtractionResult.data: dict`
contract by wrapping arrays:

```python
ExtractionResult(
    data={"rows": [{"name": "Example"}]},
    ...
)
```

## Affected Files
- `src/extractfold/text.py` - public text-first helpers.
- `src/extractfold/schema.py` - template/sample to JSON Schema conversion.
- `src/extractfold/parsing.py` - robust JSON/object/array response parsing.
- `src/extractfold/chunking.py` - chunk planning for long text and row-like inputs.
- `src/extractfold/provenance.py` - source catalog and provenance normalization.
- `src/extractfold/prescan.py` - pre-scan dataclasses and parser.
- `src/extractfold/engines/llm_structured_engine.py` - align existing `extract_text`.
- `src/extractfold/engines/text_template_engine.py` - add a local text/template engine path.
- `src/extractfold/evaluation/metrics.py` - add row-array metrics.
- `src/extractfold/evaluation/runner.py` - support text/template/gold fixture layout.
- `pyproject.toml` - add optional extras for local engines, provider routing, and parser helpers.
- `tests/text/` - text-first API, parsing, schema conversion, chunking, provenance.
- `tests/engines/` - stubbed text-mode engine tests.
- `tests/evaluation/` - row-array benchmark and metrics tests.

## Milestones

### Milestone 1: Text-first core API
- Add `extract_text(...)` and `extract_rows(...)` helpers.
- Keep `ExtractionResult.data` as a dict by wrapping row arrays under `rows`.
- Detect engines that expose `extract_text`; otherwise route through temporary
  text files only where the engine already supports text-like extensions.
- Add tests proving the existing file-first API still works unchanged.

### Milestone 2: Schema and template conversion
- Convert JSON samples/templates into JSON Schema.
- Treat flat arrays as row schemas.
- Preserve field descriptions, required fields, enums, and primitive types.
- Exclude computed fields from extraction while keeping them visible in metadata.

### Milestone 3: Parsing and repair
- Parse raw model responses that contain:
  - a JSON object
  - a JSON array
  - fenced JSON
  - prose-wrapped JSON
  - `{"rows": [...]}`
  - `{"data": {"rows": [...]}}`
- Keep parser helpers dependency-free in core.
- Put optional repair libraries behind an extra.

### Milestone 4: Chunk planning and execution
- Add deterministic chunk plans before adding model calls.
- Support character/token budget chunks, row-aware chunks, JSON-array-aware chunks,
  Markdown/HTML section chunks, and spreadsheet-like row windows.
- Include overlap and previous-chunk digest metadata so callers can deduplicate.
- Add parallel chunk execution later through engine helpers, not core imports.

### Milestone 5: Provenance and source catalogs
- Build source catalogs from text, Markdown, HTML, CSV, and JSON.
- Normalize per-field provenance with source refs, confidence, and rationale.
- Support row-level provenance aligned with `data["rows"]`.
- Keep source catalogs in `ExtractionResult.provenance` or metadata, not in `data`.

### Milestone 6: Pre-scan utilities
- Add dataclasses for detected columns, document structure, control values, and
  suggested chunk boundaries.
- Add a parser that safely returns an empty pre-scan result on malformed output.
- Keep provider calls outside core and behind engine-specific adapters.

### Milestone 7: Engine and router expansion
- Add a text-oriented local engine behind an optional extra.
- Expand existing local text/template support behind optional extras.
- Add a provider-routing engine behind an optional extra for chat model routing
  without making any provider SDK a core dependency.
- Add router signals for local/remote preference, text length, schema shape,
  nested arrays, provenance requirement, and expected row count.

### Milestone 8: Evaluation and benchmark fixtures
- Support datasets shaped as:

```text
dataset/
  cases/
    invoice_rows/
      input_text.txt
      template.json
      ground_truth.json
```

- Report row count accuracy, per-field precision/recall/F1, value similarity,
  type correctness, hallucination rate, array alignment, schema compliance,
  latency, and cost metadata where engines provide it.

## Test Plan

### Unit / Functional Tests
- [ ] Text helper uses a stub engine with `extract_text`.
- [ ] Text helper preserves file-first router behavior for existing engines.
- [ ] Row helper wraps arrays as `{"rows": [...]}`.
- [ ] Template conversion infers object fields from a sample object.
- [ ] Template conversion infers row schema from a sample array.
- [ ] Computed fields are removed from extraction schema and retained in metadata.
- [ ] Parser recovers fenced JSON objects.
- [ ] Parser recovers fenced JSON arrays.
- [ ] Parser unwraps `rows`, `data.rows`, and `result.rows`.
- [ ] Parser rejects non-JSON responses with a clear error.
- [ ] Chunk planner does not split JSON array objects when avoidable.
- [ ] Chunk planner keeps row windows within configured limits.
- [ ] Source catalog creates stable refs for Markdown sections.
- [ ] Source catalog creates stable refs for CSV rows and columns.
- [ ] Provenance aligns one provenance map per extracted row.
- [ ] Pre-scan parser returns typed control values from valid JSON.
- [ ] Pre-scan parser returns an empty result for malformed JSON.
- [ ] Evaluation runner scores text/template/gold datasets.
- [ ] Router honors provenance-required and local-only constraints.

### Integration / E2E Tests
- [ ] Skipped integration test for local text-engine model weights.
- [ ] Skipped integration test for local template-mode model weights.
- [ ] Skipped integration test for provider-router credentials.
- [ ] CLI benchmark accepts the text/template/gold fixture layout.

### Test Commands
```bash
pytest tests/text/ -v
pytest tests/engines/test_text_template_engine.py -v
pytest tests/evaluation/ -v
ruff check src/ tests/
mypy src/
pytest tests/ -m "not integration"
```

## Edge Cases
- Very long text that exceeds the selected model context window.
- Empty input text.
- Input text that is already a JSON array.
- Rows that are split across chunk boundaries.
- Duplicate rows produced by overlapping chunks.
- Required fields that are missing in some rows.
- Nested arrays inside each extracted row.
- Currency, number, and date normalization.
- Source refs that point to repeated identical text.
- Engines that return partial data plus invalid JSON around it.

## Out of Scope
- Service routers, authentication, storage, billing, and job orchestration.
- Application-specific model registries.
- Database persistence or report-file generation.
- Mandatory network calls in unit tests.
- Making heavy model, cloud, or provider SDKs required core dependencies.
