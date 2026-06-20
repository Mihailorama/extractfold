from __future__ import annotations

from pathlib import Path
from typing import Any

INVOICE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["invoice_id", "total"],
    "properties": {
        "invoice_id": {"type": "string"},
        "vendor": {"type": "string"},
        "total": {"type": "number"},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["description", "amount"],
                "properties": {
                    "description": {"type": "string"},
                    "amount": {"type": "number"},
                },
            },
        },
    },
}


def write_document(tmp_path: Path, text: str = "Invoice INV-001 total 125.50") -> Path:
    path = tmp_path / "invoice.txt"
    path.write_text(text, encoding="utf-8")
    return path
