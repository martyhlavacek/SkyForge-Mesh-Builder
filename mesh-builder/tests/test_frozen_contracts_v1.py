from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from common.schema_validation import (
    CONTRACT_ROOT,
    EXAMPLE_ROOT,
    SCHEMA_ROOT,
    ContractValidationError,
    check_schema,
    load_json,
    load_schema,
    validate_document,
    validate_example,
)
from scripts import generate_contract_schemas, seal_release

PACKAGE_ROOT = Path(__file__).resolve().parents[1]

POSITIVE_VECTORS = {
    "authority_manifest.schema.json": [
        "authority_embedded_valid.json",
        "authority_hash_only_valid.json",
    ],
    "validated_mesh_package.schema.json": [
        "manifest_optional_absent_valid.json",
        "manifest_optional_present_valid.json",
        "manifest_producer_version_rebuild_valid.json",
    ],
    "frame_contract.schema.json": ["frame_contract_valid.json"],
    "known_limitations.schema.json": ["known_limitations_valid.json"],
    "manufacturing_axes.schema.json": ["manufacturing_axes_valid.json"],
    "provider_task_record.schema.json": ["provider_task_recovery_valid.json"],
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def test_all_frozen_schemas_are_valid_draft_2020_12_documents():
    schema_paths = sorted(SCHEMA_ROOT.glob("*.json"))
    assert len(schema_paths) >= 20
    for path in schema_paths:
        check_schema(path.name)
        schema = load_schema(path.name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False


@pytest.mark.parametrize(
    ("schema_filename", "example_filename"),
    [
        (schema_filename, example_filename)
        for schema_filename, examples in POSITIVE_VECTORS.items()
        for example_filename in examples
    ],
)
def test_positive_contract_vectors(schema_filename: str, example_filename: str):
    validate_example(schema_filename, example_filename)


@pytest.mark.parametrize(
    ("schema_filename", "example_filename"),
    [
        ("authority_manifest.schema.json", "authority_unknown_embedded_invalid.json"),
        ("validated_mesh_package.schema.json", "manifest_explicit_null_invalid.json"),
    ],
)
def test_required_negative_contract_vectors_are_rejected(
    schema_filename: str, example_filename: str
):
    with pytest.raises(ContractValidationError):
        validate_example(schema_filename, example_filename)


def test_optional_digest_fields_are_omitted_or_present_but_never_null():
    absent = load_json(EXAMPLE_ROOT / "manifest_optional_absent_valid.json")
    present = load_json(EXAMPLE_ROOT / "manifest_optional_present_valid.json")
    invalid = load_json(EXAMPLE_ROOT / "manifest_explicit_null_invalid.json")
    assert "providerModel" not in absent["producer"]
    assert "providerEvidencePackageSha256" not in absent["source"]
    assert "supersession" not in absent
    assert present["producer"]["providerModel"]
    assert present["source"]["providerEvidencePackageSha256"]
    assert present["supersession"]["reasonCode"] == "producer_version_rebuild"
    assert invalid["producer"]["providerModel"] is None
    with pytest.raises(ContractValidationError):
        validate_document("validated_mesh_package.schema.json", invalid)


def test_digest_profile_field_set_is_exhaustive_and_frozen():
    profile = load_json(EXAMPLE_ROOT / "manifest_optional_absent_valid.json")["digestProfile"]
    assert profile == generate_contract_schemas.digest_profile_value()
    assert profile["unknownFieldPolicy"] == "excluded"
    assert profile["optionalFieldEncoding"] == {
        "absent": "omitted",
        "explicitNull": "prohibited",
    }
    assert "producer.sidecarVersion" in profile["includedManifestFields"]
    assert "contentIndex" in profile["includedManifestFields"]


def test_unknown_v1_manifest_field_is_rejected():
    document = load_json(EXAMPLE_ROOT / "manifest_optional_absent_valid.json")
    document["futureSemanticField"] = "must require a new schema/profile"
    with pytest.raises(ContractValidationError, match="Additional properties"):
        validate_document("validated_mesh_package.schema.json", document)


def test_authority_embedding_is_fail_closed():
    permitted = load_json(EXAMPLE_ROOT / "authority_embedded_valid.json")
    hash_only = load_json(EXAMPLE_ROOT / "authority_hash_only_valid.json")
    validate_document("authority_manifest.schema.json", permitted)
    validate_document("authority_manifest.schema.json", hash_only)
    mutation = json.loads(json.dumps(hash_only))
    mutation["authorities"][0].update(
        {
            "embedded": True,
            "embeddedPath": "authorities/silhouette_authority.png",
        }
    )
    with pytest.raises(ContractValidationError):
        validate_document("authority_manifest.schema.json", mutation)


def test_frame_contract_requires_calibration_envelope_and_excludes_runtime_effects():
    frame = load_json(EXAMPLE_ROOT / "frame_contract_valid.json")
    assert frame["calibrationEnvelope"]["runtimeEffectsEnabled"] is False
    validate_document("frame_contract.schema.json", frame)
    frame.pop("calibrationEnvelope")
    with pytest.raises(ContractValidationError):
        validate_document("frame_contract.schema.json", frame)

    limitations = load_json(EXAMPLE_ROOT / "known_limitations_valid.json")
    excluded = limitations["limitations"][0]["excludedRuntimeEffects"]
    assert excluded == [
        "thrusters",
        "muzzle_flashes",
        "shadows",
        "debris",
        "other_sprite_foundry_effects",
    ]
    validate_document("known_limitations.schema.json", limitations)


def test_manufacturing_axes_match_versioned_sf_am_0001_enumeration_exactly():
    document = load_json(EXAMPLE_ROOT / "manufacturing_axes_valid.json")
    expected = {
        "runtimeTransforms": ["yaw", "position", "alpha", "approved_tint"],
        "bakedCandidateAxes": ["bank", "pitch", "damage_state", "destruction_sequence"],
        "independentLayers": ["hull", "thruster", "shadow", "emission", "recolour_mask"],
        "crossProductBakeProhibited": True,
        "ownership": {
            "bankPitchRendering": "sprite_foundry",
            "perFrameSocketProjection": "sprite_foundry",
            "runtimeSocketAcceptance": "gameplay_integration",
        },
    }
    assert {key: document[key] for key in expected} == expected
    validate_document("manufacturing_axes.schema.json", document)
    mutation = json.loads(json.dumps(document))
    mutation["ownership"]["perFrameSocketProjection"] = "mesh_foundry"
    with pytest.raises(ContractValidationError):
        validate_document("manufacturing_axes.schema.json", mutation)


def test_effective_sf_am_0001_assigns_socket_projection_to_sprite_foundry():
    governing = (PACKAGE_ROOT / "docs" / "governance" / "SF-AM-0001.md").read_text(encoding="utf-8")
    normalized = " ".join(governing.split())
    assert "**Status:** EFFECTIVE" in governing
    assert "Mesh Foundry may emit approved or candidate three-dimensional sockets" in normalized
    assert "Sprite Foundry owns projection" in normalized
    assert "Gameplay integration validates and consumes" in normalized
    assert "must not reach back into Mesh Foundry" in normalized


def test_provider_task_record_carries_complete_recovery_correlation_and_stays_unresolved():
    task = load_json(EXAMPLE_ROOT / "provider_task_recovery_valid.json")
    required = {
        "requestDigest",
        "providerId",
        "providerModel",
        "resolvedProviderOptionsDigest",
        "authoritySetSha256",
        "accountIdentityDigest",
        "dispatchWindowStart",
        "dispatchWindowEnd",
        "expectedCost",
    }
    assert set(task["recoveryCorrelation"]) == required
    assert task["state"] == "unresolved"
    assert task["correspondenceStatus"] == "zero_matches_unresolved"
    validate_document("provider_task_record.schema.json", task)


def test_air_moving_is_the_only_asset_role_accepted():
    valid = {
        "schemaVersion": "skyforge.asset-role.v1",
        "preset": "air_moving",
        "capabilities": {
            "timelineMovement": True,
            "airborne": True,
            "terrainPlacement": False,
            "directionalGroundSet": False,
        },
    }
    validate_document("asset_role.schema.json", valid)
    for unsupported in ("ground_moving", "ground_static"):
        mutation = json.loads(json.dumps(valid))
        mutation["preset"] = unsupported
        with pytest.raises(ContractValidationError):
            validate_document("asset_role.schema.json", mutation)


def test_validation_and_structural_schemas_cannot_assert_downstream_readiness():
    report = {
        "schemaVersion": "skyforge.validation-report.v1",
        "validationClass": "blender",
        "validatorVersion": "0.7.1",
        "sourceGlbSha256": "1" * 64,
        "executedAt": "2026-08-01T00:00:00Z",
        "measuredValues": [{"name": "silhouetteIoU", "value": 0.95}],
        "gates": [
            {
                "name": "silhouetteIoU",
                "passed": True,
                "measuredValue": 0.95,
                "thresholdOperator": ">=",
                "thresholdValue": 0.94,
            }
        ],
        "passed": True,
        "failureReasons": [],
    }
    validate_document("validation_report.schema.json", report)
    report["spriteFoundryReady"] = True
    with pytest.raises(ContractValidationError):
        validate_document("validation_report.schema.json", report)

    structural = {
        "schemaVersion": "skyforge.structural-measurements.v1",
        "sourceGlbSha256": "2" * 64,
        "measurements": [{"name": "minimumFeatureScale", "value": 0.02, "unit": "world_units"}],
        "topologyLimitations": [],
    }
    validate_document("structural_measurements.schema.json", structural)
    structural["destructionEligible"] = True
    with pytest.raises(ContractValidationError):
        validate_document("structural_measurements.schema.json", structural)


def test_no_schema_declares_json_null_as_an_allowed_type():
    for path in sorted(SCHEMA_ROOT.glob("*.json")):
        for node in _walk(load_json(path)):
            if not isinstance(node, dict) or "type" not in node:
                continue
            declared = node["type"]
            if isinstance(declared, str):
                assert declared != "null", path.name
            elif isinstance(declared, list):
                assert "null" not in declared, path.name


def test_producer_version_rebuild_has_explicit_supersession_reason():
    manifest = load_json(EXAMPLE_ROOT / "manifest_producer_version_rebuild_valid.json")
    assert "producer.sidecarVersion" in manifest["digestProfile"]["includedManifestFields"]
    assert manifest["supersession"]["reasonCode"] == "producer_version_rebuild"
    validate_document("validated_mesh_package.schema.json", manifest)


def test_governance_files_are_byte_identical_to_v060_baseline():
    baseline = load_json(PACKAGE_ROOT / "docs" / "v0.7.1" / "GOVERNANCE_BASELINE_HASHES.json")
    assert len(baseline["files"]) == 12
    for relative, expected in baseline["files"].items():
        assert _sha256(PACKAGE_ROOT / relative) == expected, relative


def test_schema_and_jcs_dependencies_are_exactly_pinned_and_release_bound():
    requirements = (PACKAGE_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert "jsonschema==4.26.0" in requirements
    assert "rfc8785==0.1.4" in requirements
    assert seal_release.REQUIRED_DISTRIBUTIONS["jsonschema"] == "4.26.0"
    assert seal_release.REQUIRED_DISTRIBUTIONS["rfc8785"] == "0.1.4"


def test_schema_generation_is_byte_deterministic():
    before = {
        path.relative_to(CONTRACT_ROOT).as_posix(): _sha256(path)
        for path in sorted(CONTRACT_ROOT.rglob("*.json"))
    }
    subprocess.run(
        [sys.executable, str(PACKAGE_ROOT / "scripts" / "generate_contract_schemas.py")],
        cwd=PACKAGE_ROOT,
        check=True,
    )
    after = {
        path.relative_to(CONTRACT_ROOT).as_posix(): _sha256(path)
        for path in sorted(CONTRACT_ROOT.rglob("*.json"))
    }
    assert before == after


def test_schema_index_lists_every_frozen_schema_and_example():
    index = load_json(CONTRACT_ROOT / "SCHEMA_INDEX.json")
    assert index["packageVersion"] == "1.0.0"
    assert index["digestProfile"] == "skyforge.vmp-content-digest.v1"
    assert index["schemas"] == sorted(path.name for path in SCHEMA_ROOT.glob("*.json"))
    assert index["examples"] == sorted(path.name for path in EXAMPLE_ROOT.glob("*.json"))


def test_frozen_schemas_have_no_unresolved_external_references():
    for path in sorted(SCHEMA_ROOT.glob("*.json")):
        schema = load_json(path)
        for node in _walk(schema):
            if isinstance(node, dict) and "$ref" in node:
                assert not str(node["$ref"]).startswith(("http://", "https://")), path.name
        Draft202012Validator.check_schema(schema)
