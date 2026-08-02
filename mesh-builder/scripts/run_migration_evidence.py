#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from app.asset_migration import canonical_legacy_projection, write_migration_artifacts  # noqa: E402


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def run(output_dir: Path) -> Path:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    legacy = {
        "schemaVersion": "skyforge.asset.sidecar.v3.0",
        "integrationStatus": "pre-schema-sidecar",
        "assetId": "approved_gunship",
        "profileId": "enemy_gunship",
        "profileScale": 1.0,
        "normalization": {"targetCoordinates": {"forward": "+Y", "up": "+Z"}},
        "pivot": None,
        "collision": {"type": "ellipse", "radiusX": 1.0, "radiusY": 0.5},
        "animations": {"bank": {"fps": 8}},
        "anchors": None,
        "features": {"thrusters": {"implemented": False}},
        "sourceManifest": "../manifest.json",
        "generator": {
            "generatorId": "skyforge.authority-two-sided-field",
            "provider": "SkyForge Authority Two-Sided Field",
            "providerVersion": "0.6.0",
        },
    }
    source_manifest = {
        "mesh": {"origin": "generated_from_authority", "sha256": "1" * 64},
        "authority": {"sha256": "2" * 64},
    }
    approval = {
        "eventId": "migration-evidence-approval",
        "state": "approved",
        "approvedForDistribution": True,
        "artifactSha256": "3" * 64,
    }
    legacy_path = output_dir / "legacy_asset.sidecar.v3.0.json"
    manifest_path = output_dir / "source_manifest.json"
    legacy_bytes = (json.dumps(legacy, indent=2) + "\n").encode("utf-8")
    legacy_path.write_bytes(legacy_bytes)
    manifest_path.write_text(json.dumps(source_manifest, indent=2) + "\n", encoding="utf-8")
    migrated_dir = output_dir / "migrated"
    first = write_migration_artifacts(
        legacy_path,
        manifest_path,
        migrated_dir,
        approval=approval,
        asset_version="1.0.0",
    )
    first_asset = (migrated_dir / "asset.json").read_bytes()
    second = write_migration_artifacts(
        legacy_path,
        manifest_path,
        migrated_dir,
        approval=approval,
        asset_version="1.0.0",
    )
    copy = migrated_dir / "evidence/pre_migration_asset.sidecar.v3.0.json"
    report = {
        "schemaVersion": "skyforge.asset-v3-migration-evidence.v1",
        "sourceSchema": legacy["schemaVersion"],
        "targetSchema": first.asset_v3["schemaVersion"],
        "sourceBytesSha256": sha256_bytes(legacy_bytes),
        "readOnlyEvidenceSha256": sha256_bytes(copy.read_bytes()),
        "sourceEvidenceByteIdentical": copy.read_bytes() == legacy_bytes,
        "sourceEvidenceMode": oct(stat.S_IMODE(copy.stat().st_mode)),
        "assetRole": first.asset_v3["assetRole"],
        "providerId": first.asset_v3["provider"]["id"],
        "collisionHintAuthoritative": first.asset_v3["collisionHint"]["authoritative"],
        "collisionHintConsumerMustIgnoreForRuntime": first.asset_v3["collisionHint"][
            "consumerMustIgnoreForRuntime"
        ],
        "inferencesMade": first.report["inferencesMade"],
        "roundTripProjectionMatches": canonical_legacy_projection(first.asset_v3, first.report) == legacy,
        "idempotentAssetBytes": second.asset_bytes == first.asset_bytes == first_asset,
        "passed": (
            copy.read_bytes() == legacy_bytes
            and stat.S_IMODE(copy.stat().st_mode) == 0o444
            and first.asset_v3["assetRole"] == "air_moving"
            and first.asset_v3["provider"]["id"] == "local_deterministic"
            and first.asset_v3["collisionHint"]["authoritative"] is False
            and first.report["inferencesMade"] == []
            and canonical_legacy_projection(first.asset_v3, first.report) == legacy
            and second.asset_bytes == first.asset_bytes == first_asset
        ),
    }
    target = output_dir / "migration_report.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not report["passed"]:
        raise RuntimeError("Asset-v3 migration evidence failed")
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    print(run(args.output_dir.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
