---
purpose: "Per-chunk quality checks, a truncation flag and a structured LLM-failure result"
status: "DONE"
priority: "P1"
created: "2026-11-12"
---

# Feature: chunk quality checks, truncation flag, structured LLM failure (#7)

## Problem
A caller replacing its own row-extraction loop needs, per chunk, the same response
checks it ran before accepting an answer, to know when an answer was cut at the token
limit, and to get a structured error instead of an exception when every model failed.

## Proposed Solution
- `extractfold.quality.check_rows(rows, columns=, expected_rows=, tolerance=0.5)` returns
  `[{check, status, message}]`: `row_count` (under half of expected fails, over 1.5x
  warns), `schema_compliance` (under half of the columns fails, some missing warns),
  `suspicious_patterns` (all empty / under 10% filled / all rows identical fails, a cut
  last row warns).
- `ProviderRouterEngine` unwraps chat-completion objects and `{"content", "finish_reason"}`
  dicts. `finish_reason` in `length` / `max_tokens` sets `metadata["truncated"]`; an
  unparseable truncated answer moves to the next model.
- `ProviderRouterEngine(raise_on_error=False)` returns `valid=False`, `data={}` and
  `metadata["error"] = {"stage": "llm", "model", "message"}` after the last model fails.
  Raising stays the default.
- `extract_rows_chunked` adds `checks` and `truncated` to every succeeded chunk and
  `truncated_chunks` to the summary; a structured LLM failure marks the chunk `failed`
  with `error_type="LLMError"`, `stage`, `model`, `error` and extraction goes on.

## Affected Files
- `src/extractfold/quality.py` - new
- `src/extractfold/engines/provider_router_engine.py` - answer envelope, `raise_on_error`
- `src/extractfold/text.py` - per-chunk checks, truncation, LLM failure

## Test Plan
- [x] `check_rows` pass / fail / warning cases for each check
- [x] chat-completion answer: content parsed, `finish_reason` and usage copied
- [x] truncated answer that parses is kept and flagged
- [x] truncated unparseable answer falls back to the next model
- [x] `raise_on_error=False` returns the structured error, no call settings leak
- [x] chunked extraction reports checks, truncation and a failed chunk's error

```bash
pytest tests/text/test_quality.py tests/engines/test_provider_router_engine.py tests/text/test_chunked_extraction.py -v
```

## Edge Cases
- Error messages come from the caller's exception text; never put secrets in them.

## Out of Scope
- Asking a truncated model to continue its answer (the next model is tried instead).
