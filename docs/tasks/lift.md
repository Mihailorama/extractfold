---
purpose: "Reference extraction adapter for Datalab Lift-style responses"
status: "OPEN"
priority: "P1"
created: "2026-06-20"
---

# Feature: lift

## Problem
`lift` is the reference implementation for extractfold's engine contract and must define the adapter pattern for schema loading, validation, confidence, provenance, raw payloads, and lazy optional dependencies.

## Proposed Solution
Implement `LiftEngine` behind `ExtractionEngine`. Keep SDK/network imports inside methods, accept dependency-injected callables for unit tests, and normalize responses into `ExtractionResult`.

## Affected Files
- `src/extractfold/engines/lift_engine.py` - adapter and response normalization
- `src/extractfold/engines/__init__.py` - public export
- `pyproject.toml` - `extractfold[lift]` extra

## Test Plan

### Unit / Functional Tests
- [ ] Stubbed response returns schema-conformant `ExtractionResult`.
- [ ] Missing optional dependency or credentials reports unavailable.

### Integration / E2E Tests
- [ ] Skipped integration test documents the real Lift run prerequisites.

### Test Commands
```bash
pytest tests/engines/test_lift_engine.py -v
```

## Edge Cases
- Raw response may contain JSON string or nested result object.
- Engine may return partial confidence/provenance maps.

## Out of Scope
- Downloading model weights or making network calls in unit tests.
