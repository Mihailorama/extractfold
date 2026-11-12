---
purpose: "Per-field provenance and confidence in ProviderRouterEngine"
status: "DONE"
priority: "P1"
created: "2026-11-12"
---

# Feature: per-field provenance and confidence (#9)

## Problem
`ProviderRouterEngine` declared provenance and confidence unsupported, so a caller could
not show where a value came from (page, block and bounding box, or sheet cell) or how
sure the extraction is.

## Proposed Solution
- `extractfold.provenance.build_source_catalog(text, input_format=, blocks=)`: entries
  `{id, text, location..., start, end}`:
  - `blocks` (docfold `bounding_boxes`): `page`, `bbox`, `block_id`, `block_type`;
  - `spreadsheet` / `tsv`: one entry per non-empty cell, `Sheet!A1` ids;
  - `csv`: one entry per non-empty cell, `A1` ids;
  - `json`: one entry per scalar, `$.path` ids; `html`: block elements with `page`;
  - other text: paragraphs.
- `ProviderRouterEngine.extract_text(..., source_catalog=entries)`: appends the catalog
  and the citation rules to the prompt (the caller's prompt builder included), parses
  `{"rows", "provenance"}`, and fills `result.provenance` (`{"rows": [...]}` for rows,
  else a field map) and `result.field_confidence` (mean per field).
- `align_provenance(rows, provenance, catalog)`: `source_refs` become the cited entries'
  locations, unknown ids go to `unknown_refs`; confidence is re-scored against the cited
  text (empty 0; no source >= 0.2; source >= 0.4; equal 0.95; inside 0.8; containing 0.75;
  60% shared words 0.7).
- `extract_rows_chunked(source_catalog=)`: each chunk gets only the entries whose
  `start` falls inside it; provenance rows stay aligned with rows through de-duplication.

## Affected Files
- `src/extractfold/provenance.py` - new
- `src/extractfold/engines/provider_router_engine.py` - catalog prompt, provenance result
- `src/extractfold/text.py` - per-chunk catalog, aligned provenance

## Test Plan
- [x] catalogs for sheets, CSV, docfold blocks, text, JSON, HTML (offsets match the text)
- [x] alignment: locations, unknown refs, confidence rules
- [x] engine: catalog in prompt, provenance and field confidence on the result
- [x] chunked: catalog per chunk, provenance aligned after de-duplication

## Edge Cases
- Entries without offsets (blocks whose text is not found) go to every chunk.
- A CSV value with escaped quotes gets no offsets.

## Out of Scope
- Converting bbox coordinates between page units (docfold's job).
