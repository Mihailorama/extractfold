"""JSON Schema inference and template conversion helpers."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from extractfold.engines.base import JsonSchema


@dataclass(frozen=True)
class SchemaConversionResult:
    """Schema plus conversion metadata."""

    schema: JsonSchema
    metadata: dict[str, Any]


def infer_schema(sample: Any) -> JsonSchema:
    """Infer a JSON Schema fragment from a sample value."""
    if isinstance(sample, bool):
        return {"type": "boolean"}
    if isinstance(sample, int):
        return {"type": "integer"}
    if isinstance(sample, float):
        return {"type": "number"}
    if isinstance(sample, str):
        return {"type": "string"}
    if sample is None:
        return {"type": "null"}
    if isinstance(sample, list):
        return {"type": "array", "items": infer_schema(sample[0]) if sample else {}}
    if isinstance(sample, Mapping):
        return {
            "type": "object",
            "properties": {str(key): infer_schema(value) for key, value in sample.items()},
        }
    return {}


def template_to_schema(template: Any) -> SchemaConversionResult:
    """Convert a JSON-like template into a JSON Schema."""
    if isinstance(template, list):
        item_template = template[0] if template else {}
        item_result = template_to_schema(item_template)
        return SchemaConversionResult(
            schema={"type": "array", "items": item_result.schema},
            metadata=item_result.metadata,
        )

    if not isinstance(template, Mapping):
        return SchemaConversionResult(
            schema=infer_schema(template),
            metadata={"computed_fields": {}},
        )

    properties: dict[str, JsonSchema] = {}
    required: list[str] = []
    computed_fields: dict[str, Any] = {}

    for name, field_template in template.items():
        field_name = str(name)
        if _is_computed(field_template):
            computed_fields[field_name] = deepcopy(field_template)
            continue
        if _is_required(field_template):
            required.append(field_name)
        properties[field_name] = _field_to_schema(field_template)

    schema: JsonSchema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return SchemaConversionResult(schema=schema, metadata={"computed_fields": computed_fields})


def _field_to_schema(field_template: Any) -> JsonSchema:
    if not isinstance(field_template, Mapping):
        return infer_schema(field_template)

    if not _looks_like_field_descriptor(field_template):
        return infer_schema(field_template)

    if "sample" in field_template:
        field_schema = infer_schema(field_template["sample"])
    elif "type" in field_template:
        field_schema = {"type": field_template["type"]}
        if field_template.get("type") == "array" and "items" in field_template:
            field_schema["items"] = _field_to_schema(field_template["items"])
        if field_template.get("type") == "object" and isinstance(
            field_template.get("properties"), Mapping
        ):
            field_schema["properties"] = template_to_schema(field_template["properties"]).schema[
                "properties"
            ]
    else:
        field_schema = infer_schema(field_template)

    for key in ("description", "enum"):
        if key in field_template:
            field_schema[key] = deepcopy(field_template[key])
    return field_schema


def _looks_like_field_descriptor(value: Mapping[str, Any]) -> bool:
    return any(
        key in value
        for key in (
            "type",
            "sample",
            "description",
            "required",
            "enum",
            "computed",
            "ComputeField",
        )
    )


def _is_required(value: Any) -> bool:
    return isinstance(value, Mapping) and value.get("required") is True


def _is_computed(value: Any) -> bool:
    return isinstance(value, Mapping) and (
        value.get("computed") is True or value.get("ComputeField") is True
    )
