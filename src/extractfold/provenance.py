"""Source catalogs and per-field provenance.

A source catalog lists the citable pieces of a document: cells of a sheet or CSV,
layout blocks with page and bounding box (docfold ``bounding_boxes``), HTML blocks,
JSON values or paragraphs. Each entry is a dict with ``id`` and ``text``, location keys
(``page``, ``bbox``, ``block_id``, ``block_type``, ``sheet``, ``cell``, ``path``) and,
when known, the ``start`` / ``end`` offsets of the entry in the source text.

The model cites entry ids per field; :func:`align_provenance` resolves them back to
locations and scores the confidence against the cited text.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Mapping, Sequence
from html.parser import HTMLParser
from typing import Any

_TEXT_KEYS = {"text", "start", "end"}
_HTML_BLOCKS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "caption", "dt",
                "dd", "blockquote"}

PROVENANCE_INSTRUCTIONS = (
    'Return a JSON object with two keys: "rows" and "provenance".\n'
    '- "rows": the extracted rows.\n'
    '- "provenance": an array with one item per row, in the same order. Each item maps every '
    'field name to {"source_refs": [ids of the Source Catalog entries that support the '
    'value], "confidence": number between 0 and 1, "rationale": short explanation}.\n'
    "- Cite only ids present in the Source Catalog. When a value is not in the document, "
    'leave it empty and use "source_refs": [], "confidence": 0.'
)


def build_source_catalog(
    text: str = "",
    *,
    input_format: str | None = None,
    blocks: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Catalog entries for *text*, or for layout *blocks* (docfold bounding boxes)."""
    if blocks is not None:
        return _block_entries(text, blocks)
    fmt = (input_format or "").strip().lower()
    if fmt in {"spreadsheet", "tsv"}:
        return _sheet_entries(text)
    if fmt == "csv":
        return _csv_entries(text)
    if fmt == "json":
        try:
            return [
                {"id": path, "text": _scalar(value), "path": path}
                for path, value in _flatten(json.loads(text), "$")
            ]
        except ValueError:
            pass
    if fmt in {"html", "htm"}:
        parser = _HtmlCatalog(text)
        parser.feed(text)
        parser.close()
        if parser.entries:
            return parser.entries
    return _paragraph_entries(text)


def catalog_for_span(
    catalog: Sequence[Mapping[str, Any]], start: int, end: int
) -> list[dict[str, Any]]:
    """Entries that start inside ``[start, end)``; entries without offsets are always kept."""
    return [
        dict(entry)
        for entry in catalog
        if not isinstance(entry.get("start"), int) or start <= entry["start"] < end
    ]


def catalog_prompt(catalog: Sequence[Mapping[str, Any]], *, max_text: int = 200) -> str:
    """The prompt section listing catalog entries, one JSON object per line."""
    lines = []
    for entry in catalog:
        item = {"id": entry["id"], "text": str(entry.get("text", ""))[:max_text]}
        if "page" in entry:
            item["page"] = entry["page"]
        lines.append(json.dumps(item, ensure_ascii=False))
    return "Source Catalog:\n" + "\n".join(lines) + "\n\n" + PROVENANCE_INSTRUCTIONS


def align_provenance(
    rows: Sequence[Any],
    provenance: Any,
    catalog: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """One ``{field: {source_refs, confidence, rationale, ...}}`` per row.

    ``source_refs`` become the cited entries' locations (unknown ids go to
    ``unknown_refs``). Confidence starts from the model's, then: an empty value 0; no
    sources at least 0.2, sources at least 0.4; the value equal to a cited text 0.95,
    inside it 0.8, containing it 0.75, sharing 60% of its words 0.7.
    """
    lookup = {str(entry["id"]): entry for entry in catalog}
    items = provenance if isinstance(provenance, list) else []
    aligned: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        item = items[index] if index < len(items) and isinstance(items[index], dict) else {}
        fields = list(row) if isinstance(row, dict) else []
        fields += [name for name in item if name not in fields]
        aligned.append(
            {
                name: _align_field(
                    row.get(name) if isinstance(row, dict) else None,
                    item.get(name),
                    lookup,
                )
                for name in fields
            }
        )
    return aligned


def field_confidence(aligned: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Mean confidence per field over aligned rows."""
    totals: dict[str, list[float]] = {}
    for row in aligned:
        for name, info in row.items():
            if isinstance(info, Mapping) and isinstance(info.get("confidence"), (int, float)):
                totals.setdefault(name, []).append(float(info["confidence"]))
    return {name: round(sum(v) / len(v), 3) for name, v in totals.items()}


def _align_field(value: Any, info: Any, lookup: Mapping[str, Mapping[str, Any]]) -> dict:
    info = info if isinstance(info, dict) else {}
    refs = info.get("source_refs") or []
    refs = [str(ref) for ref in refs] if isinstance(refs, list) else []
    known = [lookup[ref] for ref in refs if ref in lookup]
    unknown = [ref for ref in refs if ref not in lookup]
    text = _scalar(value).strip()
    try:
        score = float(info.get("confidence") or 0)
    except (TypeError, ValueError):
        score = 0.0
    if not text:
        score = 0.0
    else:
        score = max(score, 0.4 if known else 0.2)
        lowered = text.lower()
        for entry in known:
            source = str(entry.get("text", "")).lower()
            if lowered == source:
                score = max(score, 0.95)
            elif lowered in source:
                score = max(score, 0.8)
            elif source and source in lowered:
                score = max(score, 0.75)
            elif _overlap(lowered, source) >= 0.6:
                score = max(score, 0.7)
    out: dict[str, Any] = {
        "source_refs": [{k: v for k, v in e.items() if k not in _TEXT_KEYS} for e in known],
        "confidence": min(round(score, 3), 1.0),
        "rationale": str(info.get("rationale") or ""),
    }
    if unknown:
        out["unknown_refs"] = unknown
    return out


def _overlap(value: str, source: str) -> float:
    a, b = set(re.findall(r"\w+", value)), set(re.findall(r"\w+", source))
    return len(a & b) / max(len(a), len(b)) if a and b else 0.0


def _scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _column(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def _lines(text: str) -> list[tuple[int, str]]:
    out, position = [], 0
    for line in text.splitlines(keepends=True):
        out.append((position, line.rstrip("\r\n")))
        position += len(line)
    return out


def _sheet_entries(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    sheet: str | None = None
    row = 0
    for offset, line in _lines(text):
        if line.startswith("Sheet: "):
            sheet, row = line[len("Sheet: ") :].strip(), 0
            continue
        row += 1
        position = offset
        for col, cell in enumerate(line.split("\t")):
            value = cell.strip()
            if value:
                start = position + cell.index(value)
                cell_id = f"{_column(col)}{row}"
                entry: dict[str, Any] = {"id": f"{sheet}!{cell_id}" if sheet else cell_id,
                                         "text": value}
                if sheet:
                    entry["sheet"] = sheet
                entry.update({"cell": cell_id, "start": start, "end": start + len(value)})
                entries.append(entry)
            position += len(cell) + 1
    return entries


def _csv_entries(text: str) -> list[dict[str, Any]]:
    entries = []
    cursor = 0
    for row, record in enumerate(csv.reader(io.StringIO(text)), start=1):
        for col, value in enumerate(record):
            if value.strip():
                cell = f"{_column(col)}{row}"
                entry: dict[str, Any] = {"id": cell, "text": value, "cell": cell}
                found = text.find(value, cursor)  # escaped quotes ("") are not found
                if found >= 0:
                    cursor = found + len(value)
                    entry.update({"start": found, "end": cursor})
                entries.append(entry)
    return entries


def _block_entries(text: str, blocks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    entries = []
    cursor = 0
    for index, block in enumerate(blocks):
        content = str(block.get("text") or "")
        page = block.get("page")
        block_id = str(block.get("id") or f"p{page}-b{index}")
        entry: dict[str, Any] = {"id": block_id, "text": content, "block_id": block_id}
        for key in ("page", "bbox", "polygon", "page_width", "page_height"):
            if block.get(key) is not None:
                entry[key] = block[key]
        if block.get("type"):
            entry["block_type"] = block["type"]
        found = text.find(content, cursor) if content and text else -1
        if found < 0 and content and text:
            found = text.find(content)
        if found >= 0:
            entry.update({"start": found, "end": found + len(content)})
            cursor = found + len(content)
        entries.append(entry)
    return entries


def _paragraph_entries(text: str) -> list[dict[str, Any]]:
    """Runs of non-blank lines."""
    entries: list[dict[str, Any]] = []
    for match in re.finditer(r"[^\n]*\S[^\n]*(?:\n[^\n]*\S[^\n]*)*", text):
        raw = match.group(0)
        start = match.start() + len(raw) - len(raw.lstrip())
        content = raw.strip()
        entries.append({"id": f"para-{len(entries)}", "text": content,
                        "start": start, "end": start + len(content)})
    return entries


def _flatten(value: Any, path: str) -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        return [item for key, child in value.items() for item in _flatten(child, f"{path}.{key}")]
    if isinstance(value, list):
        return [item for i, child in enumerate(value) for item in _flatten(child, f"{path}[{i}]")]
    return [(path, value)]


class _HtmlCatalog(HTMLParser):
    """Block-level elements with the page (``data-page-id``) they sit on."""

    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=True)
        self._text = text
        self._line_starts = [0] + [m.end() for m in re.finditer("\n", text)]
        self.entries: list[dict[str, Any]] = []
        self._stack: list[list[Any]] = []  # [tag, parts, start]
        self._page: str | None = None
        self._counts: dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        page = attributes.get("data-page-id") or attributes.get("data-page")
        if tag == "div" and (page or "page" in (attributes.get("class") or "").split()):
            self._page = page or str(self._counts.get("page", 0) + 1)
            self._counts["page"] = self._counts.get("page", 0) + 1
        if tag in _HTML_BLOCKS:
            self._stack.append([tag, [], self._offset()])

    def handle_data(self, data: str) -> None:
        if self._stack and data.strip():
            self._stack[-1][1].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag not in _HTML_BLOCKS or not self._stack:
            return
        start = None
        while self._stack:
            name, parts, start = self._stack.pop()
            if name == tag:
                break
        content = " ".join(" ".join(parts).split())
        if not content:
            return
        number = self._counts.get(tag, 0)
        self._counts[tag] = number + 1
        entry: dict[str, Any] = {"id": f"{tag}-{number}", "text": content}
        if self._page is not None:
            entry["page"] = self._page
        if start is not None:
            entry.update({"start": start, "end": self._text.find(">", self._offset()) + 1})
        self.entries.append(entry)
        if self._stack:
            self._stack[-1][1].append(content)

    def _offset(self) -> int:
        line, column = self.getpos()
        return self._line_starts[line - 1] + column
