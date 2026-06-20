---
purpose: "Composite docfold-to-LLM extraction engine"
status: "OPEN"
priority: "P2"
created: "2026-06-20"
---

# Feature: docfold_llm

## Problem
extractfold should demonstrate the sibling relationship with docfold by converting documents to clean text/Markdown first and then extracting schema-conformant data.

## Proposed Solution
Add `DocfoldLLMEngine` that lazily imports docfold, runs a configurable docfold engine, then passes text to `LLMStructuredEngine`.

## Affected Files
- `src/extractfold/engines/docfold_llm_engine.py` - composite adapter
- `pyproject.toml` - `extractfold[docfold_llm]` extra

## Test Plan

### Unit / Functional Tests
- [ ] Stubbed docfold runner plus stubbed LLM runner returns valid data.
- [ ] Metadata records the intermediate docfold engine.

### Integration / E2E Tests
- [ ] Skipped real docfold + LLM run.

### Test Commands
```bash
pytest tests/engines/test_docfold_llm_engine.py -v
```

## Edge Cases
- docfold may return empty content or fail before LLM extraction.

## Out of Scope
- Reimplementing docfold parsing.
