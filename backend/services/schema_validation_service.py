"""Small JSON Schema validator used at the API boundary.

The canonical contract is JSON Schema.  Keeping validation here avoids trusting
provider structured-output modes and gives callers safe, machine-readable errors.
"""
from __future__ import annotations
from typing import Any


def validate_json_schema(schema: dict, value: Any, path: str = "$") -> list[dict]:
    errors: list[dict] = []
    def fail(message: str, expected: str | None = None):
        errors.append({"path": path, "message": message, "expected": expected})
    if not isinstance(schema, dict):
        return [{"path": path, "message": "Schema must be an object"}]
    if value is None:
        if schema.get("nullable") is True or "null" in schema.get("type", []): return errors
        if schema.get("type") is not None: fail("null is not allowed", str(schema.get("type")))
        return errors
    expected = schema.get("type")
    types = expected if isinstance(expected, list) else [expected] if expected else []
    type_ok = not types or any((t == "object" and isinstance(value, dict)) or (t == "array" and isinstance(value, list)) or (t == "string" and isinstance(value, str)) or (t == "boolean" and isinstance(value, bool)) or (t == "integer" and isinstance(value, int) and not isinstance(value, bool)) or (t == "number" and isinstance(value, (int, float)) and not isinstance(value, bool)) or t == "null" for t in types)
    if not type_ok:
        fail(f"Expected {expected}, received {type(value).__name__}", str(expected)); return errors
    if "enum" in schema and value not in schema["enum"]: fail("Value is not in the allowed enum", "enum")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]: fail("String is shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]: fail("String is longer than maxLength")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]: fail("Number is below minimum")
        if "maximum" in schema and value > schema["maximum"]: fail("Number is above maximum")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value: errors.append({"path": path, "message": f"Missing required property '{key}'", "expected": "required"})
        for key, child in schema.get("properties", {}).items():
            if key in value: errors.extend(validate_json_schema(child, value[key], f"{path}.{key}"))
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in schema.get("properties", {}): errors.append({"path": f"{path}.{key}", "message": "Additional property is not allowed"})
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]: fail("Array has fewer items than minItems")
        if "maxItems" in schema and len(value) > schema["maxItems"]: fail("Array has more items than maxItems")
        if isinstance(schema.get("items"), dict):
            for i, item in enumerate(value): errors.extend(validate_json_schema(schema["items"], item, f"{path}[{i}]"))
    return errors
