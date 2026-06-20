# CLAUDE.md

## Project

extractfold turns documents plus JSON Schema into schema-conformant dictionaries.
It is the structured-extraction sibling of docfold.

## Workflow

- Use TDD for every feature and engine.
- Write or update `docs/tasks/<name>.md` from `docs/tasks/_TEMPLATE.md`.
- Confirm the new test fails for the expected reason before implementing.
- Keep the public contract in `src/extractfold/engines/base.py` backward compatible.
- Keep core imports dependency-free.
- Put heavy SDK/model imports inside methods.

## Gates

```bash
ruff check src/ tests/
mypy src/
pytest tests/ -m "not integration"
```
