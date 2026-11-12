from __future__ import annotations

from typing import Any

import pytest

from extractfold.codegen import extract_tables_with_code

TABLES = {"Sheet1": [["Name", "Qty"], ["Bricks", 2], ["Sand", 1]]}
SCHEMA = {"type": "object", "properties": {"name": {"type": "string"},
                                           "qty": {"type": "number"}}}


@pytest.mark.asyncio
async def test_refuses_to_run_without_a_sandbox() -> None:
    with pytest.raises(ValueError, match="sandbox"):
        await extract_tables_with_code(TABLES, SCHEMA, llm=lambda p: "", sandbox=None)


@pytest.mark.asyncio
async def test_worker_retries_with_feedback_until_rows_validate() -> None:
    prompts: list[str] = []
    runs: list[dict[str, Any]] = []

    def llm(prompt: str) -> str:
        prompts.append(prompt)
        if prompt.startswith("You are the scout"):
            return '{"columns": {"name": "A", "qty": "B"}}'
        if prompt.startswith("You are the schema enricher"):
            return '[{"name": "unit", "type": "string"}, {"name": "qty"}]'
        return f"```python\ndef extract(tables):\n    return []  # try {len(runs) + 1}\n```"

    answers = [
        {"error": "NameError: pd"},
        {"rows": [{"name": "Bricks", "qty": "two"}]},
        {"rows": [{"name": "Bricks", "qty": 2}, {"name": "Sand", "qty": 1}]},
    ]

    async def sandbox(code: str, inputs: dict, *, timeout_s: float, memory_mb: int) -> dict:
        runs.append({"code": code, "inputs": inputs, "timeout_s": timeout_s})
        return answers[len(runs) - 1]

    result = await extract_tables_with_code(TABLES, SCHEMA, llm=llm, sandbox=sandbox,
                                            enrich_schema=True, timeout_s=5)

    assert result["valid"] is True
    assert result["rows"] == [{"name": "Bricks", "qty": 2}, {"name": "Sand", "qty": 1}]
    assert runs[0]["code"].startswith("def extract(tables):") and runs[0]["timeout_s"] == 5
    assert runs[0]["inputs"] == {"tables": {"Sheet1": [["Name", "Qty"], ["Bricks", 2],
                                                       ["Sand", 1]]}}
    worker_prompts = [p for p in prompts if p.startswith("You are the worker")]
    assert "NameError: pd" in worker_prompts[1] and "qty" in worker_prompts[2]
    assert [("error" in a) for a in result["attempts"]] == [True, False, False]
    assert result["plan"] == {"columns": {"name": "A", "qty": "B"}}
    assert result["schema_suggestions"] == [{"name": "unit", "type": "string"}]


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts() -> None:
    def sandbox(code: str, inputs: dict, **limits: Any) -> dict:
        return {"error": "timeout"}

    result = await extract_tables_with_code(TABLES, SCHEMA, llm=lambda p: "x = 1",
                                            sandbox=sandbox, max_attempts=2)

    assert result["valid"] is False and result["rows"] == []
    assert len(result["attempts"]) == 2


def test_extractfold_never_executes_generated_code() -> None:
    from pathlib import Path

    source = Path(__file__).parents[2].joinpath("src/extractfold/codegen.py").read_text()
    assert "exec(" not in source and "eval(" not in source
