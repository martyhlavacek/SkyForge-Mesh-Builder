from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

CONTRACT_ROOT = Path(__file__).resolve().parents[1] / "contracts" / "vmp" / "v1"
SCHEMA_ROOT = CONTRACT_ROOT / "schemas"
EXAMPLE_ROOT = CONTRACT_ROOT / "examples"


class ContractValidationError(ValueError):
    """Raised when a frozen SkyForge contract or document is invalid."""


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_schema(filename: str) -> dict[str, Any]:
    path = SCHEMA_ROOT / filename
    if not path.is_file():
        raise ContractValidationError(f"Unknown frozen schema: {filename}")
    value = load_json(path)
    if not isinstance(value, dict):
        raise ContractValidationError(f"Schema is not a JSON object: {filename}")
    return value


def check_schema(filename: str) -> None:
    try:
        Draft202012Validator.check_schema(load_schema(filename))
    except SchemaError as exc:
        raise ContractValidationError(f"Invalid frozen schema {filename}: {exc.message}") from exc


def validate_document(filename: str, document: Any) -> None:
    schema = load_schema(filename)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        location = "/".join(str(item) for item in error.absolute_path) or "<root>"
        raise ContractValidationError(f"{filename} rejected {location}: {error.message}")


def validate_example(schema_filename: str, example_filename: str) -> None:
    validate_document(schema_filename, load_json(EXAMPLE_ROOT / example_filename))
