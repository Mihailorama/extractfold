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


_SHEET_PREFIX = "Sheet: "
_PAGE_DIV = re.compile(
    r"<div\b[^>]*?(?:class=[\"'][^\"']*\bpage\b[^\"']*[\"']|data-page-id=|data-page=)[^>]*>",
    re.IGNORECASE,
)
_PAGE_ID = re.compile(r"data-page(?:-id)?=[\"']?([^\"'\s>]+)", re.IGNORECASE)


def chunk_document(
    text: str,
    *,
    input_format: str | None,
    max_chars: int,
    max_rows: int | None = None,
    max_pages: int = 5,
) -> list[TextChunk]:
    """Plan format-aware chunks that never cut a row, line or page.

    - ``spreadsheet`` / ``tsv``: tab-separated lines, sheets introduced by ``Sheet: <name>``
      lines. Metadata ``sheets`` gives each sheet's 1-based row range in the chunk;
      ``context`` names the sheet and the section header (a one-cell line) in effect where
      the chunk starts.
    - ``csv``: quote-aware lines; the header line starts every chunk.
    - ``json``: a top-level array split on whole items.
    - ``html``: ``<div class="page">`` / ``data-page-id`` nodes, at most *max_pages* per
      chunk (``page_ids``); without page nodes, splits after ``</tr>``.
    - ``markdown`` / ``md``: :func:`chunk_sections`; anything else: whole lines.

    Every chunk has ``metadata["estimated_rows"]``; *max_rows* caps it.
    """
    _validate_window(max_chars, 0)
    if not text.strip():
        return []
    fmt = (input_format or "").strip().lower()
    if fmt in {"spreadsheet", "tsv"}:
        return _chunk_units(text, _spreadsheet_units(text), max_chars, max_rows, "spreadsheet")
    if fmt == "csv":
        return _chunk_units(text, _line_units(text, quotes=True), max_chars, max_rows, "csv")
    if fmt == "json":
        return _chunk_json(text, max_chars, max_rows) or chunk_text(text, max_chars=max_chars)
    if fmt in {"html", "htm"}:
        pages = _chunk_html_pages(text, max_chars, max_pages)
        if pages:
            return pages
        return _chunk_units(text, _tr_units(text) or _line_units(text), max_chars, max_rows, "html")
    if fmt in {"markdown", "md"}:
        return chunk_sections(text, max_chars=max_chars)
    return _chunk_units(text, _line_units(text), max_chars, max_rows, "lines")


def chunk_budget(
    text: str,
    *,
    max_input_tokens: int,
    max_output_tokens: int,
    reserved_tokens: int = 0,
    fields: int = 1,
) -> dict[str, int]:
    """``max_chars`` / ``max_rows`` for :func:`chunk_document` from a model's limits.

    Input: tokens left after the answer and *reserved_tokens* (prompt, context), times the
    text's estimated characters per token (Latin ~4, Cyrillic ~1.8, CJK ~1.2). Output: rows
    of *fields* values (~70 characters, 3 per token each) that fit 80% of the answer limit,
    capped at 48k answer tokens, which models rarely fill.
    """
    available = max_input_tokens - max_output_tokens - reserved_tokens
    max_chars = max(int(available * _chars_per_token(text)), 1_000)
    output = min(max_output_tokens, 49_152)
    max_rows = max(int(output * 0.8 / max(max(fields, 1) * 70 / 3, 1)), 1)
    return {"max_chars": max_chars, "max_rows": max_rows}


def _chars_per_token(text: str) -> float:
    counts = {"latin": 0, "cyrillic": 0, "cjk": 0, "other": 0}
    for char in text[:5000]:
        if not char.isalpha():
            continue
        code = ord(char)
        if code <= 0x024F:
            counts["latin"] += 1
        elif 0x0400 <= code <= 0x04FF:
            counts["cyrillic"] += 1
        elif 0x4E00 <= code <= 0x9FFF or 0x3040 <= code <= 0x30FF:
            counts["cjk"] += 1
        else:
            counts["other"] += 1
    total = sum(counts.values())
    if not total:
        return 2.5
    weights = {"latin": 4.0, "cyrillic": 1.8, "cjk": 1.2, "other": 2.5}
    return max(sum(counts[k] * weights[k] for k in counts) / total, 1.2)


@dataclass
class _Unit:
    start: int
    end: int
    rows: int = 0
    sheet: str | None = None
    sheet_first: int = 0
    sheet_last: int = 0
    category: str = ""


def _line_units(text: str, *, quotes: bool = False) -> list[_Unit]:
    units: list[_Unit] = []
    start = 0
    in_quotes = False
    for index, char in enumerate(text):
        if quotes and char == '"':
            in_quotes = not in_quotes
        elif char == "\n" and not in_quotes:
            units.append(_Unit(start, index + 1))
            start = index + 1
    if start < len(text):
        units.append(_Unit(start, len(text)))
    for unit in units:
        unit.rows = 1 if text[unit.start : unit.end].strip() else 0
    return units


def _tr_units(text: str) -> list[_Unit]:
    ends = [m.end() for m in re.finditer(r"</tr>\n?", text, re.IGNORECASE)]
    if not ends:
        return []
    starts = [0, *ends]
    if ends[-1] < len(text):
        ends.append(len(text))
    return [_Unit(s, e, rows=1) for s, e in zip(starts, ends) if e > s]


def _spreadsheet_units(text: str) -> list[_Unit]:
    units: list[_Unit] = []
    sheet: str | None = None
    sheet_row = 0
    category = ""
    pending: int | None = None  # start of a "Sheet:" line waiting for its first row
    for line in _line_units(text):
        content = text[line.start : line.end].strip("\r\n")
        if content.startswith(_SHEET_PREFIX):
            sheet, sheet_row, category = content[len(_SHEET_PREFIX) :].strip(), 0, ""
            pending = line.start if pending is None else pending
            continue
        sheet_row += 1
        start = line.start if pending is None else pending
        pending = None
        units.append(
            _Unit(start, line.end, line.rows, sheet, sheet_row, sheet_row, category)
        )
        cells = [cell.strip() for cell in content.split("\t") if cell.strip()]
        if len(cells) == 1:
            category = cells[0]
    if pending is not None:
        if units:
            units[-1].end = len(text)
        else:
            units.append(_Unit(pending, len(text)))
    return units


def _chunk_units(
    text: str,
    units: list[_Unit],
    max_chars: int,
    max_rows: int | None,
    strategy: str,
) -> list[TextChunk]:
    header = ""
    if strategy == "csv" and units:
        header = text[units[0].start : units[0].end]
        if not header.endswith("\n"):
            header += "\n"
        units = units[1:]
        if not units:
            return [_unit_chunk(text, header, [_Unit(0, len(text))], 0, 0, strategy, first=True)]
    groups: list[list[_Unit]] = []
    current: list[_Unit] = []
    chars = len(header)
    rows = 0
    for unit in units:
        size = unit.end - unit.start
        too_long = chars + size > max_chars
        too_many = max_rows is not None and rows + unit.rows > max_rows
        if current and (too_long or too_many):
            groups.append(current)
            current, chars, rows = [], len(header), 0
        current.append(unit)
        chars += size
        rows += unit.rows
    if current:
        groups.append(current)

    chunks: list[TextChunk] = []
    row_start = 0
    for group in groups:
        chunk = _unit_chunk(text, header, group, len(chunks), row_start, strategy,
                            first=not chunks)
        row_start += chunk.metadata["estimated_rows"]
        if chunk.text.strip():
            chunks.append(chunk)
    return chunks


def _unit_chunk(
    text: str,
    header: str,
    group: list[_Unit],
    index: int,
    row_start: int,
    strategy: str,
    *,
    first: bool,
) -> TextChunk:
    start = 0 if first and header else group[0].start
    body = text[start : group[-1].end]
    chunk_text_value = body if first or not header else header + body
    rows = sum(unit.rows for unit in group)
    metadata: dict[str, Any] = {
        "unit": "row",
        "row_start": row_start,
        "row_end": row_start + rows,
        "estimated_rows": rows,
    }
    if header:
        metadata["header"] = header
    if strategy == "spreadsheet":
        sheets: list[dict[str, Any]] = []
        for unit in group:
            if unit.sheet is None and not sheets:
                continue
            if sheets and sheets[-1]["sheet"] == unit.sheet:
                sheets[-1]["row_end"] = unit.sheet_last
            else:
                sheets.append(
                    {"sheet": unit.sheet, "row_start": unit.sheet_first, "row_end": unit.sheet_last}
                )
        if sheets:
            metadata["sheets"] = sheets
        lead = group[0]
        starts_sheet = text[lead.start : lead.end].startswith(_SHEET_PREFIX)
        context = []
        if index and lead.sheet and not starts_sheet:
            context.append(f"Rows continue sheet {lead.sheet}.")
        if index and lead.category and not starts_sheet:
            context.append(
                f'Context from previous section: the current section/category header is '
                f'"{lead.category}". Rows at the beginning of this chunk belong to this '
                f"section until a new section header is encountered."
            )
        if context:
            metadata["context"] = " ".join(context)
    return TextChunk(
        text=chunk_text_value,
        index=index,
        start=start,
        end=group[-1].end,
        strategy=strategy,
        metadata=metadata,
    )


def _chunk_json(text: str, max_chars: int, max_rows: int | None) -> list[TextChunk]:
    try:
        items = json.loads(text)
    except ValueError:
        return []
    if not isinstance(items, list):
        return []
    chunks: list[TextChunk] = []
    current: list[str] = []
    size = 2
    start = 0

    def flush() -> None:
        end = start + len(current)
        chunks.append(
            TextChunk(
                text="[" + ",".join(current) + "]",
                index=len(chunks),
                start=start,
                end=end,
                strategy="json_array",
                metadata={"unit": "row", "row_start": start, "row_end": end,
                          "estimated_rows": len(current)},
            )
        )

    for item in items:
        encoded = json.dumps(item, ensure_ascii=False)
        projected = size + len(encoded) + (1 if current else 0)
        if current and (projected > max_chars or (max_rows and len(current) >= max_rows)):
            flush()
            start += len(current)
            current, projected = [], 2 + len(encoded)
        current.append(encoded)
        size = projected
    if current:
        flush()
    return chunks


def _chunk_html_pages(text: str, max_chars: int, max_pages: int) -> list[TextChunk]:
    starts = [match.start() for match in _PAGE_DIV.finditer(text)]
    if not starts:
        return []
    bounds = list(zip([0, *starts[1:]], [*starts[1:], len(text)]))
    ids = []
    for number, position in enumerate(starts, start=1):
        found = _PAGE_ID.search(text, position, text.find(">", position) + 1)
        ids.append(found.group(1) if found else str(number))
    chunks: list[TextChunk] = []
    group: list[int] = []

    def flush() -> None:
        start, end = bounds[group[0]][0], bounds[group[-1]][1]
        body = text[start:end]
        chunks.append(
            TextChunk(
                text=body,
                index=len(chunks),
                start=start,
                end=end,
                strategy="html_pages",
                metadata={
                    "unit": "page",
                    "page_ids": [ids[i] for i in group],
                    "page_start": group[0],
                    "page_end": group[-1] + 1,
                    "estimated_rows": _html_rows(body),
                },
            )
        )

    for page in range(len(starts)):
        if group and (
            bounds[page][1] - bounds[group[0]][0] > max_chars or len(group) >= max_pages
        ):
            flush()
            group = []
        group.append(page)
    flush()
    return chunks


def _html_rows(html: str) -> int:
    """Table rows with at least five cells (header and layout rows are not counted)."""
    parts = re.split(r"<tr\b", html, flags=re.IGNORECASE)[1:]
    return sum(1 for part in parts if len(re.findall(r"<t[dh]\b", part, re.IGNORECASE)) >= 5)
