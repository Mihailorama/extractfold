---
purpose: "Code-generation table extraction with sandboxed execution"
status: "DONE"
priority: "P2"
created: "2026-11-12"
---

# Feature: extract_tables_with_code (#14)

## Proposed Solution
`extract_tables_with_code(tables, schema, llm=, sandbox=, max_attempts=3, timeout_s=,
memory_mb=, enrich_schema=)`: scout (plan), worker (pandas `extract(tables)`), validator
(JSON Schema + `check_rows`, feedback to the worker), optional schema enricher.
Generated code runs only through the caller's `sandbox(code, inputs, timeout_s=,
memory_mb=)`; without one the function raises. extractfold contains no `exec`/`eval`.

## Test Plan
- [x] refuses without a sandbox
- [x] retries with the sandbox error and the failed checks as feedback
- [x] stops after `max_attempts`
- [x] the module never executes code itself

## Out of Scope
- A sandbox implementation: isolation (no network, no file system, limits) depends on
  the host (containers, gVisor, a remote runner) and belongs to the caller.
