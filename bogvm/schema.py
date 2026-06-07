from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


class SchemaError(Exception):
    pass


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def validate_schema(instance: object, schema_name: str) -> None:
    validator = _validator(schema_name)
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path) or "$"
        raise SchemaError(f"{schema_name} validation failed at {location}: {error.message}")


@lru_cache(maxsize=None)
def _validator(schema_name: str):
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise SchemaError("schema validation requires the jsonschema package") from exc

    try:
        schema = json.loads((SCHEMA_DIR / schema_name).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaError(f"invalid schema {schema_name}: {exc}") from exc

    return Draft202012Validator(schema)
