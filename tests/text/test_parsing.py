from __future__ import annotations

import pytest

from extractfold.engines._common import extract_data_payload
from extractfold.parsing import (
    normalize_data_payload,
    parse_json_array,
    parse_json_object,
    parse_json_payload,
)


def test_parse_json_payload_accepts_raw_object() -> None:
    assert parse_json_payload('{"name": "Ada"}') == {"name": "Ada"}


def test_parse_json_payload_accepts_raw_array() -> None:
    assert parse_json_payload('[{"name": "Ada"}, {"name": "Grace"}]') == [
        {"name": "Ada"},
        {"name": "Grace"},
    ]


def test_parse_json_payload_accepts_fenced_object() -> None:
    assert parse_json_payload('```json\n{"invoice_id": "INV-001"}\n```') == {
        "invoice_id": "INV-001"
    }


def test_parse_json_payload_accepts_fenced_array() -> None:
    assert parse_json_payload('```json\n[{"sku": "A-1"}]\n```') == [{"sku": "A-1"}]


def test_parse_json_payload_recovers_prose_wrapped_json() -> None:
    text = 'The extracted payload is:\n{"vendor": "Acme", "total": 125.5}\nDone.'

    assert parse_json_payload(text) == {"vendor": "Acme", "total": 125.5}


def test_parse_json_object_requires_object_payload() -> None:
    with pytest.raises(ValueError, match="object"):
        parse_json_object('[{"name": "Ada"}]')


def test_parse_json_array_requires_array_payload() -> None:
    with pytest.raises(ValueError, match="array"):
        parse_json_array('{"name": "Ada"}')


@pytest.mark.parametrize(
    "payload",
    [
        {"rows": [{"name": "Ada"}]},
        {"data": {"rows": [{"name": "Ada"}]}},
        {"result": {"rows": [{"name": "Ada"}]}},
        [{"name": "Ada"}],
        '[{"name": "Ada"}]',
    ],
)
def test_normalize_data_payload_wraps_rows(payload) -> None:
    assert normalize_data_payload(payload) == {"rows": [{"name": "Ada"}]}


def test_normalize_data_payload_preserves_field_value_wrapper() -> None:
    payload = {
        "fields": {
            "invoice_id": {"value": "INV-001", "confidence": 0.9},
            "total": {"value": 125.5},
        }
    }

    assert normalize_data_payload(payload) == {"invoice_id": "INV-001", "total": 125.5}


def test_parse_json_payload_raises_clear_error_for_non_json_text() -> None:
    with pytest.raises(ValueError, match="Could not parse JSON payload"):
        parse_json_payload("no structured data here")


def test_common_extract_data_payload_uses_new_array_parser() -> None:
    assert extract_data_payload('```json\n[{"name": "Ada"}]\n```') == {
        "rows": [{"name": "Ada"}]
    }


def test_parse_llm_json_clean_answers_are_not_repaired() -> None:
    from extractfold.parsing import parse_llm_json

    assert parse_llm_json('{"rows": [1]}') == ({"rows": [1]}, False)
    assert parse_llm_json('Sure:\n```json\n[{"a": 1}]\n```') == ([{"a": 1}], False)
    assert parse_llm_json('Result: {"a": 1} done') == ({"a": 1}, False)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"rows": [{"a": 1}, {"a": 2}, {"a"', {"rows": [{"a": 1}, {"a": 2}]}),
        ('{"rows": [{"a": 1, "b": "x"}, {"a": 2, "b": "unfinish', {"rows": [{"a": 1, "b": "x"}]}),
        ('[{"a": "q\\"uote"}, {"a": 3', [{"a": 'q"uote'}]),
        ('{"rows": [{"a": "}"}, {"a": [1, 2', {"rows": [{"a": "}"}]}),
        (
            '{"rows": [], "provenance": [{"a": {"c": 0.5}}, ',
            {"rows": [], "provenance": [{"a": {"c": 0.5}}]},
        ),
    ],
)
def test_parse_llm_json_closes_truncated_answers(text: str, expected: object) -> None:
    from extractfold.parsing import _close_truncated, parse_llm_json

    assert parse_llm_json(text) == (expected, True)
    assert _close_truncated(text) == expected


def test_parse_llm_json_raises_on_text_without_json() -> None:
    from extractfold.parsing import parse_llm_json

    with pytest.raises(ValueError):
        parse_llm_json("no json at all")


def test_parse_llm_json_uses_json_repair_for_other_damage() -> None:
    from extractfold.parsing import parse_llm_json

    json_repair = pytest.importorskip("json_repair")
    assert json_repair is not None
    assert parse_llm_json("{a: 1, 'b': 2,}") == ({"a": 1, "b": 2}, True)
