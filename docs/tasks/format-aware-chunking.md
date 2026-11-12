---
purpose: "Format-aware chunking for spreadsheet/CSV/JSON/HTML and flat-JSON passthrough"
status: "DONE"
priority: "P1"
created: "2026-11-12"
---

# Feature: format-aware chunking (#8)

## Problem
Character-window chunks cut table rows, CSV records and HTML pages in half, lose the
CSV header and the current section header of a spreadsheet, and ignore how much a
model can read and write. Flat JSON that already has the target fields still pays for a
model call.

## Proposed Solution
- `chunk_document(text, input_format=, max_chars=, max_rows=None, max_pages=5)`:
  - `spreadsheet` / `tsv`: tab-separated lines; `Sheet: <name>` lines start a sheet and
    stay with its first row. `metadata["sheets"]` = `[{sheet, row_start, row_end}]`
    (1-based rows within the sheet). `metadata["context"]` names the sheet and the
    section header (last one-cell line) in effect where a chunk starts mid-sheet;
  - `csv`: records split outside quotes; the header line starts every chunk;
  - `json`: array items packed by characters and rows;
  - `html`: `<div class="page">` / `data-page-id` / `data-page` nodes, at most
    `max_pages` per chunk, `page_ids`; without page nodes, split after `</tr>`;
  - `markdown`: `chunk_sections`; other text: whole lines.
  - Every chunk carries `estimated_rows` (non-empty lines; HTML rows with >= 5 cells)
    and `row_start` / `row_end`.
- `chunk_budget(text, max_input_tokens=, max_output_tokens=, reserved_tokens=, fields=)`
  → `{max_chars, max_rows}` from the text's characters per token and the answer limit.
- `extract_rows_chunked(input_format=, max_rows=)` uses `chunk_document`; chunk
  `context` reaches the engine as `context=` (with the pre-scan context, #6).
- Flat JSON passthrough: a JSON array of objects whose keys are all schema fields and
  whose values validate is returned without a model call (`metadata["passthrough"]`).

## Affected Files
- `src/extractfold/chunking.py` - `chunk_document`, `chunk_budget`
- `src/extractfold/text.py` - `input_format`, `max_rows`, passthrough

## Test Plan
- [x] spreadsheet: rows whole, sheet ranges, carried sheet and section context
- [x] CSV: header on every chunk, quoted newline kept
- [x] HTML: page nodes, max pages, rows estimate
- [x] JSON: whole items within chars and rows
- [x] budget from model limits (Latin and Cyrillic)
- [x] spreadsheet and CSV through `ProviderRouterEngine` give the same rows as one chunk
- [x] flat JSON passthrough without a call; other keys still call the model

## Edge Cases
- A single row longer than `max_chars` stays whole in its own chunk.
- A one-cell data row is taken for a section header (same as before).

## Out of Scope
- Reading XLSX files (callers pass the sheet text).
