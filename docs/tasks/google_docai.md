---
purpose: "Google Document AI extraction adapter"
status: "OPEN"
priority: "P2"
created: "2026-06-20"
---

# Feature: google_docai

## Problem
Google Document AI custom extractors and form parsers should fit the same extractfold engine contract.

## Proposed Solution
Add `GoogleDocAIEngine` with lazy imports, processor configuration, schema-field mapping, and normalized entity provenance.

## Affected Files
- `src/extractfold/engines/google_docai_engine.py` - adapter
- `pyproject.toml` - `extractfold[google_docai]` extra

## Test Plan

### Unit / Functional Tests
- [ ] Stubbed Document AI result maps entities into data.
- [ ] Capabilities mark remote confidence and provenance support.

### Integration / E2E Tests
- [ ] Skipped real processor run.

### Test Commands
```bash
pytest tests/engines/test_google_docai_engine.py -v
```

## Edge Cases
- Entity names may not exactly match schema property names.

## Out of Scope
- Processor creation or training.
