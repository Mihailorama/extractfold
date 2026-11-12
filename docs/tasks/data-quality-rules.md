---
purpose: "Data-quality report and cross-entity rule validation"
status: "DONE"
priority: "P1"
created: "2026-11-12"
---

# Feature: data-quality rules (#11)

## Problem
`validate_data` covers JSON-Schema type/required only. Callers need rule checks over
extracted tables, across tables, and rules a model proposes, as one list of checks.

## Proposed Solution
`extractfold.rules.check_rules(tables, rules)` returns one check per rule:
`{check, type, status: passed|failed|warning|error, message, affected: [{table, row,
field}], rule}`. Rule types: `not_empty`, `unique`, `range`, `pattern`, `allowed`,
`schema`, `expression` (safe AST evaluator: arithmetic, comparisons, and/or/not, `abs`,
`round`, `field("name")`; `==` on numbers within `tolerance`; rows missing a value are
skipped), `sum_equals` (parts per key equal the total, across tables), `reference`
(referential integrity). A broken rule reports `error` instead of raising.
`suggest_rules(tables, llm=)` asks a model for rules of these types and keeps only those
that run.

## Test Plan
- [x] each field rule; warning severity
- [x] expression with tolerance and skipped rows; code refused
- [x] cross-table sum per key and overall; reference integrity
- [x] unknown rule type is an `error` check
- [x] suggested rules filtered to valid ones

## Out of Scope
- Fixing values that fail a rule.
