# CODEX.md

## Commands

```bash
rtk ruff check src/ tests/
rtk mypy src/
rtk pytest tests/ -m "not integration"
```

Use `rtk` for shell commands in this workspace. Keep changes scoped and do not
revert user work.
