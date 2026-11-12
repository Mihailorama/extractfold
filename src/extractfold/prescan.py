"""Pre-scan: read a document's head and tail once before extraction.

One LLM call reports the columns, their types, the document structure and control
values (totals, row counts). The result feeds chunk prompts (:meth:`PreScan.context`)
and the row-count check of :func:`extractfold.text.extract_rows_chunked`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from extractfold.engines._common import maybe_await
from extractfold.parsing import parse_llm_json

_PROMPT = (
    "Analyze the following document pages and return a JSON object with:\n"
    "- detected_columns: list of column names found\n"
    "- column_types: mapping of column name to type (text, integer, currency, date, "
    "identifier, etc.)\n"
    "- document_structure: one of 'table', 'list', 'mixed', 'free_text'\n"
    "- control_values: at most 20 totals, row counts, subtotals found (document totals "
    "and row counts first), each with label, value, "
    "parsed_value, value_type (sum, row_count, subtotal, average), target_column, location "
    "(header, footer, inline), confidence (0-1)\n"
    "- suggested_chunk_boundaries: list of section headers or markers where the document "
    "can be split\n"
)


@dataclass
class PreScan:
    """What a pre-scan found; empty when it failed (``error`` says why)."""

    columns: list[str] = field(default_factory=list)
    column_types: dict[str, str] = field(default_factory=dict)
    structure: str = "free_text"
    control_values: list[dict[str, Any]] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=list)
    error: str | None = None
    repaired: bool = False

    @property
    def expected_rows(self) -> int | None:
        """The first row-count control value found with confidence >= 0.8."""
        for value in self.control_values:
            if value.get("value_type") == "row_count" and _num(value.get("confidence")) >= 0.8:
                return int(_num(value.get("parsed_value")))
        return None

    def context(self) -> str:
        """One line for chunk prompts; empty when nothing useful was found."""
        parts: list[str] = []
        if self.columns:
            parts.append(f"Document schema detected: columns [{', '.join(self.columns)}]")
        if self.column_types:
            types = ", ".join(f"{name}: {kind}" for name, kind in self.column_types.items())
            parts.append(f"Column types: {types}")
        if self.structure and self.structure != "free_text":
            parts.append(f"Document structure: {self.structure}")
        if self.control_values:
            values = []
            for value in self.control_values:
                text = f"{value.get('label', '')}={value.get('value', '')}"
                if value.get("target_column"):
                    text += f" (column: {value['target_column']})"
                values.append(text)
            parts.append(f"Control values found: {'; '.join(values)}")
        return "Pre-scan analysis: " + ". ".join(parts) + "." if parts else ""

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "expected_rows": self.expected_rows}


async def prescan(
    text: str,
    *,
    llm: Callable[[str], Any],
    columns: Sequence[str] | None = None,
    instructions: str | None = None,
    head_chars: int = 3000,
    tail_chars: int = 3000,
) -> PreScan:
    """Pre-scan *text* with one call of the injected ``llm(prompt) -> str``.

    The prompt carries the first *head_chars* and last *tail_chars* characters. A failed
    call or an unparseable answer returns an empty :class:`PreScan` with ``error`` set,
    so extraction can go on without it. An answer cut at the token limit keeps its
    complete part (``repaired=True``).
    """
    head = text[:head_chars]
    tail = text[-tail_chars:] if len(text) > head_chars else ""
    parts = [_PROMPT]
    if instructions:
        parts.append(f"\n## Transformation context\n{instructions}\n")
    if columns:
        parts.append(f"\n## Expected attributes\n{', '.join(columns)}\n")
    parts.append(f"\n## First page\n{head or '(empty)'}\n\n## Last page\n{tail or '(empty)'}")
    parts.append("\n\nRespond with ONLY the JSON object, no markdown fences or explanation.")
    try:
        data, repaired = parse_llm_json(str(await maybe_await(llm("".join(parts)))))
        if not isinstance(data, dict):
            raise ValueError("JSON payload must be an object")
    except Exception as exc:
        return PreScan(error=str(exc)[:300])
    return PreScan(
        repaired=repaired,
        columns=[str(c) for c in data.get("detected_columns") or []],
        column_types={str(k): str(v) for k, v in _dict(data.get("column_types")).items()},
        structure=str(data.get("document_structure") or "free_text"),
        control_values=[v for v in data.get("control_values") or [] if isinstance(v, dict)],
        boundaries=[str(b) for b in data.get("suggested_chunk_boundaries") or []],
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
