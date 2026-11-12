---
purpose: "Schema-less entity extraction"
status: "DONE"
priority: "P2"
created: "2026-11-12"
---

# Feature: extract_entities (#13)

`extract_entities(text, llm=, types=, instructions=, max_chars=)` returns
`[{type, value, attributes, chunks}]`. Long text is read in chunks; the same entity
(type and value, case and spacing ignored) is returned once with attributes merged.
A chunk whose answer does not parse adds nothing.

## Test Plan
- [x] entities merged across chunks, type filter, empty values dropped
- [x] unparseable answer and empty text give no entities
