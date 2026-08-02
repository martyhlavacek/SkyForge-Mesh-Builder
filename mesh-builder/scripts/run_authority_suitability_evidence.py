#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from PIL import Image

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from app import server as server_module  # noqa: E402
from app.authority_validation import analyze_authority_suitability  # noqa: E402

VALID_FIXTURES = (
    "approved_gunship_authority.png",
    "v060_field_gunship_authority.png",
    "interceptor_openai_authority_regression.png",
    "user_test_gunship_authority.png",
)
REJECTED_FIXTURE = "rejected_three_quarter_beauty_mbs155.png"
REJECTED_FIXTURE_SHA256 = "6a82feefadddce2f09ea318534b3c8d913470164d5ca6f784cb05d4972b50208"
V070_DEFECT_REVIEW_PACKAGE_SHA256 = "cdfaf1c1c06ee1e54c7ede9d6d9869ed498c36e3088ae7876ed8ab82e52a5391"
V070_EMBEDDED_AUTHORITY_SHA256 = "9bba31bc544b6dd84d566d0c6b27b4b8fdc1a3d39f287665c5a8fc9e8f143e9e"
REJECTED_FIXTURE_DECODED_RGBA_SHA256 = "4053c4b9322114b10a998f2f5ccaee50a7afd63f6107ce78177fa3a2ad7347f1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decoded_rgba_sha256(data: bytes) -> str:
    with Image.open(io.BytesIO(data)) as image:
        rgba = image.convert("RGBA")
        digest = hashlib.sha256()
        digest.update(rgba.width.to_bytes(4, "big"))
        digest.update(rgba.height.to_bytes(4, "big"))
        digest.update(rgba.tobytes())
        return digest.hexdigest()


def _exercise_pre_job_boundary(rejected_path: Path) -> dict[str, Any]:
    calls = {
        "createJob": 0,
        "resolveProvider": 0,
        "resolveBlender": 0,
        "startJobThread": 0,
        "governedApiRequest": 0,
    }
    originals: dict[str, Callable[..., Any]] = {}

    def forbid(name: str):
        def blocked(*_args: Any, **_kwargs: Any):
            calls[name] += 1
            raise AssertionError(f"MBS-155 invalid authority crossed boundary: {name}")

        return blocked

    replacements = {
        "create_job": forbid("createJob"),
        "resolve_provider": forbid("resolveProvider"),
        "resolve_blender_path": forbid("resolveBlender"),
        "start_job_thread": forbid("startJobThread"),
        "execute_governed_request": forbid("governedApiRequest"),
    }
    for attribute, replacement in replacements.items():
        originals[attribute] = getattr(server_module, attribute)
        setattr(server_module, attribute, replacement)

    try:
        with tempfile.TemporaryDirectory(prefix="skyforge-mbs155-boundary-") as temporary:
            workspace = Path(temporary) / "workspace"
            app = server_module.create_app(PACKAGE_ROOT, workspace)
            client = app.test_client()
            with client.session_transaction() as session:
                session["csrf_token"] = "mbs155-evidence-token"
            response = client.post(
                "/api/jobs",
                data={
                    "experiment": "authority_mesh",
                    "profileId": "enemy_gunship",
                    "assetId": "mbs155.rejected.beauty",
                    "authority": (io.BytesIO(rejected_path.read_bytes()), rejected_path.name),
                    "manualAuthorityCertified": "on",
                    "bankDegrees": "18",
                    "masterResolution": "384",
                    "cameraPitchDegrees": "20",
                    "forwardAxis": "+Y",
                    "upAxis": "+Z",
                },
                headers={"X-SkyForge-CSRF": "mbs155-evidence-token"},
                content_type="multipart/form-data",
            )
            payload = response.get_json(silent=True) or {}
            job_directories = sorted(
                path.name
                for path in workspace.iterdir()
                if path.is_dir() and not path.name.startswith("_")
            )
    finally:
        for attribute, original in originals.items():
            setattr(server_module, attribute, original)

    report = payload.get("authoritySuitability") or {}
    return {
        "endpoint": "/api/jobs",
        "responseStatus": response.status_code,
        "responseOk": payload.get("ok"),
        "reportedSuitabilityPassed": report.get("passed"),
        "reportedFailureCodes": sorted(
            item.get("code") for item in report.get("failures", []) if isinstance(item, dict)
        ),
        "jobDirectoriesCreated": job_directories,
        "callCounts": calls,
        "passed": (
            response.status_code == 422
            and payload.get("ok") is False
            and report.get("passed") is False
            and not job_directories
            and not any(calls.values())
        ),
    }


def _inspect_v070_defect_artifact(path: Path, rejected_fixture: Path) -> dict[str, Any]:
    if not path.is_file() or sha256(path) != V070_DEFECT_REVIEW_PACKAGE_SHA256:
        raise RuntimeError("The exact v0.7.0 MBS-155 field-defect review package changed")
    rejected_bytes = rejected_fixture.read_bytes()
    rejected_raw_sha = hashlib.sha256(rejected_bytes).hexdigest()
    rejected_decoded_sha = decoded_rgba_sha256(rejected_bytes)
    if (
        rejected_raw_sha != REJECTED_FIXTURE_SHA256
        or rejected_decoded_sha != REJECTED_FIXTURE_DECODED_RGBA_SHA256
    ):
        raise RuntimeError("The exact MBS-155 rejected fixture changed")
    with zipfile.ZipFile(path) as archive:
        required = {
            "source/01_primary_authoritative.png",
            "manifest.json",
            "job.json",
            "output/asset.json",
        }
        if not required <= set(archive.namelist()):
            raise RuntimeError("The v0.7.0 MBS-155 field-defect package is incomplete")
        authority_bytes = archive.read("source/01_primary_authoritative.png")
        manifest = json.loads(archive.read("manifest.json"))
        job = json.loads(archive.read("job.json"))
        asset = json.loads(archive.read("output/asset.json"))
    authority_sha = hashlib.sha256(authority_bytes).hexdigest()
    authority_decoded_sha = decoded_rgba_sha256(authority_bytes)
    measured_iou = float(asset["measurements"]["silhouetteIoU"]["value"] or 0)
    pixels_match = authority_decoded_sha == rejected_decoded_sha
    passed = (
        authority_sha == V070_EMBEDDED_AUTHORITY_SHA256
        and authority_decoded_sha == REJECTED_FIXTURE_DECODED_RGBA_SHA256
        and pixels_match
        and manifest.get("authority", {}).get("sha256") == authority_sha
        and manifest.get("authority", {}).get("role") == "approved_top_down_authority"
        and job.get("status") == "rendered"
        and measured_iou >= 0.94
    )
    return {
        "finding": "MBS-155",
        "archiveFilename": path.name,
        "archiveSha256": sha256(path),
        "rejectedFixtureSha256": rejected_raw_sha,
        "rejectedFixtureDecodedRgbaSha256": rejected_decoded_sha,
        "embeddedAuthoritySha256": authority_sha,
        "embeddedAuthorityDecodedRgbaSha256": authority_decoded_sha,
        "embeddedAuthorityPixelsMatchRejectedFixture": pixels_match,
        "v070DeclaredAuthorityRole": manifest.get("authority", {}).get("role"),
        "v070JobStatus": job.get("status"),
        "v070BlenderSilhouetteIoU": measured_iou,
        "demonstratesDownstreamGatesCouldNotEstablishCameraSuitability": passed,
        "passed": passed,
    }


def run(output: Path, v070_defect_review_package: Path) -> dict[str, object]:
    accepted = []
    for filename in VALID_FIXTURES:
        path = PACKAGE_ROOT / "samples" / filename
        report = analyze_authority_suitability(path, source_kind="cleared_fixture")
        accepted.append({"filename": filename, "sha256": sha256(path), "report": report})
    rejected_path = PACKAGE_ROOT / "samples" / REJECTED_FIXTURE
    rejected_sha = sha256(rejected_path)
    if rejected_sha != REJECTED_FIXTURE_SHA256:
        raise RuntimeError("The exact MBS-155 field-defect fixture changed")
    rejected_report = analyze_authority_suitability(rejected_path, source_kind="fixture")
    failure_codes = {item["code"] for item in rejected_report["failures"]}
    required_codes = {"perspective_or_asymmetric_planform", "unstable_centerline", "not_nose_up"}
    execution_boundary = _exercise_pre_job_boundary(rejected_path)
    prior_defect_artifact = _inspect_v070_defect_artifact(
        v070_defect_review_package, rejected_path
    )
    payload = {
        "schemaVersion": "skyforge.authority-suitability-evidence.v2",
        "sidecarVersion": "0.7.1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "acceptedFixtures": accepted,
        "rejectedFieldDefect": {
            "finding": "MBS-155",
            "filename": REJECTED_FIXTURE,
            "sha256": rejected_sha,
            "report": rejected_report,
            "requiredFailureCodes": sorted(required_codes),
        },
        "priorDefectArtifact": prior_defect_artifact,
        "executionBoundary": execution_boundary,
        "passed": (
            all(item["report"]["passed"] is True for item in accepted)
            and rejected_report["passed"] is False
            and required_codes <= failure_codes
            and prior_defect_artifact["passed"] is True
            and execution_boundary["passed"] is True
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if not payload["passed"]:
        raise RuntimeError("Authority-suitability evidence did not reproduce the cleared/rejected fixtures")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--v070-defect-review-package", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.output.resolve(), args.v070_defect_review_package.resolve()),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
