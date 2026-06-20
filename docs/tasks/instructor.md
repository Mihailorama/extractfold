---
purpose: "Instructor-library extraction adapter"
status: "OPEN"
priority: "P2"
created: "2026-06-20"
---

# Feature: instructor

## Problem
Users who already rely on `instructor` should be able to run Pydantic/JSON-Schema extraction behind extractfold's unified contract.

## Proposed Solution
Add `InstructorEngine` with lazy imports, schema-to-model fallback behavior, injectable client call for tests, and standard result normalization.

## Affected Files
- `src/extractfold/engines/instructor_engine.py` - adapter
- `pyproject.toml` - `extractfold[instructor]` extra

## Test Plan

### Unit / Functional Tests
- [ ] Stubbed instructor response becomes `ExtractionResult`.
- [ ] Availability is false when optional dependencies are absent.

### Integration / E2E Tests
- [ ] Skipped real model/instructor test.

### Test Commands
```bash
pytest tests/engines/test_instructor_engine.py -v
```

## Edge Cases
- Response object may expose `model_dump` rather than plain dict.

## Out of Scope
- Requiring Pydantic in the core package.
