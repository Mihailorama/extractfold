from __future__ import annotations

import json

import pytest

from extractfold.entities import extract_entities


@pytest.mark.asyncio
async def test_extract_entities_merges_across_chunks() -> None:
    answers = {
        "Acme ": [{"type": "organisation", "value": "Acme", "attributes": {"inn": "77"}},
                  {"type": "person", "value": "Ann"}],
        "Acme2": [{"type": "Organisation".lower(), "value": " ACME ",
                    "attributes": {"inn": "99", "city": "Oslo"}},
                   {"type": "x", "value": ""}],
    }
    prompts: list[str] = []

    async def llm(prompt: str) -> str:
        prompts.append(prompt)
        chunk = prompt.rsplit("Text:\n", 1)[1]
        return "```json\n" + json.dumps(answers[chunk]) + "\n```"

    entities = await extract_entities("Acme Acme2", llm=llm, max_chars=5,
                                      types=["organisation", "person"])

    assert "Entity types to extract: organisation, person" in prompts[0]
    assert entities == [
        {"type": "organisation", "value": "Acme", "attributes": {"inn": "77", "city": "Oslo"},
         "chunks": [0, 1]},
        {"type": "person", "value": "Ann", "attributes": {}, "chunks": [0]},
    ]


@pytest.mark.asyncio
async def test_extract_entities_survives_a_bad_answer() -> None:
    assert await extract_entities("text", llm=lambda p: "sorry") == []
    assert await extract_entities("", llm=lambda p: "[]") == []
