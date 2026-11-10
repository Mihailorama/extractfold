---
purpose: "Cross-provider model fallback chain in provider_router; row extraction that keeps repeated line items and runs chunks concurrently"
status: "DONE"
priority: "P1"
created: "2026-11-10"
---

# Feature: model fallback chain and production row extraction

## Problem
A caller that extracts table rows from documents (first user: Datatera ai-utils, where
each pipeline step picks its own model) needs:

- a per-step model **fallback chain** across providers, so an outage, rate limit or an
  unparseable / truncated answer moves to the next model instead of failing the step;
- line items that legitimately repeat (two identical positions in one act) to survive
  `extract_rows_chunked`, which de-duplicated every identical row;
- long documents to extract several chunks at once.

## Proposed Solution
- `ProviderRouterEngine(models=[...])`: an ordered chain passed one by one as `model=`
  to the injected `provider_call` (names, or dicts of call settings). A model that
  raises or answers without parseable JSON hands the call to the next one; the last
  error is raised. `metadata["model"]` names the model that answered and
  `metadata["fallbacks"]` lists the failures (names only, never call settings).
  Without `models` the engine behaves as before (`[model]`).
- `extract_rows_chunked(..., dedupe=True, concurrency=1)`: `dedupe=False` keeps identical
  rows; `concurrency > 1` extracts that many chunks at once, rows stay in chunk order,
  engines then get no `previous_chunk_digest`.

## Affected Files
- `src/extractfold/engines/provider_router_engine.py` - `models` chain
- `src/extractfold/text.py` - `dedupe`, `concurrency`
- `tests/engines/test_provider_router_engine.py`, `tests/text/test_chunked_extraction.py`

## Test Plan
- [x] chain falls back to the next model; metadata names the answering model, not its settings
- [x] every model failing raises the last error
- [x] an unparseable answer moves to the next model
- [x] `dedupe=False` keeps identical rows
- [x] `concurrency=3` overlaps three chunks and keeps chunk order

## Edge Cases
- A dict model entry carries API keys: only its `model` name reaches metadata.
- `continue_on_error` with concurrency: failures are reported per chunk in order.

## Out of Scope
- Provider-specific error classification (any exception moves on).
