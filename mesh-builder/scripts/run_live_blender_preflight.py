from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from app.authority_mesh import (  # noqa: E402
    GENERATOR_ID,
    GENERATOR_VERSION,
    generate_authority_mesh,
)
from app.authority_validation import require_authority_suitability  # noqa: E402
from app.pipeline import (  # noqa: E402
    create_job,
    load_profiles,
    package_job,
    read_job_status,
    resolve_blender_path,
    run_job,
    sha256_file,
    write_job_status,
    write_manifest,
)
from app.providers import ProviderRequest, resolve_provider  # noqa: E402
from app.vmp_job_export import (  # noqa: E402
    JobVmpExportRequest,
    export_rendered_job_vmp,
    resolve_import_probe_command,
)
from common.mesh_equivalence import compare_mesh_semantics  # noqa: E402
from common.mesh_math import canonical_frame_calibration  # noqa: E402
from common.source_binding import PRODUCER_SCOPE, SourceBindingError, verify_binding  # noqa: E402

FIXTURES = (
    ("approved_gunship", "approved_gunship_authority.png", "enemy_gunship"),
    ("field_gunship", "v060_field_gunship_authority.png", "enemy_gunship"),
    ("interceptor", "interceptor_openai_authority_regression.png", "enemy_interceptor"),
)
EXPECTED_MESH_SHA256 = {
    "approved_gunship": "2e2f5f68dfa91ac2611113c35b1b08d90dfdecc2d593f897d40963dd46a2705a",
    "field_gunship": "f4761acd9a1f7c78c4bedc3b9616b162e4a57c2d47a756eb29ad0446952d0e91",
    "interceptor": "97617de238dc451d4ca374e1c0b05461ab71e18cfd82643e0dd2358bf1a8f118",
}
EXPECTED_AUTHORITY_SHA256 = {
    "approved_gunship": "d33075df367c97399b7ed6262030ca8ca0080eda12ebe78eb3eb3fc901f7fc1e",
    "field_gunship": "81deecf91afdc833cdffdc10cba95706afe22484621ba575edb46583bddc5f08",
    "interceptor": "8eb3b788bb2932f3aafdf7051a41c668eec77bb655a84340c45213de378a782f",
}
BLENDER_SILHOUETTE_IOU_MIN = 0.94
EXPECTED_LIVE_BLENDER_IOU = {
    "approved_gunship": 0.975865,
    "field_gunship": 0.947415,
    "interceptor": 0.952496,
}
LIVE_BASELINE_TOLERANCE = 1e-6


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source_binding(package_root: Path) -> dict[str, object]:
    try:
        return verify_binding(package_root, PRODUCER_SCOPE)
    except SourceBindingError as exc:
        raise RuntimeError(str(exc)) from exc


def _write_deterministic_zip(source: Path, destination: Path) -> None:
    timestamp = (2026, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            info = zipfile.ZipInfo(path.relative_to(source).as_posix(), timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def _probe_command(
    package_root: Path, probe_root: Path | None, probe_python: Path | None
) -> tuple[str, ...]:
    if probe_root is not None or probe_python is not None:
        if probe_root is None or probe_python is None:
            raise RuntimeError("--probe-root and --probe-python must be supplied together")
        script = probe_root.resolve() / "scripts/run_import_probe.py"
        binding = probe_root.resolve() / "IMPORT_PROBE_SOURCE_BINDING.json"
        interpreter = Path(os.path.abspath(os.fspath(probe_python.expanduser())))
        if not interpreter.is_file() or not script.is_file() or not binding.is_file():
            raise RuntimeError("Independent Import Probe environment is incomplete")
        return (str(interpreter), str(script))
    command = resolve_import_probe_command(package_root)
    if command is None:
        raise RuntimeError("Independent Import Probe environment is not configured")
    return command


def run(
    package_root: Path,
    output_zip: Path,
    *,
    probe_root: Path | None = None,
    probe_python: Path | None = None,
) -> dict[str, object]:
    source_binding = verify_source_binding(package_root)
    command = _probe_command(package_root, probe_root, probe_python)
    blender = resolve_blender_path(package_root)
    if blender is None:
        raise RuntimeError("Blender is not configured or could not be found")
    profiles = load_profiles(package_root)
    profile_by_id = {item["id"]: item for item in profiles}
    maximum_scale = max(float(item["scale"]) for item in profiles)
    profile_path = package_root / "profiles/craft_profiles.json"
    frame = canonical_frame_calibration(maximum_scale, len(profiles), sha256_file(profile_path))
    provider = resolve_provider("local_deterministic")

    with tempfile.TemporaryDirectory(prefix="skyforge-v071-live-blender-") as temporary:
        temp_root = Path(temporary)
        workspace = temp_root / "workspace"
        archives = temp_root / "archives"
        vmp_dir = temp_root / "vmp"
        evidence = temp_root / "evidence"
        evidence.mkdir(parents=True)
        vmp_dir.mkdir(parents=True)
        results: list[dict[str, object]] = []

        for label, filename, profile_id in FIXTURES:
            profile = profile_by_id[profile_id]
            authority_source = package_root / "samples" / filename
            job = create_job(workspace, profile, f"preflight.{label}")
            authority = job.source / filename
            shutil.copy2(authority_source, authority)
            authority_suitability = require_authority_suitability(
                authority,
                source_kind="cleared_fixture",
                lineage={
                    "fixture": label,
                    "profileId": profile_id,
                    "expectedAuthoritySha256": EXPECTED_AUTHORITY_SHA256[label],
                },
            )
            authority_suitability_path = job.source / "authority_suitability_report.json"
            authority_suitability_path.write_text(
                json.dumps(authority_suitability, indent=2) + "\n", encoding="utf-8"
            )
            legacy_dir = job.source / "legacy_direct"
            legacy = generate_authority_mesh(authority, legacy_dir)
            capture = provider.execute(
                ProviderRequest(
                    request_id=job.root.name,
                    operation="authority_to_mesh",
                    asset_id=f"preflight.{label}",
                    asset_role="air_moving",
                    authority_path=authority,
                    output_dir=job.source / "generated",
                )
            )
            for item in (*capture.preview_paths, capture.report_path):
                shutil.copy2(item, job.output / item.name)
            shutil.copy2(job.source / "generated/provider_events.jsonl", job.logs / "provider_events.jsonl")
            settings = {
                "bankDegrees": 18.0,
                "masterResolution": 384,
                "cameraPitchDegrees": 20.0,
                "forwardAxis": "+Y",
                "upAxis": "+Z",
                "profileScale": float(profile["scale"]),
                "canonicalOrthoScale": frame["canonicalOrthoScale"],
                "canonicalFrameCalibration": frame,
                "renderSamples": 64,
                "destruction": {
                    "requested": False,
                    "implemented": False,
                    "reason": "Not part of the deterministic geometry preflight.",
                },
            }
            generator = {
                "provider": "SkyForge Authority Two-Sided Field",
                "providerVersion": GENERATOR_VERSION,
                "generatorId": GENERATOR_ID,
                "license": "Project SkyForge internal deterministic generator",
                "licenseUrl": None,
                "retrievedDate": "2026-08-01",
                "approvedForDistribution": True,
            }
            manifest = write_manifest(
                job,
                profile,
                f"preflight.{label}",
                authority,
                capture.mesh_path,
                "generated_from_authority",
                capture.report_path,
                "authority_mesh",
                "Authority Mesh — local deterministic generation",
                settings,
                generator,
                authority_suitability_path,
            )
            write_job_status(job, "prepared", manifest="manifest.json", experiment="authority_mesh")
            run_job(package_root, job, manifest, blender)
            status = read_job_status(job)
            if status.get("status") != "rendered":
                raise RuntimeError(f"Live Blender preflight failed for {label}: {status.get('error')}")
            review_zip = package_job(job, archives)
            shutil.copy2(review_zip, evidence / f"{label}_review_package.zip")

            full_request = JobVmpExportRequest(
                asset_version="1.0.0",
                authority_redistribution_permission="permitted",
                authority_terms_basis="Project SkyForge cleared fixture authority; review evidence only",
                asset_commercial_use_asserted=True,
            )
            first = export_rendered_job_vmp(
                package_root,
                job,
                full_request,
                vmp_dir / f"{label}_build_a.sfmeshpack",
                import_probe_command=command,
            )
            second = export_rendered_job_vmp(
                package_root,
                job,
                full_request,
                vmp_dir / f"{label}_build_b.sfmeshpack",
                import_probe_command=command,
            )
            if first.build.archive_path.read_bytes() != second.build.archive_path.read_bytes():
                raise RuntimeError(f"Deterministic VMP rebuild mismatch for {label}")
            shutil.copy2(first.build.archive_path, evidence / f"{label}.sfmeshpack")
            shutil.copy2(first.receipt_path, evidence / f"{label}_IMPORT_RECEIPT.json")

            hash_only: dict[str, object] | None = None
            if label == "approved_gunship":
                hash_result = export_rendered_job_vmp(
                    package_root,
                    job,
                    JobVmpExportRequest(
                        asset_version="1.0.0",
                        authority_redistribution_permission="unknown",
                        authority_terms_basis="Redistribution permission intentionally unknown for hash-only vector",
                        asset_commercial_use_asserted=True,
                    ),
                    vmp_dir / "approved_gunship_hash_only.sfmeshpack",
                    import_probe_command=command,
                )
                shutil.copy2(hash_result.build.archive_path, evidence / "approved_gunship_hash_only.sfmeshpack")
                shutil.copy2(hash_result.receipt_path, evidence / "approved_gunship_hash_only_IMPORT_RECEIPT.json")
                hash_only = {
                    "packageContentDigest": hash_result.build.package_content_digest,
                    "archiveSha256": hash_result.build.archive_sha256,
                    "authorityReverification": hash_result.receipt.get("authorityReverification"),
                }

            generation = json.loads(capture.report_path.read_text(encoding="utf-8"))
            semantic = compare_mesh_semantics(
                legacy.mesh_path,
                capture.mesh_path,
                legacy.report_path,
                capture.report_path,
            )
            asset = json.loads((job.output / "asset.json").read_text(encoding="utf-8"))
            run_report = json.loads((job.output / "run_report.json").read_text(encoding="utf-8"))
            generated_mesh_sha256 = generation["mesh"]["sha256"]
            expected_mesh_sha256 = EXPECTED_MESH_SHA256[label]
            provider_events = [
                json.loads(line)
                for line in (job.logs / "provider_events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            measured_blender_iou = float(asset["measurements"]["silhouetteIoU"]["value"])
            expected_blender_iou = EXPECTED_LIVE_BLENDER_IOU[label]
            live_baseline_matches = abs(measured_blender_iou - expected_blender_iou) <= LIVE_BASELINE_TOLERANCE
            results.append(
                {
                    "fixture": label,
                    "profileId": profile_id,
                    "profileScale": float(profile["scale"]),
                    "authoritySuitability": authority_suitability,
                    "authoritySha256": _sha256(authority_source),
                    "expectedAuthoritySha256": EXPECTED_AUTHORITY_SHA256[label],
                    "authorityHashMatchesClearedFixture": _sha256(authority_source) == EXPECTED_AUTHORITY_SHA256[label],
                    "legacyDirectMeshSha256": _sha256(legacy.mesh_path),
                    "generatedMeshSha256": generated_mesh_sha256,
                    "reviewedCandidateMeshSha256": expected_mesh_sha256,
                    "adapterTransportHashMatchesLegacy": generated_mesh_sha256 == _sha256(legacy.mesh_path),
                    "reviewedCandidateTransportHashMatch": generated_mesh_sha256 == expected_mesh_sha256,
                    "semanticComparison": semantic,
                    "providerId": capture.task.provider_id,
                    "providerModel": capture.task.provider_model,
                    "providerEvents": provider_events,
                    "providerCostZero": all(event["consumedCost"] == "0" for event in provider_events),
                    "generatorGatesPassed": generation["gateResults"]["passed"],
                    "blenderSilhouetteIoU": measured_blender_iou,
                    "expectedForwardBaselineIoU": expected_blender_iou,
                    "forwardBaselineTolerance": LIVE_BASELINE_TOLERANCE,
                    "forwardBaselineMatches": live_baseline_matches,
                    "neutralPoseRestoredBeforeExport": run_report["neutralPoseRestoredBeforeExport"],
                    "meshMatricesIdentityAtExport": run_report["meshMatricesIdentityAtExport"],
                    "reviewPackage": f"{label}_review_package.zip",
                    "reviewPackageSha256": _sha256(review_zip),
                    "vmp": {
                        "packageContentDigest": first.build.package_content_digest,
                        "archiveSha256": first.build.archive_sha256,
                        "deterministicRebuildByteIdentical": True,
                        "probeAccepted": first.receipt.get("accepted") is True,
                        "receiptId": first.receipt.get("receiptId"),
                        "authorityReverification": first.receipt.get("authorityReverification"),
                    },
                    "hashOnlyVector": hash_only,
                }
            )

        summary = {
            "schemaVersion": "skyforge.v071-live-blender-preflight.v3",
            "sidecarVersion": "0.7.1",
            "generatorVersion": GENERATOR_VERSION,
            "blenderExecutableName": blender.name,
            "executedAt": datetime.now(timezone.utc).isoformat(),
            "blenderSilhouetteIoUMin": BLENDER_SILHOUETTE_IOU_MIN,
            "authoritySuitabilityRequired": True,
            "profileBaselineDisclosure": "docs/v0.7.1/MBS-144_INTERCEPTOR_PROFILE_BASELINE.md",
            "outputEquivalenceBinding": "same-environment legacy-direct semantic comparison",
            "exactProducerSourceBinding": source_binding,
            "independentProbeCommand": [Path(command[0]).name, Path(command[1]).name],
            "fixtures": results,
            "passed": all(
                bool(item["generatorGatesPassed"])
                and bool(item["authorityHashMatchesClearedFixture"])
                and bool(item["authoritySuitability"]["passed"])
                and bool(item["forwardBaselineMatches"])
                and bool(item["adapterTransportHashMatchesLegacy"])
                and bool(item["semanticComparison"]["passed"])
                and bool(item["providerCostZero"])
                and float(item["blenderSilhouetteIoU"]) >= BLENDER_SILHOUETTE_IOU_MIN
                and bool(item["neutralPoseRestoredBeforeExport"])
                and bool(item["meshMatricesIdentityAtExport"])
                and bool(item["vmp"]["deterministicRebuildByteIdentical"])
                and bool(item["vmp"]["probeAccepted"])
                for item in results
            ),
        }
        (evidence / "LIVE_BLENDER_PREFLIGHT.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        _write_deterministic_zip(evidence, output_zip)
        output_zip.with_suffix(output_zip.suffix + ".sha256").write_text(
            f"{_sha256(output_zip)}  {output_zip.name}\n", encoding="utf-8"
        )
        return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--probe-root", type=Path)
    parser.add_argument("--probe-python", type=Path)
    args = parser.parse_args()
    output = args.output or (PACKAGE_ROOT.parent / "SkyForge_v0.7.1_LIVE_BLENDER_PREFLIGHT.zip")
    summary = run(
        PACKAGE_ROOT,
        output.resolve(),
        probe_root=args.probe_root,
        probe_python=args.probe_python,
    )
    print(json.dumps(summary, indent=2))
    print(f"Wrote {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
