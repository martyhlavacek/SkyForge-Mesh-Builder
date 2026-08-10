from __future__ import annotations

import hashlib
from typing import Iterable

from common.canonical_json import canonicalize

QUARANTINE_SCHEMA_VERSION = "skyforge.reconstruction-input-quarantine.v1"
QUARANTINED_HASHES = {
    "ff3d6931b1b4eb79cab63d6e0b3cf29d07f911878d39b137473111daf00af58f": {
        "role": "front",
        "reason": "MBS-195 geometric incoherence",
    },
    "d787043b91dc58cb3cc443a73ef562ea6550a14d45463b20c36eff518ce37c11": {
        "role": "right",
        "reason": "MBS-195 geometric incoherence",
    },
}


class QuarantineError(ValueError):
    """Raised when rejected evidence is reused as reconstruction input."""


def quarantine_record() -> dict[str, object]:
    return {
        "schemaVersion": QUARANTINE_SCHEMA_VERSION,
        "entries": [
            {"sha256": digest, **QUARANTINED_HASHES[digest]}
            for digest in sorted(QUARANTINED_HASHES)
        ],
    }


def quarantine_digest() -> str:
    return hashlib.sha256(canonicalize(quarantine_record())).hexdigest()


def assert_reconstruction_hashes_eligible(hashes: Iterable[str]) -> None:
    rejected = sorted(set(hashes) & set(QUARANTINED_HASHES))
    if rejected:
        raise QuarantineError(
            "Rejected MBS-195 evidence is quarantined from reconstruction/provider input: "
            + ", ".join(rejected)
        )
