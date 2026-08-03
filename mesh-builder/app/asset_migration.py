from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from common.schema_validation import ContractValidationError, validate_document

LEGACY_SCHEMA = "skyforge.asset.sidecar.v3.0"
ASSET_V3_SCHEMA = "skyforge.asset.v3"
SUPPORTED_ROLE = "air_moving"
LOCAL_PROVIDER_ID = "local_deterministic"
LOCAL_IDENTITY_MODEL = "deterministic_reproducibility"


class AssetMigrationError(ValueError):
    """Raised when legacy meaning cannot be migrated without inference."""


@dataclass(frozen=True)
class AssetMigrationResult:
    asset_v3: dict[str, Any]
    report: dict[str, Any]
    legacy_projection: dict[str, Any]

    @property
    def asset_bytes(self) -> bytes:
        return canonical_json_bytes(self.asset_v3)

    @property
    def report_bytes(self) -> bytes:
        return canonical_json_bytes(self.report)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migrate_asset(
    legacy: Mapping[str, Any],
    *,
    source_manifest: Mapping[str, Any],
    approval: Mapping[str, Any],
    asset_version: str,
    asset_role: str = SUPPORTED_ROLE,
) -> AssetMigrationResult:
    if legacy.get("schemaVersion") == ASSET_V3_SCHEMA:
        document = dict(legacy)
        _validate_v3(document)
        report = {
            "schemaVersion": "skyforge.asset-migration-report.v1",
            "migration": "validated_no_op",
            "sourceSchema": ASSET_V3_SCHEMA,
            "targetSchema": ASSET_V3_SCHEMA,
            "assetSha256": sha256_bytes(canonical_json_bytes(document)),
            "inferencesMade": [],
            "preservedLegacyFields": [],
        }
        return AssetMigrationResult(document, report, {})

    if legacy.get("schemaVersion") != LEGACY_SCHEMA:
        raise AssetMigrationError(f"Unsupported source asset schema: {legacy.get('schemaVersion')!r}")
    if asset_role != SUPPORTED_ROLE:
        raise AssetMigrationError(f"Unsupported asset role: {asset_role!r}")
    existing_role = legacy.get("assetRole")
    if existing_role is not None and existing_role != asset_role:
        raise AssetMigrationError("Legacy asset role contradicts the requested migration role")

    asset_id = _required_string(legacy, "assetId")
    craft_profile_id = _required_string(legacy, "profileId")
    if "anchors" not in legacy:
        raise AssetMigrationError("Legacy anchors state is absent; migration may not infer it")
    anchors = legacy.get("anchors")
    if anchors is None:
        anchor_state = "not_authored"
    elif isinstance(anchors, dict) and anchors:
        anchor_state = "authored"
    else:
        raise AssetMigrationError("Legacy anchors value is ambiguous")

    _validate_approval(approval)
    generator = legacy.get("generator")
    if not isinstance(generator, dict):
        raise AssetMigrationError("Legacy generator lineage is required")
    generator_id = generator.get("generatorId")
    mesh_origin = (source_manifest.get("mesh") or {}).get("origin")
    if generator_id != "skyforge.authority-two-sided-field" or mesh_origin != "generated_from_authority":
        raise AssetMigrationError("Provider identity cannot be set to local_deterministic from this lineage")

    asset_v3: dict[str, Any] = {
        "schemaVersion": ASSET_V3_SCHEMA,
        "assetId": asset_id,
        "assetVersion": asset_version,
        "craftProfileId": craft_profile_id,
        "assetRole": asset_role,
        "provider": {"id": LOCAL_PROVIDER_ID, "identityModel": LOCAL_IDENTITY_MODEL},
        "geometry": {"normalizedGlb": "mesh/normalized.glb"},
        "approval": {"state": "approved", "approvedForDistribution": True},
        "anchorState": anchor_state,
    }
    collision = legacy.get("collision")
    if collision is not None:
        if not isinstance(collision, dict) or collision.get("type") != "ellipse":
            raise AssetMigrationError("Only an explicit legacy collision ellipse can become a collision hint")
        asset_v3["collisionHint"] = {
            "authoritative": False,
            "consumerMustIgnoreForRuntime": True,
            "sourceSchema": LEGACY_SCHEMA,
            "description": "Legacy sidecar collision ellipse; informational only.",
        }

    _validate_v3(asset_v3)
    legacy_projection = _legacy_projection(legacy)
    legacy_bytes = canonical_json_bytes(dict(legacy))
    report = {
        "schemaVersion": "skyforge.asset-migration-report.v1",
        "migration": "legacy_v3_to_asset_v3",
        "sourceSchema": LEGACY_SCHEMA,
        "targetSchema": ASSET_V3_SCHEMA,
        "legacyAssetSha256": sha256_bytes(legacy_bytes),
        "assetSha256": sha256_bytes(canonical_json_bytes(asset_v3)),
        "sourceManifestSha256": sha256_bytes(canonical_json_bytes(dict(source_manifest))),
        "providerIdentity": LOCAL_PROVIDER_ID,
        "assetRole": asset_role,
        "inferencesMade": [],
        "preservedLegacyFields": sorted(legacy_projection),
        "legacyProjection": legacy_projection,
        "generatorLineage": generator,
        "approvalEvidence": dict(approval),
    }
    return AssetMigrationResult(asset_v3, report, legacy_projection)


def write_migration_artifacts(
    legacy_asset_path: Path,
    source_manifest_path: Path,
    output_dir: Path,
    *,
    approval: Mapping[str, Any],
    asset_version: str,
    asset_role: str = SUPPORTED_ROLE,
) -> AssetMigrationResult:
    legacy_bytes = legacy_asset_path.read_bytes()
    legacy = json.loads(legacy_bytes)
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    result = migrate_asset(
        legacy,
        source_manifest=source_manifest,
        approval=approval,
        asset_version=asset_version,
        asset_role=asset_role,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = output_dir / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    legacy_copy = evidence_dir / "pre_migration_asset.sidecar.v3.0.json"
    if legacy_copy.exists():
        if legacy_copy.read_bytes() != legacy_bytes:
            raise AssetMigrationError("Existing read-only pre-migration evidence differs from the current legacy asset")
    else:
        legacy_copy.write_bytes(legacy_bytes)
        os.chmod(legacy_copy, 0o444)
    _write_bytes_atomic(output_dir / "asset.json", result.asset_bytes)
    _write_bytes_atomic(evidence_dir / "asset_migration_report.json", result.report_bytes)
    return result


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def canonical_legacy_projection(asset_v3: Mapping[str, Any], migration_report: Mapping[str, Any]) -> dict[str, Any]:
    _validate_v3(dict(asset_v3))
    projection = migration_report.get("legacyProjection")
    if not isinstance(projection, dict):
        raise AssetMigrationError("Migration report does not contain the preserved legacy projection")
    return dict(projection)


def _legacy_projection(legacy: Mapping[str, Any]) -> dict[str, Any]:
    preserved = (
        "schemaVersion",
        "integrationStatus",
        "assetId",
        "profileId",
        "profileScale",
        "normalization",
        "pivot",
        "collision",
        "animations",
        "anchors",
        "features",
        "sourceManifest",
        "generator",
    )
    return {name: legacy[name] for name in preserved if name in legacy}


def _required_string(document: Mapping[str, Any], name: str) -> str:
    value = document.get(name)
    if not isinstance(value, str) or not value:
        raise AssetMigrationError(f"Legacy field {name!r} is required and may not be inferred")
    return value


def _validate_approval(approval: Mapping[str, Any]) -> None:
    if approval.get("state") != "approved" or approval.get("approvedForDistribution") is not True:
        raise AssetMigrationError("Explicit approved distribution metadata is required before migration")
    if not isinstance(approval.get("eventId"), str) or not approval.get("eventId"):
        raise AssetMigrationError("Approval eventId is required")
    artifact = approval.get("artifactSha256")
    if not isinstance(artifact, str) or len(artifact) != 64:
        raise AssetMigrationError("Approval artifactSha256 is required")


def _validate_v3(document: dict[str, Any]) -> None:
    try:
        validate_document("asset_v3.schema.json", document)
    except ContractValidationError as exc:
        raise AssetMigrationError(str(exc)) from exc
