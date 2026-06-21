---
purpose: "Command-line interface mirroring docfold"
status: "OPEN"
priority: "P1"
created: "2026-06-20"
---

# Feature: CLI

## Problem
Users need a first-class `extractfold` console command for extraction, comparison, engine introspection, and benchmark execution.

## Proposed Solution
Add `extractfold.cli` with `extract`, `compare`, `list-engines`, and `benchmark` subcommands and a project script entry point.

## Affected Files
- `src/extractfold/cli.py` - CLI
- `pyproject.toml` - console script

## Test Plan

### Unit / Functional Tests
- [ ] `list-engines` prints engine status/capability table.
- [ ] `extract` writes JSON to stdout or file using a stubbed router.
- [ ] `compare` prints side-by-side results and field agreement.
- [ ] `benchmark` delegates to benchmark runner.

### Integration / E2E Tests
- [ ] CLI smoke with installed package and stub engine.

### Test Commands
```bash
pytest tests/test_cli.py -v
```

## Edge Cases
- Missing schema path or invalid schema JSON.

## Out of Scope
- Non-JSON output formats beyond the requested `json`.
