---
purpose: "Azure Document Intelligence extraction adapter"
status: "OPEN"
priority: "P2"
created: "2026-06-20"
---

# Feature: azure_docint

## Problem
Azure Document Intelligence provides prebuilt and query-field extraction that should be available through extractfold's schema-first API.

## Proposed Solution
Add `AzureDocIntEngine` with lazy Azure imports, environment-based credentials, query-field construction from schema properties, and normalized confidence/provenance.

## Affected Files
- `src/extractfold/engines/azure_docint_engine.py` - adapter
- `pyproject.toml` - `extractfold[azure_docint]` extra

## Test Plan

### Unit / Functional Tests
- [ ] Stubbed Azure result maps fields, confidence, and provenance.
- [ ] Availability requires SDK and endpoint/key.

### Integration / E2E Tests
- [ ] Skipped real Azure test.

### Test Commands
```bash
pytest tests/engines/test_azure_docint_engine.py -v
```

## Edge Cases
- Query fields may be missing or low confidence.

## Out of Scope
- Training custom extractors.
