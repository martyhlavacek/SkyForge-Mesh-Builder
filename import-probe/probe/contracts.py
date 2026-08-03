from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = PACKAGE_ROOT / "contracts" / "vmp" / "v1"
SCHEMA_ROOT = CONTRACT_ROOT / "schemas"


class ProbeContractError(ValueError):
    """Raised when a package document violates the probe's independent contract copy."""


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_schema(filename: str) -> dict[str, Any]:
    path = SCHEMA_ROOT / filename
    if not path.is_file():
        raise ProbeContractError(f"Unsupported schema: {filename}")
    value = load_json(path)
    if not isinstance(value, dict):
        raise ProbeContractError(f"Schema is not an object: {filename}")
    return value


def validate(filename: str, document: Any) -> None:
    schema = load_schema(filename)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        location = "/".join(str(item) for item in error.absolute_path) or "<root>"
        raise ProbeContractError(f"{filename} rejected {location}: {error.message}")
