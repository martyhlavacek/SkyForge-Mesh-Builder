from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import Any, Mapping

from .errors import ProbeReject

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROFILE_SCHEMA = PACKAGE_ROOT / "contracts/vmp/v1/schemas/vmp_content_digest_profile.schema.json"


def canonicalize(value: Any) -> bytes:
    try:
        module = importlib.import_module("rfc8785")
    except ModuleNotFoundError as exc:
        raise ProbeReject("canonicalizer_unavailable", "rfc8785==0.1.4 is required") from exc
    encoded = module.dumps(value)
    if not isinstance(encoded, bytes):
        raise ProbeReject("canonicalizer_invalid", "RFC 8785 implementation returned non-bytes")
    return encoded


def build_digest_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    schema = json.loads(PROFILE_SCHEMA.read_text(encoding="utf-8"))
    included = schema["properties"]["includedManifestFields"]["const"]
    result: dict[str, Any] = {}
    for dotted in included:
        value, present = _get(manifest, dotted)
        if not present:
            continue
        if value is None:
            raise ProbeReject("digest_explicit_null", f"digest field may not be null: {dotted}")
        _set(result, dotted, value)
    return result


def content_digest(manifest: Mapping[str, Any], canonicalizer=canonicalize) -> str:
    return hashlib.sha256(canonicalizer(build_digest_payload(manifest))).hexdigest()


def _get(document: Mapping[str, Any], dotted: str) -> tuple[Any, bool]:
    value: Any = document
    for part in dotted.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None, False
        value = value[part]
    return value, True


def _set(document: dict[str, Any], dotted: str, value: Any) -> None:
    current = document
    parts = dotted.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value
