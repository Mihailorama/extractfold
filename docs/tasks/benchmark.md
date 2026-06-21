---
purpose: "Folder benchmark harness"
status: "OPEN"
priority: "P1"
created: "2026-06-20"
---

# Feature: Benchmark Harness

## Problem
Users need a reproducible way to run documents, schemas, and gold answers across engines and compare accuracy/F1, compliance, latency, and cost.

## Proposed Solution
Add root `benchmark.py` with dataset discovery, router execution, evaluation aggregation, JSON output, and a plain text table.

## Affected Files
- `benchmark.py` - harness
- `src/extractfold/evaluation/runner.py` - shared report structures

## Test Plan

### Unit / Functional Tests
- [ ] Harness discovers document/schema/gold triples.
- [ ] Harness writes result JSON and includes latency/cost fields.

### Integration / E2E Tests
- [ ] CLI benchmark subcommand runs the harness.

### Test Commands
```bash
pytest tests/test_benchmark.py -v
```

## Edge Cases
- Missing gold files should be reported cleanly.

## Out of Scope
- Generating synthetic PDFs.
