---
purpose: "LlamaCloud Extract SaaS adapter"
status: "OPEN"
priority: "P2"
created: "2026-06-20"
---

# Feature: llamaextract

## Problem
LlamaCloud Extract is a managed extraction option that should share extractfold's contract and fallback behavior.

## Proposed Solution
Add `LlamaExtractEngine` with lazy LlamaCloud imports, API-key availability checks, file/schema submission, and response normalization.

## Affected Files
- `src/extractfold/engines/llamaextract_engine.py` - adapter
- `pyproject.toml` - `extractfold[llamaextract]` extra

## Test Plan

### Unit / Functional Tests
- [ ] Stubbed client response returns valid data.
- [ ] Capabilities mark remote execution and nested schemas.

### Integration / E2E Tests
- [ ] Skipped real SaaS run.

### Test Commands
```bash
pytest tests/engines/test_llamaextract_engine.py -v
```

## Edge Cases
- Client may return data under `data`, `result`, or `extraction`.

## Out of Scope
- Managing LlamaCloud projects.
