---
purpose: "Canonical document profile output (sections, line items, quality metrics)"
status: "DONE"
priority: "P2"
created: "2026-11-12"
---

# Feature: canonical_extract (#15)

`canonical_extract(text, llm=, schema=, max_chars=, on_progress=)` returns
`{document_type, proposed_schema, header_fields, sections, line_items, quality, errors}`.
The first chunk proposes the schema unless one is given; later chunks must use it.
Header fields keep the first non-empty value, sections and line items are concatenated.
`quality`: header and line-item fill rates, counts, `check_rows` of the line items,
failed chunks. `on_progress(done, total)` lets a job runner report progress.

## Test Plan
- [x] chunks merged, schema carried to later chunks, bad chunk recorded, progress, quality
