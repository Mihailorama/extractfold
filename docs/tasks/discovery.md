---
purpose: "Schema proposal, document-type classification and multi-file context"
status: "DONE"
priority: "P2"
created: "2026-11-12"
---

# Feature: schema proposal, classification, shared context (#12)

## Proposed Solution
`extractfold.discovery`, each with an injected `llm(prompt) -> str`:
- `propose_schema(llm=, samples=, attributes=, relational=)` → `{"tables": [{name,
  description, schema, primary_key, foreign_keys}]}`; one table unless relational; JSON
  types cleaned, keys pointing at unknown tables or fields dropped.
- `classify_document(text, profiles, llm=)` → `{document_type, profile, confidence,
  rationale}`; only a known profile id, else `None`.
- `shared_context(files, attributes, llm=)` → `{defaults, sources, context}`: attribute
  defaults stated once across files, each with its source file, plus prompt text.

## Test Plan
- [x] relational proposal cleaned; single table; nothing to go on raises
- [x] classification limited to known profiles, confidence clamped
- [x] defaults kept only with a value and a known source file
