---
purpose: "Schema-extraction evaluation metrics and runner"
status: "OPEN"
priority: "P1"
created: "2026-06-20"
---

# Feature: Evaluation

## Problem
Structured extraction needs metrics beyond text error rate: field accuracy, schema compliance, precision/recall/F1, hallucination rate, type correctness, nested alignment, and normalized value matching.

## Proposed Solution
Extend `extractfold.evaluation` with dependency-free metrics and a runner that compares predictions against gold JSON files and emits JSON plus a tabulated text report.

## Affected Files
- `src/extractfold/evaluation/metrics.py` - metrics
- `src/extractfold/evaluation/runner.py` - dataset runner

## Test Plan

### Unit / Functional Tests
- [ ] Metrics cover exact, normalized, hallucinated, typed, nested, and array cases.
- [ ] Runner loads prediction/gold pairs and aggregates per-engine summaries.

### Integration / E2E Tests
- [ ] Benchmark CLI can call the runner on a folder dataset.

### Test Commands
```bash
pytest tests/evaluation/ -v
```

## Edge Cases
- Missing fields and extra fields must be counted separately.

## Out of Scope
- OCR text quality metrics.
