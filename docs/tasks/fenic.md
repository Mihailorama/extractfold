---
purpose: "fenic (typedef-ai) semantic extraction adapter"
status: "OPEN"
priority: "P2"
created: "2026-08-19"
---

# Feature: fenic

## Problem
Users who run typedef-ai's `fenic` dataframe framework (https://github.com/typedef-ai/fenic)
should be able to use its `semantic.extract` operator behind extractfold's unified contract.

## Proposed Solution
Add `FenicEngine` with lazy imports, JSON-Schema-to-Pydantic conversion for
`semantic.extract`, injectable extractor callable for tests, and standard result
normalization via `build_result`.

## Affected Files
- `src/extractfold/engines/fenic_engine.py` - adapter
- `src/extractfold/engines/__init__.py` - export
- `src/extractfold/cli.py` - router registration
- `pyproject.toml` - `extractfold[fenic]` extra
- `docs/tasks/fenic.md` - this document

## Test Plan

### Unit / Functional Tests
- [ ] Stubbed fenic extractor response becomes a valid `ExtractionResult`.
- [ ] Availability is false when `fenic` is absent, true with an injected extractor.
- [ ] Capabilities report remote + nested schemas + batch.
- [ ] Default router registers the engine.
- [ ] JSON Schema converts to Pydantic field specs (types, required, nesting).

### Integration / E2E Tests
- [ ] Skipped real fenic session test.

### Test Commands
```bash
pytest tests/engines/test_fenic_engine.py -v
pytest tests/engines/test_engine_roster.py -v
```

## Edge Cases
- `semantic.extract` needs a Pydantic model; JSON Schema must be converted lazily.
- Optional fields (not in `required`) must map to `Optional[...] = None`.
- Extraction returns a struct column; missing values should be dropped, not kept as None.

## Out of Scope
- Requiring `fenic` or Pydantic in the core package.
- fenic's own document parsing/markdown operators; the adapter feeds document text.
