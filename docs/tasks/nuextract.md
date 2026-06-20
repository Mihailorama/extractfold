---
purpose: "NuExtract open-model adapter"
status: "OPEN"
priority: "P1"
created: "2026-06-20"
---

# Feature: nuextract

## Problem
Users need a local/open extraction path that can run with Hugging Face or vLLM while still returning the same extractfold result shape.

## Proposed Solution
Add `NuExtractEngine` with lazy backend imports, configurable backend/model, JSON prompt construction, response parsing, and validation.

## Affected Files
- `src/extractfold/engines/nuextract_engine.py` - adapter
- `pyproject.toml` - `extractfold[nuextract]` extra

## Test Plan

### Unit / Functional Tests
- [ ] Stubbed backend returns valid extracted data.
- [ ] Capabilities advertise local execution and nested schema support.

### Integration / E2E Tests
- [ ] Skipped integration test for HF/vLLM real model execution.

### Test Commands
```bash
pytest tests/engines/test_nuextract_engine.py -v
```

## Edge Cases
- Model output may wrap JSON in prose or code fences.

## Out of Scope
- Bundling model weights.
