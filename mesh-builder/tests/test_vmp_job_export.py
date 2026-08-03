from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

import pytest

from app import vmp_builder
from app.pipeline import JobPaths
from app.vmp_builder import build_vmp
from app.vmp_job_export import (
    JobVmpExportError,
    JobVmpExportRequest,
    _import_probe_environment,
    build_job_payload,
    resolve_import_probe_command,
    run_import_probe,
)
from common.glb_facts import GlbFactsError, parse_glb_facts
from common.mesh_math import canonical_frame_calibration


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fixture_job(tmp_path: Path, package_root: Path) -> tuple[JobPaths, dict, dict, dict]:
    job = JobPaths(tmp_path, tmp_path / "source", tmp_path / "output", tmp_path / "logs")
    for path in (job.source, job.output, job.logs):
        path.mkdir()
    authority_source = package_root / "samples/approved_gunship_authority.png"
    authority = job.source / authority_source.name
    shutil.copy2(authority_source, authority)
    generated = job.source / "generated"
    generated.mkdir()
    shutil.copy2(
        package_root / "docs/SELF_TEST_EVIDENCE_v0.6.0/approved_gunship/authority_mesh_generation_report.json",
        generated / "report.json",
    )
    shutil.copy2(package_root / "samples/v053_field_gunship_baseline.glb", job.output / "normalized.glb")
    for name in ("preview_neutral_96_lanczos.png", "silhouette_comparison.png"):
        shutil.copy2(authority_source, job.output / name)
    legacy_asset = {
        "schemaVersion": "skyforge.asset.sidecar.v3.0",
        "integrationStatus": "pre-schema-sidecar",
        "assetId": "approved_gunship",
        "profileId": "enemy_gunship",
        "profileScale": 1.0,
        "normalization": {},
        "pivot": None,
        "collision": {"type": "ellipse", "rx": 0.3, "ry": 0.2},
        "animations": {},
        "anchors": None,
        "features": {},
        "sourceManifest": "../manifest.json",
        "generator": {"generatorId": "skyforge.authority-two-sided-field"},
        "measurements": {"silhouetteIoU": {"value": 0.97}},
    }
    (job.output / "asset.json").write_text(json.dumps(legacy_asset), encoding="utf-8")
    run_report = {
        "neutralPoseRestoredBeforeExport": True,
        "meshMatricesIdentityAtExport": True,
        "cleanExportContainsReviewRig": False,
        "meshWorldBoundsPreservedDuringBake": True,
    }
    (job.output / "run_report.json").write_text(json.dumps(run_report), encoding="utf-8")
    profile_path = package_root / "profiles/craft_profiles.json"
    profiles = json.loads(profile_path.read_text(encoding="utf-8"))
    calibration = canonical_frame_calibration(
        max(float(item["scale"]) for item in profiles),
        len(profiles),
        hashlib.sha256(profile_path.read_bytes()).hexdigest(),
    )
    manifest = {
        "assetId": "approved_gunship",
        "profile": {"id": "enemy_gunship", "scale": 1.0},
        "experiment": {"id": "authority_mesh"},
        "authority": {"path": authority.name, "sha256": hashlib.sha256(authority.read_bytes()).hexdigest()},
        "mesh": {
            "origin": "generated_from_authority",
            "generatedFromAuthority": True,
            "generationReport": "generated/report.json",
        },
        "generator": {
            "generatorId": "skyforge.authority-two-sided-field",
            "approvedForDistribution": True,
        },
        "distributionGate": {"approved": True},
        "settings": {
            "bankDegrees": 18.0,
            "masterResolution": 384,
            "cameraPitchDegrees": 20.0,
            "forwardAxis": "+Y",
            "upAxis": "+Z",
            "renderSamples": 64,
            "canonicalFrameCalibration": calibration,
        },
    }
    (job.root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    status = {"status": "rendered", "updatedAt": "2026-08-01T12:00:00+00:00"}
    verification = {"requiredOutputCount": 26}
    return job, manifest, status, verification


def test_glb_facts_match_independent_probe_fixture():
    package_root = Path(__file__).resolve().parents[1]
    facts = parse_glb_facts((package_root / "samples/v053_field_gunship_baseline.glb").read_bytes())
    assert facts.vertex_count == 19720
    assert facts.triangle_count == 39460
    assert facts.mesh_count == 1
    assert facts.image_count == 1


def test_glb_facts_reject_external_or_invalid_data():
    with pytest.raises(GlbFactsError):
        parse_glb_facts(b"not-a-glb")


@pytest.mark.parametrize(
    ("permission", "embedded"),
    [("permitted", True), ("unknown", False), ("prohibited", False)],
)
def test_build_job_payload_is_schema_valid_deterministic_and_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, permission: str, embedded: bool
):
    package_root = Path(__file__).resolve().parents[1]
    job, manifest, status, verification = _fixture_job(tmp_path, package_root)
    monkeypatch.setattr(vmp_builder, "canonicalize", _canonical)
    request = JobVmpExportRequest("1.0.0", permission, "explicit test assertion", True)
    payload, metadata = build_job_payload(package_root, job, manifest, status, verification, request)
    repeated_payload, repeated_metadata = build_job_payload(
        package_root, job, manifest, status, verification, request
    )
    assert repeated_payload == payload
    assert repeated_metadata == metadata
    first = build_vmp(payload, metadata, tmp_path / "first.sfmeshpack")
    second = build_vmp(payload, metadata, tmp_path / "second.sfmeshpack")
    assert first.package_content_digest == second.package_content_digest
    assert first.archive_sha256 == second.archive_sha256
    assert first.archive_path.read_bytes() == second.archive_path.read_bytes()
    authority = json.loads(payload["authorities/authority_manifest.json"])
    assert authority["authorities"][0]["embedded"] is embedded
    assert ("authorities/silhouette_authority.png" in payload) is embedded
    asset = json.loads(payload["asset.json"])
    assert asset["assetRole"] == "air_moving"
    assert asset["collisionHint"] == {
        "authoritative": False,
        "consumerMustIgnoreForRuntime": True,
        "sourceSchema": "skyforge.asset.sidecar.v3.0",
        "description": "Legacy sidecar collision ellipse; informational only.",
    }
    legacy_evidence = job.root / "vmp_staging/evidence/pre_migration_asset.sidecar.v3.0.json"
    assert legacy_evidence.read_bytes() == (job.output / "asset.json").read_bytes()
    assert legacy_evidence.stat().st_mode & 0o222 == 0


def test_job_payload_rejects_provider_job_unapproved_job_and_changed_frame(tmp_path: Path):
    package_root = Path(__file__).resolve().parents[1]
    job, manifest, status, verification = _fixture_job(tmp_path, package_root)
    request = JobVmpExportRequest("1.0.0", "unknown", "explicit test assertion", True)
    manifest["experiment"]["id"] = "provider_mesh"
    with pytest.raises(JobVmpExportError, match="Only local Authority Mesh"):
        build_job_payload(package_root, job, manifest, status, verification, request)
    manifest["experiment"]["id"] = "authority_mesh"
    manifest["distributionGate"]["approved"] = False
    with pytest.raises(JobVmpExportError, match="distribution approval"):
        build_job_payload(package_root, job, manifest, status, verification, request)
    manifest["distributionGate"]["approved"] = True
    manifest["settings"]["masterResolution"] = 512
    with pytest.raises(JobVmpExportError, match="masterResolution=384"):
        build_job_payload(package_root, job, manifest, status, verification, request)


def test_job_payload_rejects_low_blender_iou_and_non_png_authority(tmp_path: Path):
    package_root = Path(__file__).resolve().parents[1]
    job, manifest, status, verification = _fixture_job(tmp_path, package_root)
    request = JobVmpExportRequest("1.0.0", "unknown", "explicit test assertion", True)
    asset = json.loads((job.output / "asset.json").read_text(encoding="utf-8"))
    asset["measurements"]["silhouetteIoU"]["value"] = 0.9399
    (job.output / "asset.json").write_text(json.dumps(asset), encoding="utf-8")
    with pytest.raises(JobVmpExportError, match="below the frozen 0.94 floor"):
        build_job_payload(package_root, job, manifest, status, verification, request)
    asset["measurements"]["silhouetteIoU"]["value"] = 0.97
    (job.output / "asset.json").write_text(json.dumps(asset), encoding="utf-8")
    authority = job.source / manifest["authority"]["path"]
    jpeg = authority.with_suffix(".jpg")
    jpeg.write_bytes(authority.read_bytes())
    manifest["authority"]["path"] = jpeg.name
    with pytest.raises(JobVmpExportError, match="requires the approved authority to be PNG"):
        build_job_payload(package_root, job, manifest, status, verification, request)


def _fixture_probe_venv(tmp_path: Path) -> tuple[Path, Path]:
    environment_root = tmp_path / "probe_clean_env"
    interpreter = environment_root / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(sys.executable)
    (environment_root / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    site_packages = environment_root / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    site_packages.mkdir(parents=True)
    return interpreter, site_packages


def test_import_probe_environment_is_minimal_and_pins_exact_probe_venv(tmp_path: Path):
    interpreter, site_packages = _fixture_probe_venv(tmp_path)
    environment = _import_probe_environment([str(interpreter), "probe.py"], platform_name="darwin")
    assert environment == {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(site_packages.absolute()),
        "__PYVENV_LAUNCHER__": str(interpreter.absolute()),
    }
    assert environment["PYTHONPATH"] != os.environ.get("PYTHONPATH")
    assert "VIRTUAL_ENV" not in environment


def test_import_probe_environment_omits_macos_launcher_off_darwin(tmp_path: Path):
    interpreter, site_packages = _fixture_probe_venv(tmp_path)
    environment = _import_probe_environment([str(interpreter), "probe.py"], platform_name="linux")
    assert "__PYVENV_LAUNCHER__" not in environment
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["PYTHONPATH"] == str(site_packages.absolute())


def test_import_probe_resolution_preserves_virtual_environment_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    probe_root = tmp_path / "probe"
    (probe_root / "scripts").mkdir(parents=True)
    (probe_root / "scripts/run_import_probe.py").write_text("pass\n", encoding="utf-8")
    (probe_root / "IMPORT_PROBE_SOURCE_BINDING.json").write_text("{}\n", encoding="utf-8")
    interpreter, _site_packages = _fixture_probe_venv(tmp_path)
    monkeypatch.setenv("SKYFORGE_IMPORT_PROBE_ROOT", str(probe_root))
    monkeypatch.setenv("SKYFORGE_IMPORT_PROBE_PYTHON", str(interpreter))
    command = resolve_import_probe_command(tmp_path)
    assert command is not None
    assert command[0] == str(interpreter.absolute())
    assert Path(command[0]).is_symlink()


def test_minimal_probe_environment_can_import_exact_venv_site_packages(tmp_path: Path):
    environment_root = tmp_path / "real_probe_clean_env"
    venv.EnvBuilder(with_pip=False).create(environment_root)
    interpreter = environment_root / "bin" / "python"
    site_packages = next((environment_root / "lib").glob("python*/site-packages"))
    (site_packages / "skyforge_probe_marker.py").write_text("VALUE = 47\n", encoding="utf-8")
    completed = subprocess.run(
        [
            str(interpreter),
            "-c",
            "import skyforge_probe_marker; print(skyforge_probe_marker.VALUE)",
        ],
        text=True,
        capture_output=True,
        check=False,
        env=_import_probe_environment([str(interpreter), "probe.py"]),
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "47"


def test_import_probe_subprocess_contract(tmp_path: Path):
    package = tmp_path / "fixture.sfmeshpack"
    package.write_bytes(b"package")
    receipt = tmp_path / "receipt.json"
    helper = tmp_path / "probe.py"
    helper.write_text(
        "import argparse,hashlib,json\n"
        "p=argparse.ArgumentParser();p.add_argument('archive');p.add_argument('--receipt');a=p.parse_args()\n"
        "raw=open(a.archive,'rb').read();d='a'*64\n"
        "r={'schemaVersion':'skyforge.sprite-foundry-import-receipt.v1','accepted':True,"
        "'sourcePackageContentDigest':d,'sourceArchiveSha256':hashlib.sha256(raw).hexdigest()}\n"
        "open(a.receipt,'w').write(json.dumps(r))\n",
        encoding="utf-8",
    )
    result = run_import_probe([sys.executable, str(helper)], package, receipt)
    assert result["accepted"] is True
    assert result["sourceArchiveSha256"] == hashlib.sha256(b"package").hexdigest()
