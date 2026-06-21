# Golden Rules

1. TDD is mandatory: proposal, failing test, implementation, verification.
2. Preserve public API backward compatibility in `extractfold.engines.base`.
3. Keep base `dependencies = []`.
4. Import heavy dependencies lazily inside engine methods.
5. Unit tests must not require model weights, cloud credentials, or network.
6. Gate real engine runs behind the `integration` marker.
7. Required gates before done:

```bash
ruff check src/ tests/
mypy src/
pytest tests/ -m "not integration"
```
