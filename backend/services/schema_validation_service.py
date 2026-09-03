"""JSON Schema validator used at the API boundary.

Uses the python `jsonschema` library for full standard compliance.
Returns structured error messages with JSON paths.
"""
from __future__ import annotations
from typing import Any
import jsonschema


def validate_json_schema(schema: dict, value: Any, path: str = "$") -> list[dict]:
    if not isinstance(schema, dict):
        return [{"path": path, "message": "Schema must be an object", "expected": "dict"}]

    validator = jsonschema.Draft202012Validator(schema)
    errors: list[dict] = []

    for err in validator.iter_errors(value):
        # Format path into a readable JSONPath representation e.g. $.items[0].name
        json_path = path
        for elem in err.path:
            if isinstance(elem, int):
                json_path += f"[{elem}]"
            else:
                json_path += f".{elem}"

        errors.append({
            "path": json_path,
            "message": err.message,
            "expected": str(err.validator) if err.validator else None,
        })

    return errors
