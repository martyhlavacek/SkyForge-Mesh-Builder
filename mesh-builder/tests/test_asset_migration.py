from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from app.asset_migration import (
    AssetMigrationError,
    canonical_legacy_projection,
    migrate_asset,
    write_migration_artifacts,
)


def legacy_asset(*, collision=None, anchors=None, role_missing=True):
    value = {
        "schemaVersion": "skyforge.asset.sidecar.v3.0",
        "integrationStatus": "pre-schema-sidecar",
        "assetId": "approved_gunship",
        "profileId": "enemy_gunship",
        "profileScale": 1.0,
        "normalization": {"targetCoordinates": {"forward": "+Y", "up": "+Z"}},
        "pivot": None,
        "collision": collision,
        "animations": {"bank": {"fps": 8}},
        "anchors": anchors,
        "features": {"thrusters": {"implemented": False}},
        "sourceManifest": "../manifest.json",
        "generator": {
            "generatorId": "skyforge.authority-two-sided-field",
            "provider": "SkyForge Authority Two-Sided Field",
            "providerVersion": "0.6.0",
        },
    }
    if not role_missing:
        value["assetRole"] = "air_moving"
    return value


def manifest():
    return {
        "mesh": {"origin": "generated_from_authority", "sha256": "1" * 64},
        "authority": {"sha256": "2" * 64},
    }


def approval():
    return {
        "eventId": "approval-1",
        "state": "approved",
        "approvedForDistribution": True,
        "artifactSha256": "3" * 64,
    }


def test_legacy_migration_is_explicit_and_idempotent():
    first = migrate_asset(
        legacy_asset(), source_manifest=manifest(), approval=approval(), asset_version="1.0.0"
    )
    assert first.asset_v3["assetId"] == "approved_gunship"
    assert first.asset_v3["craftProfileId"] == "enemy_gunship"
    assert first.asset_v3["assetRole"] == "air_moving"
    assert first.asset_v3["provider"] == {
        "id": "local_deterministic",
        "identityModel": "deterministic_reproducibility",
    }
    assert first.asset_v3["anchorState"] == "not_authored"
    assert "collisionHint" not in first.asset_v3
    second = migrate_asset(
        first.asset_v3, source_manifest=manifest(), approval=approval(), asset_version="1.0.0"
    )
    assert second.asset_bytes == first.asset_bytes
    assert second.report["migration"] == "validated_no_op"


def test_collision_ellipse_becomes_non_authoritative_hint():
    result = migrate_asset(
        legacy_asset(collision={"type": "ellipse", "radiusX": 1.0, "radiusY": 0.5}),
        source_manifest=manifest(),
        approval=approval(),
        asset_version="1.0.0",
    )
    assert result.asset_v3["collisionHint"]["authoritative"] is False
    assert result.asset_v3["collisionHint"]["consumerMustIgnoreForRuntime"] is True


@pytest.mark.parametrize("role", ["ground_moving", "ground_static"])
def test_unsupported_roles_fail(role: str):
    with pytest.raises(AssetMigrationError, match="Unsupported asset role"):
        migrate_asset(
            legacy_asset(), source_manifest=manifest(), approval=approval(), asset_version="1.0.0", asset_role=role
        )


def test_missing_or_contradictory_semantics_are_not_inferred():
    missing_profile = legacy_asset()
    missing_profile.pop("profileId")
    with pytest.raises(AssetMigrationError, match="may not be inferred"):
        migrate_asset(missing_profile, source_manifest=manifest(), approval=approval(), asset_version="1.0.0")
    contradictory = legacy_asset()
    contradictory["assetRole"] = "ground_static"
    with pytest.raises(AssetMigrationError, match="contradicts"):
        migrate_asset(contradictory, source_manifest=manifest(), approval=approval(), asset_version="1.0.0")
    missing_anchors = legacy_asset()
    missing_anchors.pop("anchors")
    with pytest.raises(AssetMigrationError, match="may not infer"):
        migrate_asset(missing_anchors, source_manifest=manifest(), approval=approval(), asset_version="1.0.0")


def test_nonlocal_lineage_and_unapproved_asset_fail_closed():
    external = legacy_asset()
    external["generator"]["generatorId"] = "external"
    with pytest.raises(AssetMigrationError, match="Provider identity"):
        migrate_asset(external, source_manifest=manifest(), approval=approval(), asset_version="1.0.0")
    denied = dict(approval(), approvedForDistribution=False)
    with pytest.raises(AssetMigrationError, match="approved distribution"):
        migrate_asset(legacy_asset(), source_manifest=manifest(), approval=denied, asset_version="1.0.0")


def test_round_trip_projection_preserves_every_declared_legacy_field():
    legacy = legacy_asset(collision={"type": "ellipse", "radiusX": 1.0, "radiusY": 0.5})
    result = migrate_asset(legacy, source_manifest=manifest(), approval=approval(), asset_version="1.0.0")
    assert canonical_legacy_projection(result.asset_v3, result.report) == legacy


def test_artifact_writer_preserves_read_only_byte_identical_legacy_copy(tmp_path: Path):
    legacy_path = tmp_path / "legacy.json"
    manifest_path = tmp_path / "manifest.json"
    original = json.dumps(legacy_asset(), indent=2).encode("utf-8")
    legacy_path.write_bytes(original)
    manifest_path.write_text(json.dumps(manifest()), encoding="utf-8")
    output = tmp_path / "migration"
    first = write_migration_artifacts(
        legacy_path, manifest_path, output, approval=approval(), asset_version="1.0.0"
    )
    assert (output / "evidence/pre_migration_asset.sidecar.v3.0.json").read_bytes() == original
    mode = stat.S_IMODE((output / "evidence/pre_migration_asset.sidecar.v3.0.json").stat().st_mode)
    assert mode == 0o444
    first_asset = (output / "asset.json").read_bytes()
    second = write_migration_artifacts(
        legacy_path, manifest_path, output, approval=approval(), asset_version="1.0.0"
    )
    assert second.asset_bytes == first.asset_bytes == first_asset
