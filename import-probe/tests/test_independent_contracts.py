from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from probe.contracts import CONTRACT_ROOT, SCHEMA_ROOT, ProbeContractError, load_json, load_schema, validate

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_contract_copy_matches_its_release_checksum_manifest():
    expected: dict[str, str] = {}
    for line in (PACKAGE_ROOT / "CONTRACTS_SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        expected[relative] = digest
    actual = {
        path.relative_to(PACKAGE_ROOT).as_posix(): sha256(path)
        for path in sorted(CONTRACT_ROOT.rglob("*.json"))
    }
    assert actual == expected


def test_every_probe_schema_is_independently_valid():
    for path in sorted(SCHEMA_ROOT.glob("*.json")):
        schema = load_schema(path.name)
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False


def test_probe_accepts_frozen_manufacturing_axes_and_rejects_ownership_mutation():
    document = load_json(CONTRACT_ROOT / "examples" / "manufacturing_axes_valid.json")
    validate("manufacturing_axes.schema.json", document)
    mutation = json.loads(json.dumps(document))
    mutation["ownership"]["perFrameSocketProjection"] = "mesh_foundry"
    with pytest.raises(ProbeContractError):
        validate("manufacturing_axes.schema.json", mutation)


def test_probe_rejects_unknown_embedded_authority():
    invalid = load_json(CONTRACT_ROOT / "examples" / "authority_unknown_embedded_invalid.json")
    with pytest.raises(ProbeContractError):
        validate("authority_manifest.schema.json", invalid)


def test_probe_contract_origin_forbids_runtime_producer_import():
    origin = load_json(PACKAGE_ROOT / "CONTRACT_ORIGIN.json")
    assert origin["runtimeProducerImportPermitted"] is False
    assert origin["contractProfile"] == "skyforge.vmp-content-digest.v1"


def test_probe_source_contains_no_mesh_foundry_runtime_imports():
    forbidden = ("from app", "import app", "from common", "import common")
    for path in sorted((PACKAGE_ROOT / "probe").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{path.name}: {token}"
