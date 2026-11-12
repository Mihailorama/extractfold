from __future__ import annotations

import json

import pytest

from extractfold.postprocess import compute_fields, drop_rows_missing, map_to_reference, merge_rows


def test_drop_rows_missing_records_what_was_dropped() -> None:
    rows = [{"id": "1", "name": "a"}, {"id": "", "name": "b"}, {"id": "3", "name": "N/A"}]
    kept, record = drop_rows_missing(rows, ["id", "name"])

    assert kept == [{"id": "1", "name": "a"}]
    assert record["step"] == "drop_rows_missing" and record["changed"] == 2
    assert record["changes"][0] == {"row": 1, "action": "dropped", "missing": ["id"]}
    assert rows[1] == {"id": "", "name": "b"}  # input untouched


@pytest.mark.asyncio
async def test_merge_rows_by_key_without_a_model() -> None:
    rows = [
        {"inn": "77", "name": "Acme", "city": ""},
        {"inn": "88", "name": "Beta", "city": "Riga"},
        {"inn": "77", "name": "", "city": "Oslo"},
        {"inn": "", "name": "loose", "city": ""},
    ]
    merged, record = await merge_rows(rows, key=["inn"])

    assert merged == [
        {"inn": "77", "name": "Acme", "city": "Oslo"},
        {"inn": "88", "name": "Beta", "city": "Riga"},
        {"inn": "", "name": "loose", "city": ""},
    ]
    assert record["changes"] == [{"rows": [0, 2], "action": "merged", "into": 0,
                                  "method": "fields"}]


@pytest.mark.asyncio
async def test_merge_rows_with_a_model_and_a_fallback() -> None:
    rows = [{"name": "Acme Inc", "note": "x"}, {"name": "ACME", "note": "y"}]

    async def good(prompt: str) -> str:
        assert "Acme Inc" in prompt
        return '{"name": "Acme Inc", "note": "x; y"}'

    merged, record = await merge_rows(rows, llm=good)
    assert merged == [{"name": "Acme Inc", "note": "x; y"}]
    assert record["changes"][0]["method"] == "llm"

    merged, record = await merge_rows(rows, llm=lambda p: '{"invented": 1}')
    assert merged == [{"name": "Acme Inc", "note": "x"}]
    assert record["changes"][0]["method"] == "fields"


@pytest.mark.asyncio
async def test_compute_fields_local_and_model() -> None:
    rows = [{"qty": 2, "price": 5}, {"qty": 3, "price": None}]
    prompts: list[str] = []

    def llm(prompt: str) -> str:
        prompts.append(prompt)
        return json.dumps({"label": "pair" if '"qty": 2' in prompt else "triple"})

    out, record = await compute_fields(
        rows,
        [
            {"name": "amount", "compute": lambda r: r["qty"] * r["price"]},
            {"name": "label", "description": "size word", "samples": ["single"]},
        ],
        llm=llm,
    )

    assert out == [{"qty": 2, "price": 5, "amount": 10, "label": "pair"},
                   {"qty": 3, "price": None, "amount": None, "label": "triple"}]
    assert "Examples: single" in prompts[0] and len(prompts) == 2
    assert {"row": 0, "field": "amount", "before": None, "after": 10} in record["changes"]
    with pytest.raises(ValueError):
        await compute_fields(rows, [{"name": "label"}])


@pytest.mark.asyncio
async def test_map_to_reference_exact_similar_model_and_other() -> None:
    reference = [{"code": "01", "name": "Concrete works"}, {"code": "02", "name": "Painting"},
                 {"code": "99", "name": "Other"}]
    rows = [{"w": "concrete  WORKS"}, {"w": "Paintng"}, {"w": "Bетон"}, {"w": "zzz"},
            {"w": ""}]

    def llm(prompt: str) -> str:
        assert '"zzz"' in prompt and '"Paintng"' not in prompt
        return json.dumps({"Bетон": "Concrete works", "zzz": "Invented"})

    out, record = await map_to_reference(rows, "w", reference, value_key="name", llm=llm,
                                         other="Other")

    assert [r["w"] for r in out] == ["Concrete works", "Painting", "Concrete works", "Other", ""]
    assert [c["method"] for c in record["changes"]] == ["exact", "similar", "llm", "other"]


@pytest.mark.asyncio
async def test_model_call_errors_are_not_mistaken_for_empty_answers() -> None:
    from extractfold.codegen import extract_tables_with_code
    from extractfold.entities import extract_entities
    from extractfold.rules import suggest_rules

    def down(prompt: str) -> str:
        raise RuntimeError("429 rate limit")

    rows = [{"a": "1"}, {"a": "1"}]
    for call in (
        merge_rows(rows, llm=down),
        compute_fields(rows, [{"name": "b"}], llm=down),
        map_to_reference(rows, "a", ["x"], llm=down),
        suggest_rules(rows, llm=down),
        extract_entities("text", llm=down),
        extract_tables_with_code({"t": [["a"]]}, {"type": "object"}, llm=down,
                                 sandbox=lambda *a, **k: {}),
    ):
        with pytest.raises(RuntimeError, match="429"):
            await call
