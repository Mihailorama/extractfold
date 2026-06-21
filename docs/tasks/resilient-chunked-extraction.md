---
purpose: "Add opt-in resilient chunk execution for text-first row extraction."
status: "OPEN"
priority: "P1"
created: "2026-06-21"
---

# Feature: resilient chunked extraction

## Problem
Long prepared-text extraction often runs as a sequence of chunks. A single chunk
can fail because the model output is malformed, the provider rejects a request,
or a transient error occurs. The current helper raises immediately, which is the
right default, but production callers also need an opt-in mode that returns
successful rows plus explicit failure metadata for retry and audit decisions.

## Proposed Solution
Extend `extract_rows_chunked(...)` with `continue_on_error=False` by default.
When false, existing exception behavior remains unchanged. When true, the helper
will:

- Catch per-chunk exceptions.
- Record failed chunk metadata with error type, error message, row counters, and
  previous-chunk digest.
- Preserve successful rows and duplicate removal from other chunks.
- Return an aggregate `ExtractionResult` with `valid=False` when any chunk fails.
- Include `succeeded_chunks`, `failed_chunks`, and `partial` in chunking metadata.
- Keep `raw` aligned to the chunk plan by inserting error payloads for failures.

## Affected Files
- `src/extractfold/text.py` - chunk execution and aggregate metadata.
- `tests/text/test_chunked_extraction.py` - resilient chunk tests.

## Test Plan

### Unit / Functional Tests
- [ ] Default behavior still raises when a chunk fails.
- [ ] `continue_on_error=True` returns successful rows and failed chunk metadata.
- [ ] Failed chunks make the aggregate result invalid.
- [ ] Raw results stay aligned with chunk order.

### Integration / E2E Tests
- [ ] Not required; unit tests use stub engines and no network.

### Test Commands
```bash
pytest tests/text/test_chunked_extraction.py -v
pytest tests/ -m "not integration"
```

## Edge Cases
- First chunk fails and later chunks succeed.
- Consecutive chunks fail.
- A failed chunk should not create a duplicate digest or duplicate rows.
- Existing callers that do not pass `continue_on_error` must keep current
  exception behavior.

## Out of Scope
- Automatic retry policy.
- Parallel chunk execution.
- Provider-specific error classification.
