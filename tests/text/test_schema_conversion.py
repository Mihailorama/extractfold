from __future__ import annotations

from extractfold.schema import SchemaConversionResult, infer_schema, template_to_schema


def test_infer_schema_from_object_sample() -> None:
    schema = infer_schema(
        {
            "vendor": "Acme",
            "total": 125.5,
            "line_count": 3,
            "paid": False,
            "notes": None,
        }
    )

    assert schema == {
        "type": "object",
        "properties": {
            "vendor": {"type": "string"},
            "total": {"type": "number"},
            "line_count": {"type": "integer"},
            "paid": {"type": "boolean"},
            "notes": {"type": "null"},
        },
    }


def test_infer_schema_from_row_array_sample() -> None:
    schema = infer_schema(
        [
            {
                "sku": "A-1",
                "quantity": 2,
                "amount": 19.99,
            }
        ]
    )

    assert schema == {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "quantity": {"type": "integer"},
                "amount": {"type": "number"},
            },
        },
    }


def test_template_to_schema_preserves_field_metadata() -> None:
    result = template_to_schema(
        {
            "status": {
                "type": "string",
                "description": "Lifecycle status",
                "required": True,
                "enum": ["new", "paid"],
            },
            "total": {
                "sample": 125.5,
                "description": "Grand total",
            },
        }
    )

    assert isinstance(result, SchemaConversionResult)
    assert result.schema == {
        "type": "object",
        "required": ["status"],
        "properties": {
            "status": {
                "type": "string",
                "description": "Lifecycle status",
                "enum": ["new", "paid"],
            },
            "total": {
                "type": "number",
                "description": "Grand total",
            },
        },
    }
    assert result.metadata == {"computed_fields": {}}


def test_template_to_schema_excludes_computed_fields_and_keeps_metadata() -> None:
    result = template_to_schema(
        {
            "vendor": {"type": "string"},
            "score": {
                "type": "number",
                "description": "Confidence score computed after extraction",
                "computed": True,
            },
            "legacy_score": {
                "type": "integer",
                "description": "Legacy computed score",
                "ComputeField": True,
            },
        }
    )

    assert result.schema == {
        "type": "object",
        "properties": {
            "vendor": {"type": "string"},
        },
    }
    assert result.metadata == {
        "computed_fields": {
            "score": {
                "type": "number",
                "description": "Confidence score computed after extraction",
                "computed": True,
            },
            "legacy_score": {
                "type": "integer",
                "description": "Legacy computed score",
                "ComputeField": True,
            },
        }
    }


def test_template_to_schema_treats_array_templates_as_rows() -> None:
    result = template_to_schema(
        [
            {
                "sku": {"type": "string", "required": True},
                "quantity": {"type": "integer"},
            }
        ]
    )

    assert result.schema == {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["sku"],
            "properties": {
                "sku": {"type": "string"},
                "quantity": {"type": "integer"},
            },
        },
    }
    assert result.metadata == {"computed_fields": {}}
