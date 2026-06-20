---
purpose: "Open-source project files, docs, packaging, and CI"
status: "OPEN"
priority: "P1"
created: "2026-06-20"
---

# Feature: Docs, Packaging, CI

## Problem
extractfold should be publishable as a polished open-source sibling to docfold with the same quality gates and contributor guidance.

## Proposed Solution
Add README, changelog, contributor docs, agent instructions, per-engine extras, and CI for Python 3.10-3.12 on Linux/macOS/Windows.

## Affected Files
- `README.md` - positioning, usage, engine matrix
- `CLAUDE.md`, `AGENTS.md`, `CODEX.md`, `CONTRIBUTING.md` - project instructions
- `docs/conventions/golden-rules.md`, `docs/benchmarks.md` - conventions and engine profiles
- `pyproject.toml`, `.github/workflows/ci.yml`, `CHANGELOG.md` - packaging and automation

## Test Plan

### Unit / Functional Tests
- [ ] `python -c "import extractfold"` succeeds with no third-party deps.
- [ ] `pyproject.toml` exposes all required extras and console script.

### Integration / E2E Tests
- [ ] CI runs ruff, mypy, and non-integration pytest matrix.

### Test Commands
```bash
ruff check src/ tests/
mypy src/
pytest tests/ -m "not integration"
```

## Edge Cases
- `[all]` must aggregate optional engine extras without adding base dependencies.

## Out of Scope
- Publishing a release tag in this task.
