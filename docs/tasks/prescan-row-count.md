---
purpose: "Pre-scan pass and row-count control with re-run of short chunks"
status: "DONE"
priority: "P1"
created: "2026-11-12"
---

# Feature: pre-scan and row-count control (#6)

## Problem
Row extraction loses rows silently: a chunk answer can stop early and nothing compares
the result with what the document says it holds (a row count, a total). A caller
replacing its own pipeline needs the pre-scan step and the re-run of short chunks.

## Proposed Solution
- `prescan(text, llm=, columns=, instructions=)`: one call of an injected
  `llm(prompt) -> str` over the first and last 3,000 characters. Returns `PreScan`
  (`columns`, `column_types`, `structure`, `control_values`, `boundaries`, `error`) with
  `expected_rows` (first `row_count` control value with confidence >= 0.8) and
  `context()` for prompts. A failed call returns an empty `PreScan` with `error`.
- `extract_rows_chunked(prescan=, rerun_below=, rerun_engine=)`:
  - the pre-scan context (and a chunk's own `metadata["context"]`) is passed to every
    chunk call as `context=`;
  - a chunk's expected rows: `chunk.metadata["estimated_rows"]`, or the pre-scan's
    `expected_rows` when there is one chunk; the chunk's `row_count` check uses it;
  - a chunk under `rerun_below * expected` rows is extracted again with `rerun_engine`
    (default: the same engine); the longer answer is kept;
  - counts: per chunk `expected_rows`, `rerun = {engine, rows, kept}`; summary
    `rerun_chunks`; `metadata["row_count"] = {expected, extracted, status, message}` and
    `metadata["prescan"]`.

## Affected Files
- `src/extractfold/prescan.py` - new
- `src/extractfold/text.py` - context, expected rows, re-run, counts
- `src/extractfold/engines/provider_router_engine.py` - default prompt shows `context`

## Test Plan
- [x] pre-scan prompt holds head, tail, instructions, columns; answer parsed
- [x] a failed pre-scan returns an empty result with the error
- [x] only a confident row count becomes `expected_rows`
- [x] a short chunk is re-run with the re-run engine and the longer answer kept
- [x] a re-run that is not longer keeps the first answer; row-count check fails

## Edge Cases
- Several chunks without `estimated_rows`: the document count is not split across
  chunks; only the document-level `row_count` is reported.

## Out of Scope
- Checking sums against control values (data-quality rules, #11).
