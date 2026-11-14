---
purpose: "No silent row loss when a chunk's answer is cut at the token limit"
status: "DONE"
priority: "P1"
created: "2026-11-14"
---

# Fix: truncated chunk answers (EXTRACTFOLD-1)

## Problem
`extract_rows_chunked` kept a chunk answer cut at the token limit (repaired JSON or a
parseable prefix) and only counted it in `truncated_chunks`; the result stayed `valid`
and the chunk's tail rows were gone.

## Proposed Solution
A truncated chunk is split in two at the line break nearest its middle and each half is
extracted again, halving again up to `split_truncated` levels (default 2, `0` off). A csv
chunk's header (`metadata["header"]`) starts both halves and is left out of their document
offsets; header-less chunks get no extra context. The split answer replaces the original
when it adds at least as many rows after dedupe; `raw` stays the original answer and the
pieces (span, raw, metadata) and summed usage go to the chunk's `split`. A chunk still truncated is listed in
`chunking["truncated_chunk_indexes"]` and makes the result `partial` and not `valid`.

## Affected Files
- `src/extractfold/text.py` - split, merge, flags

## Test Plan
- [x] `test_extract_rows_chunked_splits_a_truncated_chunk_and_keeps_its_tail_rows`
- [x] `test_extract_rows_chunked_flags_a_chunk_still_truncated_after_splitting`

## Edge Cases
- A chunk without a line break cannot be split: flagged.
- An engine that raises on an unparseable truncated answer fails the chunk as before.

## Out of Scope
- Engines that do not report truncation (`metadata["truncated"]`) are not detected.
