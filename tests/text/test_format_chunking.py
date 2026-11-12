from __future__ import annotations

import json
from typing import Any

import pytest

from extractfold.chunking import chunk_budget, chunk_document
from extractfold.engines.provider_router_engine import ProviderRouterEngine
from extractfold.text import extract_rows_chunked

SHEET = "\n".join(
    [
        "Sheet: Prices",
        "Service\tPrice",
        "Consults",
        "Visit\t100",
        "Repeat visit\t80",
        "Labs",
        "Blood test\t30",
        "Urine test\t20",
        "Sheet: Extra",
        "Delivery\t5",
    ]
)


def test_spreadsheet_chunks_keep_rows_whole_and_carry_sheet_and_category() -> None:
    chunks = chunk_document(SHEET, input_format="spreadsheet", max_chars=10**6, max_rows=5)

    assert "".join(c.text for c in chunks) == SHEET
    assert all(not c.text.startswith("\t") for c in chunks)
    second = chunks[1]
    assert second.strategy == "spreadsheet"
    assert second.metadata["sheets"][0]["sheet"] == "Prices"
    assert second.metadata["estimated_rows"] == sum(
        1 for line in second.text.splitlines() if line.strip() and not line.startswith("Sheet: ")
    )
    labs = next(c for c in chunks if c.text.startswith("Blood test"))
    assert '"Labs"' in labs.metadata["context"] and "sheet Prices" in labs.metadata["context"]
    assert labs.metadata["sheets"] == [
        {"sheet": "Prices", "row_start": 6, "row_end": 7},
        {"sheet": "Extra", "row_start": 1, "row_end": 1},
    ]
    assert len(chunk_document(SHEET, input_format="spreadsheet", max_chars=30)) > 3


def test_csv_chunks_repeat_the_header_and_respect_quoted_newlines() -> None:
    text = 'name,note\n"a","x\ny"\nb,z\nc,w\n'
    chunks = chunk_document(text, input_format="csv", max_chars=18)

    assert all(c.text.startswith("name,note\n") for c in chunks)
    assert any('"a","x\ny"' in c.text for c in chunks)
    assert sum(c.metadata["estimated_rows"] for c in chunks) == 3
    assert [c.metadata["row_start"] for c in chunks] == sorted(
        c.metadata["row_start"] for c in chunks
    )


def test_html_chunks_follow_page_nodes() -> None:
    pages = "".join(
        f'<div class="page" data-page-id="{i}"><table><tr>'
        + "<td>c</td>" * 5
        + "</tr></table></div>"
        for i in range(1, 8)
    )
    chunks = chunk_document("<html><body>" + pages + "</body></html>", input_format="html",
                            max_chars=10_000)

    assert [c.metadata["page_ids"] for c in chunks] == [["1", "2", "3", "4", "5"], ["6", "7"]]
    assert chunks[0].metadata["estimated_rows"] == 5
    small = chunk_document(pages, input_format="html", max_chars=200)
    assert all(len(c.metadata["page_ids"]) == 1 for c in small)


def test_json_chunks_split_on_objects_by_rows_and_chars() -> None:
    rows = [{"id": i, "name": "x" * 10} for i in range(5)]
    chunks = chunk_document(json.dumps(rows), input_format="json", max_chars=60, max_rows=10)

    assert [r for c in chunks for r in json.loads(c.text)] == rows
    assert all(len(c.text) <= 60 for c in chunks)
    assert chunks[0].metadata["estimated_rows"] == len(json.loads(chunks[0].text))


def test_chunk_budget_from_model_limits() -> None:
    budget = chunk_budget("latin text " * 100, max_input_tokens=100_000,
                          max_output_tokens=16_000, reserved_tokens=4_000, fields=4)

    assert budget["max_chars"] == (100_000 - 16_000 - 4_000) * 4
    assert budget["max_rows"] == int(16_000 * 0.8 / (4 * 70 / 3))
    assert chunk_budget("я" * 100, max_input_tokens=10_000, max_output_tokens=2_000)[
        "max_chars"
    ] == int(8_000 * 1.8)


def _line_rows(**kwargs: Any) -> str:
    """Fake model: one row per data line; spreadsheet category lines carry over."""
    text, rows = kwargs["text"], []
    category = None
    context = kwargs.get("context") or ""
    if '"' in context:
        category = context.split('"')[1]
    for line in text.splitlines():
        cells = [c for c in line.replace(",", "\t").split("\t") if c]
        if line.startswith("Sheet: "):
            category = None
            continue
        if not cells or cells == ["name", "note"]:
            continue
        if cells == ["Service", "Price"]:
            continue
        if len(cells) == 1:
            category = cells[0]
            continue
        rows.append({"name": cells[0], "category": category})
    return json.dumps({"rows": rows})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fmt", "text"),
    [
        ("spreadsheet", SHEET),
        ("csv", "name,note\n" + "".join(f"{c},{i}\n" for i, c in enumerate("abcdefgh"))),
    ],
)
async def test_formats_extract_the_same_rows_as_the_single_chunk_text_path(fmt, text) -> None:
    engine = ProviderRouterEngine(provider_call=_line_rows)
    schema = {"type": "object", "properties": {"name": {}, "category": {}}}

    whole = await extract_rows_chunked(text, schema, engine=engine, max_chars=10**6,
                                       dedupe=False)
    chunked = await extract_rows_chunked(text, schema, engine=engine, max_chars=30,
                                         input_format=fmt, dedupe=False)

    assert chunked.metadata["chunking"]["total_chunks"] > 1
    assert chunked.data["rows"] == whole.data["rows"]


@pytest.mark.asyncio
async def test_flat_json_matching_the_schema_passes_through_without_a_call() -> None:
    calls: list[Any] = []
    engine = ProviderRouterEngine(provider_call=lambda **kw: calls.append(kw) or "[]")
    rows = [{"name": "a", "qty": 1}, {"name": "b"}]
    schema = {"type": "object", "properties": {"name": {"type": "string"},
                                               "qty": {"type": "number"}}}

    result = await extract_rows_chunked(json.dumps(rows), schema, engine=engine,
                                        input_format="json", max_chars=1000)

    assert calls == []
    assert result.data["rows"] == rows
    assert result.metadata["passthrough"] is True

    other = [{"Name": "a"}]
    await extract_rows_chunked(json.dumps(other), schema, engine=engine,
                               input_format="json", max_chars=1000)
    assert len(calls) == 1
