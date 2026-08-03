from __future__ import annotations

import json
from pathlib import Path

import pytest

import probe.vmp_validator as validator
from probe.vmp_validator import import_vmp

ROOT = Path(__file__).resolve().parents[1]


def simple_canonicalize(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


@pytest.fixture(autouse=True)
def canonicalizer(monkeypatch):
    monkeypatch.setattr(validator, "canonicalize", simple_canonicalize)


@pytest.mark.parametrize(
    ("filename", "authority_state"),
    [("valid_embedded.sfmeshpack", "full"), ("valid_hash_only.sfmeshpack", "unavailable_due_to_terms")],
)
def test_independent_probe_accepts_valid_packages(filename: str, authority_state: str):
    receipt = import_vmp(ROOT / "tests/fixtures" / filename, created_at="2026-08-01T00:00:00Z")
    assert receipt["accepted"] is True
    assert receipt["authorityReverification"] == authority_state
    assert receipt["manufacturingAxesVerified"] is True
    assert receipt["collisionHintsIgnoredForRuntime"] is True
    assert any(item.startswith("glb_vertices=") for item in receipt["diagnostics"])
