from __future__ import annotations

import hashlib
import importlib
from typing import Any

JCS_IMPLEMENTATION = "rfc8785"
JCS_DISTRIBUTION = "rfc8785"
JCS_VERSION = "0.1.4"
DIGEST_ALGORITHM = "sha256"


class CanonicalizationUnavailable(RuntimeError):
    """Raised when the exact RFC 8785 implementation is unavailable."""


def canonicalize(value: Any) -> bytes:
    try:
        implementation = importlib.import_module(JCS_IMPLEMENTATION)
    except ModuleNotFoundError as exc:
        raise CanonicalizationUnavailable(
            f"{JCS_DISTRIBUTION}=={JCS_VERSION} is required for RFC 8785 JCS"
        ) from exc
    encoded = implementation.dumps(value)
    if not isinstance(encoded, bytes):
        raise CanonicalizationUnavailable("RFC 8785 implementation returned non-byte output")
    return encoded


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonicalize(value)).hexdigest()
