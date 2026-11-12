---
purpose: "Row post-processing: merge, mandatory-field filter, computed fields, reference-list mapping"
status: "DONE"
priority: "P1"
created: "2026-11-12"
---

# Feature: row post-processing (#10)

## Problem
After extraction a caller merges duplicate or partial rows, drops rows without
mandatory values, fills computed fields and maps values to a reference list, and needs
to know what each step changed.

## Proposed Solution
`extractfold.postprocess`, each step returns `(rows, {"step", "changed", "changes"})` and
never edits its input:
- `drop_rows_missing(rows, mandatory)`: drops rows with an empty mandatory value (`""`,
  `None`, `N/A`, `-`, `no information found`).
- `merge_rows(rows, key=, llm=)`: groups by key fields (all rows without `key`); merges a
  group field by field (first non-empty wins) or with one `llm` call per group, falling
  back to the field merge when the answer invents fields or does not parse.
- `compute_fields(rows, fields, llm=)`: a field's `compute(row)` callable, or one `llm`
  call per row for the remaining fields (name, type, description, samples).
- `map_to_reference(rows, field, reference, value_key=, threshold=, llm=, other=)`: exact
  match (case and spacing ignored), then string similarity, then one `llm` call for all
  distinct unmatched values (only list entries accepted), then `other`.

## Test Plan
- [x] each step: result rows, change record, input untouched
- [x] merge: model answer used, invented fields fall back
- [x] compute: local callable, one model call per row, no `llm` raises
- [x] map: exact, similar, model and `other` paths

## Out of Scope
- Reading the merge, mandatory or classifier settings from a caller's own attribute format.
