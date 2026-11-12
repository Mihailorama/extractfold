---
purpose: "Fast repair of truncated or malformed LLM JSON"
status: "DONE"
priority: "P2"
created: "2026-11-12"
---

# Feature: parse_llm_json (#16)

## Problem
Callers run pure-Python `json_repair` on every large model answer, about 0.5 s per
truncated large answer, because extractfold only parsed clean JSON.

## Proposed Solution
- `parse_llm_json(text) -> (data, repaired)`: strip fences; parse with orjson when
  installed, else stdlib, also inside prose (never skipping the opening bracket). On
  failure: a dependency-free closer that cuts back to the last closed object/array or
  top-level comma and closes the open brackets; when that yields nothing and
  `json_repair` is installed, `json_repair.loads`.
- `fast_json` extra: `orjson`, `json_repair`. Base dependencies stay empty.
- `ProviderRouterEngine(repair_json=True)`: an unparseable answer is repaired instead of
  falling back; `metadata["repaired"] = True`.
- Benchmark script `benchmarks/json_repair_bench.py`, results in `docs/benchmarks.md`.

## Affected Files
- `src/extractfold/parsing.py`, `src/extractfold/engines/provider_router_engine.py`
- `pyproject.toml`, `benchmarks/json_repair_bench.py`, `docs/benchmarks.md`

## Test Plan
- [x] clean answers (fenced, in prose) are not marked repaired
- [x] truncated answers keep complete elements only (strings with brackets, escapes)
- [x] other damage goes to json_repair when installed (skipped otherwise)
- [x] engine repairs a truncated answer with `repair_json=True`

## Edge Cases
- An answer cut inside its first row repairs to an empty list of rows.

## Out of Scope
- A Rust-backed repair port: the built-in closer already removes the cost for truncation.
