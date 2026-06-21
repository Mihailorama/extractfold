# Contributing

## Development Setup

```bash
pip install -e ".[dev]"
```

## Adding An Engine

1. Add `docs/tasks/<engine>.md` from `docs/tasks/_TEMPLATE.md`.
2. Write stubbed unit tests and a skipped `integration` test.
3. Confirm the unit test fails before writing adapter code.
4. Implement the adapter behind `ExtractionEngine`.
5. Add an optional extra in `pyproject.toml`.
6. Register the engine in the CLI router and priority order.
7. Run the quality gates.

## Quality Gates

```bash
ruff check src/ tests/
mypy src/
pytest tests/ -m "not integration"
```
