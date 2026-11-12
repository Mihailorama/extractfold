from __future__ import annotations

import json

import pytest

from extractfold.canonical import canonical_extract


@pytest.mark.asyncio
async def test_canonical_extract_merges_chunks_and_measures_quality() -> None:
    answers = [
        {"document_type": "act", "proposed_schema": {
            "header": {"properties": {"number": {}, "total": {}}},
            "line_item": {"properties": {"name": {}, "amount": {}}}},
         "header_fields": {"number": "7", "total": None},
         "sections": [{"title": "Works", "summary": "two lines"}],
         "line_items": [{"name": "Bricks", "amount": 10}]},
        "not json",
        {"document_type": "other", "header_fields": {"number": "8", "total": 30},
         "line_items": [{"name": "Sand", "amount": None}, "junk"]},
    ]
    prompts: list[str] = []
    progress: list[tuple[int, int]] = []

    def llm(prompt: str) -> str:
        prompts.append(prompt)
        answer = answers[len(prompts) - 1]
        return answer if isinstance(answer, str) else json.dumps(answer)

    profile = await canonical_extract("a" * 30, llm=llm, max_chars=10,
                                      on_progress=lambda d, t: progress.append((d, t)))

    assert profile["document_type"] == "act"
    assert profile["header_fields"] == {"number": "7", "total": 30}
    assert profile["line_items"] == [{"name": "Bricks", "amount": 10},
                                     {"name": "Sand", "amount": None}]
    assert '"line_item"' in prompts[1] and "part 2 of 3" in prompts[1]
    assert profile["errors"][0]["chunk"] == 1
    assert progress == [(1, 3), (2, 3), (3, 3)]
    quality = profile["quality"]
    assert quality["header_fill"] == 1.0 and quality["line_items"] == 2
    assert quality["line_item_fill"] == 0.75 and quality["failed_chunks"] == 1
    assert {c["check"] for c in quality["checks"]} == {"schema_compliance",
                                                        "suspicious_patterns"}
