"""Deterministic chunk planning utilities."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TextChunk:
    """A planned extraction chunk with stable source coordinates."""

    text: str
    index: int
    start: int
    end: int
    strategy: str
    overlap: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the chunk to a plain dictionary."""
        return {
            "text": self.text,
            "index": self.index,
            "start": self.start,
            "end": self.end,
            "strategy": self.strategy,
            "overlap": self.overlap,
            "metadata": dict(self.metadata),
        }


def chunk_text(text: str, *, max_chars: int, overlap: int = 0) -> list[TextChunk]:
    """Plan character-window chunks for plain text."""
    _validate_window(max_chars, overlap)
    if not text:
        return []

    chunks: list[TextChunk] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(
            TextChunk(
                text=text[start:end],
                index=len(chunks),
                start=start,
                end=end,
                strategy="text",
                overlap=0 if not chunks else overlap,
                metadata={"unit": "char"},
            )
        )
        if end == len(text):
            break
        start = end - overlap
    return chunks


def chunk_json_array(json_text: str, *, max_rows: int, overlap: int = 0) -> list[TextChunk]:
    """Plan row-safe chunks from a JSON array string."""
    rows = json.loads(json_text)
    if not isinstance(rows, list):
        raise ValueError("chunk_json_array expects a JSON array")
    return chunk_rows(rows, max_rows=max_rows, overlap=overlap, strategy="json_array")


def chunk_rows(
    rows: Sequence[Any],
    *,
    max_rows: int,
    overlap: int = 0,
    strategy: str = "rows",
) -> list[TextChunk]:
    """Plan row-window chunks from already parsed rows."""
    _validate_window(max_rows, overlap)
    if not rows:
        return []

    chunks: list[TextChunk] = []
    start = 0
    while start < len(rows):
        end = min(start + max_rows, len(rows))
        row_slice = list(rows[start:end])
        chunks.append(
            TextChunk(
                text=json.dumps(row_slice, ensure_ascii=False),
                index=len(chunks),
                start=start,
                end=end,
                strategy=strategy,
                overlap=0 if not chunks else overlap,
                metadata={"unit": "row", "row_start": start, "row_end": end},
            )
        )
        if end == len(rows):
            break
        start = end - overlap
    return chunks


def chunk_sections(text: str, *, max_chars: int, overlap: int = 0) -> list[TextChunk]:
    """Plan section-aware chunks for Markdown or HTML-like text."""
    _validate_window(max_chars, overlap)
    if not text:
        return []

    sections = _find_sections(text)
    if not sections:
        return chunk_text(text, max_chars=max_chars, overlap=overlap)

    chunks: list[TextChunk] = []
    current_start: int | None = None
    current_end: int | None = None
    current_text = ""

    for start, end in sections:
        section_text = text[start:end]
        if current_text and len(current_text) + len(section_text) > max_chars:
            chunks.append(
                _section_chunk(
                    current_text,
                    len(chunks),
                    current_start or 0,
                    current_end or 0,
                )
            )
            current_start = start
            current_text = section_text
            current_end = end
        else:
            if current_start is None:
                current_start = start
            current_text += section_text
            current_end = end

    if current_text:
        chunks.append(
            _section_chunk(
                current_text,
                len(chunks),
                current_start or 0,
                current_end or 0,
            )
        )
    return chunks


def _validate_window(size: int, overlap: int) -> None:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= size:
        raise ValueError("overlap must be smaller than chunk size")


def _find_sections(text: str) -> list[tuple[int, int]]:
    starts = _markdown_heading_starts(text) or _html_heading_starts(text)
    if not starts:
        return []
    ends = starts[1:] + [len(text)]
    return [(start, end) for start, end in zip(starts, ends) if end > start]


def _markdown_heading_starts(text: str) -> list[int]:
    return [match.start() for match in re.finditer(r"(?m)^#{1,6}\s+", text)]


def _html_heading_starts(text: str) -> list[int]:
    return [match.start() for match in re.finditer(r"(?i)<h[1-6][^>]*>", text)]


def _section_chunk(text: str, index: int, start: int, end: int) -> TextChunk:
    return TextChunk(
        text=text,
        index=index,
        start=start,
        end=end,
        strategy="section",
        overlap=0,
        metadata={"unit": "char"},
    )
