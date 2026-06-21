from __future__ import annotations

import json

from extractfold.chunking import (
    TextChunk,
    chunk_json_array,
    chunk_rows,
    chunk_sections,
    chunk_text,
)


def test_chunk_text_splits_by_max_chars_with_overlap_metadata() -> None:
    chunks = chunk_text("abcdefghijklmnopqrstuvwxyz", max_chars=10, overlap=2)

    assert [chunk.text for chunk in chunks] == ["abcdefghij", "ijklmnopqr", "qrstuvwxyz"]
    assert [
        (chunk.index, chunk.start, chunk.end, chunk.strategy, chunk.overlap, chunk.metadata)
        for chunk in chunks
    ] == [
        (0, 0, 10, "text", 0, {"unit": "char"}),
        (1, 8, 18, "text", 2, {"unit": "char"}),
        (2, 16, 26, "text", 2, {"unit": "char"}),
    ]
    assert chunks[1].to_dict()["text"] == "ijklmnopqr"


def test_chunk_text_returns_no_chunks_for_empty_text() -> None:
    assert chunk_text("", max_chars=10) == []


def test_chunk_json_array_does_not_split_row_objects() -> None:
    rows = [
        {"id": 1, "name": "Ada"},
        {"id": 2, "name": "Grace"},
        {"id": 3, "name": "Katherine"},
    ]

    chunks = chunk_json_array(json.dumps(rows), max_rows=2)

    assert [json.loads(chunk.text) for chunk in chunks] == [rows[:2], rows[2:]]
    assert [(chunk.start, chunk.end, chunk.strategy, chunk.metadata) for chunk in chunks] == [
        (0, 2, "json_array", {"unit": "row", "row_start": 0, "row_end": 2}),
        (2, 3, "json_array", {"unit": "row", "row_start": 2, "row_end": 3}),
    ]


def test_chunk_rows_uses_row_windows_with_overlap() -> None:
    rows = [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]

    chunks = chunk_rows(rows, max_rows=3, overlap=1)

    assert [json.loads(chunk.text) for chunk in chunks] == [rows[:3], rows[2:]]
    assert [(chunk.index, chunk.start, chunk.end, chunk.overlap) for chunk in chunks] == [
        (0, 0, 3, 0),
        (1, 2, 4, 1),
    ]


def test_chunk_sections_keeps_markdown_heading_boundaries() -> None:
    text = "# One\nalpha\n\n# Two\nbeta\n\n# Three\ngamma"

    chunks = chunk_sections(text, max_chars=18)

    assert [chunk.text.strip() for chunk in chunks] == [
        "# One\nalpha",
        "# Two\nbeta",
        "# Three\ngamma",
    ]
    assert all(chunk.strategy == "section" for chunk in chunks)
    assert [chunk.start for chunk in chunks] == [0, 13, 25]


def test_chunk_sections_keeps_html_heading_boundaries() -> None:
    html = "<h1>One</h1><p>alpha</p><h2>Two</h2><p>beta</p>"

    chunks = chunk_sections(html, max_chars=30)

    assert [chunk.text for chunk in chunks] == [
        "<h1>One</h1><p>alpha</p>",
        "<h2>Two</h2><p>beta</p>",
    ]
    assert all(chunk.metadata["unit"] == "char" for chunk in chunks)


def test_text_chunk_serializes_to_dict() -> None:
    chunk = TextChunk(
        text="alpha",
        index=0,
        start=5,
        end=10,
        strategy="text",
        overlap=0,
        metadata={"unit": "char"},
    )

    assert chunk.to_dict() == {
        "text": "alpha",
        "index": 0,
        "start": 5,
        "end": 10,
        "strategy": "text",
        "overlap": 0,
        "metadata": {"unit": "char"},
    }
