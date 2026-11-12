from __future__ import annotations

import json
from typing import Any

import pytest

from extractfold.chunking import TextChunk
from extractfold.engines.provider_router_engine import ProviderRouterEngine
from extractfold.provenance import align_provenance, build_source_catalog
from extractfold.text import extract_rows_chunked

SHEET = "Sheet: Prices\nService\tPrice\nVisit\t100\n"


def _spans_match(text: str, catalog: list[dict[str, Any]]) -> bool:
    return all(text[e["start"] : e["end"]] == e["text"] for e in catalog if "start" in e)


def test_spreadsheet_catalog_has_one_entry_per_cell() -> None:
    catalog = build_source_catalog(SHEET, input_format="spreadsheet")

    assert [e["id"] for e in catalog] == ["Prices!A1", "Prices!B1", "Prices!A2", "Prices!B2"]
    assert catalog[3] == {"id": "Prices!B2", "text": "100", "sheet": "Prices", "cell": "B2",
                          "start": catalog[3]["start"], "end": catalog[3]["end"]}
    assert _spans_match(SHEET, catalog)


def test_csv_catalog_skips_nothing_and_respects_quotes() -> None:
    text = 'name,note\n"Acme, Inc","x"\n'
    catalog = build_source_catalog(text, input_format="csv")

    assert [(e["cell"], e["text"]) for e in catalog] == [
        ("A1", "name"), ("B1", "note"), ("A2", "Acme, Inc"), ("B2", "x")
    ]
    assert _spans_match(text, catalog)


def test_block_catalog_carries_pages_and_bboxes() -> None:
    text = "Invoice INV-7\n\nTotal 120.00"
    blocks = [
        {"type": "Text", "bbox": [10, 10, 200, 30], "page": 1, "text": "Invoice INV-7",
         "id": "p1-b0"},
        {"type": "Text", "bbox": [10, 700, 200, 720], "page": 2, "text": "Total 120.00"},
    ]
    catalog = build_source_catalog(text, blocks=blocks)

    assert catalog[0]["id"] == "p1-b0" and catalog[0]["page"] == 1
    assert catalog[0]["bbox"] == [10, 10, 200, 30] and catalog[0]["block_type"] == "Text"
    assert catalog[1]["id"] == "p2-b1"
    assert _spans_match(text, catalog)


def test_text_json_and_html_catalogs() -> None:
    para = build_source_catalog("first block\n\nsecond block")
    assert [e["text"] for e in para] == ["first block", "second block"]
    assert _spans_match("first block\n\nsecond block", para)

    data = build_source_catalog('{"a": [1, {"b": "x"}]}', input_format="json")
    assert [(e["id"], e["text"]) for e in data] == [("$.a[0]", "1"), ("$.a[1].b", "x")]

    html = (
        '<div class="page" data-page-id="3"><p>Hello</p>\n'
        "<table><tr><td>42</td></tr></table></div>"
    )
    blocks = build_source_catalog(html, input_format="html")
    assert [(e["text"], e["page"]) for e in blocks] == [("Hello", "3"), ("42", "3")]
    assert [html[e["start"] : e["end"]] for e in blocks] == ["<p>Hello</p>", "<td>42</td>"]


def test_align_provenance_scores_against_the_cited_source() -> None:
    catalog = [
        {"id": "c1", "text": "Visit", "sheet": "S", "cell": "A2"},
        {"id": "c2", "text": "Total due 100 EUR", "page": 1},
    ]
    rows = [{"service": "Visit", "price": 100, "note": "", "free": "paid"}]
    raw = [{
        "service": {"source_refs": ["c1"], "confidence": 0.5, "rationale": "cell A2"},
        "price": {"source_refs": ["c2", "nope"], "confidence": 0.9},
        "note": {"source_refs": [], "confidence": 0.7},
    }]

    aligned = align_provenance(rows, raw, catalog)[0]

    assert aligned["service"]["confidence"] == 0.95
    assert aligned["service"]["source_refs"] == [{"id": "c1", "sheet": "S", "cell": "A2"}]
    assert aligned["service"]["rationale"] == "cell A2"
    assert aligned["price"]["confidence"] == 0.9
    assert aligned["price"]["source_refs"] == [{"id": "c2", "page": 1}]
    assert aligned["price"]["unknown_refs"] == ["nope"]
    assert aligned["note"]["confidence"] == 0.0
    assert aligned["free"]["confidence"] == 0.2 and aligned["free"]["source_refs"] == []


@pytest.mark.asyncio
async def test_provider_router_returns_per_field_provenance() -> None:
    catalog = build_source_catalog(SHEET, input_format="spreadsheet")
    prompts: list[str] = []

    def provider_call(**kwargs: Any) -> str:
        prompts.append(kwargs["prompt"])
        return json.dumps({
            "rows": [{"service": "Visit", "price": 100}],
            "provenance": [{
                "service": {"source_refs": ["Prices!A2"], "confidence": 0.9, "rationale": "A2"},
                "price": {"source_refs": ["Prices!B2"], "confidence": 0.9, "rationale": "B2"},
            }],
        })

    engine = ProviderRouterEngine(provider_call=provider_call)
    result = await engine.extract_text(
        SHEET, {"type": "object", "properties": {"service": {}, "price": {}}},
        source_catalog=catalog,
    )

    assert '"id": "Prices!B2"' in prompts[0] and '"provenance"' in prompts[0]
    assert result.data == {"rows": [{"service": "Visit", "price": 100}]}
    field = result.provenance["rows"][0]["price"]
    assert field["source_refs"] == [{"id": "Prices!B2", "sheet": "Prices", "cell": "B2"}]
    assert field["confidence"] == 0.95
    assert result.field_confidence == {"service": 0.95, "price": 0.95}
    assert engine.capabilities.provenance is True


@pytest.mark.asyncio
async def test_chunked_provenance_stays_aligned_and_catalog_is_per_chunk() -> None:
    text = "alpha\n\nbeta"
    catalog = build_source_catalog(text)
    prompts: list[str] = []

    def provider_call(**kwargs: Any) -> str:
        prompts.append(kwargs["prompt"])
        word = kwargs["text"].strip()
        ref = next(e["id"] for e in kwargs["source_catalog"] if e["text"] == word)
        return json.dumps({
            "rows": [{"w": word}, {"w": word}],
            "provenance": [{"w": {"source_refs": [ref], "confidence": 0.6}}, {}],
        })

    chunks = [
        TextChunk(text="alpha\n\n", index=0, start=0, end=7, strategy="m"),
        TextChunk(text="beta", index=1, start=7, end=11, strategy="m"),
    ]
    result = await extract_rows_chunked(
        text, {"w": "x"}, engine=ProviderRouterEngine(provider_call=provider_call),
        chunks=chunks, source_catalog=catalog,
    )

    assert result.data["rows"] == [{"w": "alpha"}, {"w": "beta"}]  # dedupe drops repeats
    refs = [r["w"]["source_refs"][0]["id"] for r in result.provenance["rows"]]
    assert refs == [catalog[0]["id"], catalog[1]["id"]]
    assert catalog[1]["id"] not in prompts[0] and catalog[0]["id"] not in prompts[1]
