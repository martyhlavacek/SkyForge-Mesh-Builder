from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts import assemble_claude_candidate as candidate


def write_zip(path: Path, root: str, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(f"{root}/{name}", data)
    return path


def test_source_diff_manifest_reports_added_changed_and_removed_files(tmp_path: Path):
    baseline = write_zip(
        tmp_path / "baseline.zip",
        "baseline",
        {"same.txt": b"same\n", "changed.txt": b"old\n", "removed.bin": b"old"},
    )
    current = write_zip(
        tmp_path / "current.zip",
        "candidate",
        {"same.txt": b"same\n", "changed.txt": b"new\n", "added.txt": b"added\n"},
    )
    report = candidate.write_source_diff(baseline, current, tmp_path / "diff")
    states = {item["path"]: item["state"] for item in report["files"]}
    assert states == {
        "added.txt": "added",
        "changed.txt": "changed",
        "removed.bin": "removed",
    }
    patch = (tmp_path / "diff/SOURCE_DIFF.patch").read_text(encoding="utf-8")
    assert "v0.7.0/changed.txt" in patch
    assert "v0.7.1/changed.txt" in patch


def test_local_adapter_verifier_requires_semantic_equivalence_and_cleared_authorities(tmp_path: Path):
    evidence = tmp_path / "evidence/local_adapter"
    evidence.mkdir(parents=True)
    fixtures = [
        {
            "fixture": name,
            "authoritySha256": candidate.EXPECTED_AUTHORITY_SHA256[name],
            "reviewedCandidateMeshSha256": candidate.EXPECTED_FIXTURES[name],
            "adapterTransportHashMatchesLegacy": True,
            "semanticComparison": {"passed": True},
            "providerCostZero": True,
        }
        for name in candidate.EXPECTED_FIXTURES
    ]
    (evidence / "local_adapter_three_fixture.json").write_text(
        json.dumps({"schemaVersion": "skyforge.local-adapter-three-fixture-evidence.v2", "passed": True, "paidOperationPerformed": False, "fixtures": fixtures}),
        encoding="utf-8",
    )
    assert candidate.verify_local_adapter(tmp_path / "evidence")["passed"] is True
    fixtures[0]["semanticComparison"] = {"passed": False}
    (evidence / "local_adapter_three_fixture.json").write_text(
        json.dumps({"schemaVersion": "skyforge.local-adapter-three-fixture-evidence.v2", "passed": True, "paidOperationPerformed": False, "fixtures": fixtures}),
        encoding="utf-8",
    )
    with pytest.raises(candidate.CandidateAssemblyError, match="semantic mismatch"):
        candidate.verify_local_adapter(tmp_path / "evidence")

def test_candidate_assembler_refuses_missing_live_blender_primary_evidence(tmp_path: Path):
    with pytest.raises(candidate.CandidateAssemblyError, match="Required evidence is missing"):
        candidate.verify_blender(tmp_path)


def test_live_blender_verifier_enforces_profiles_forward_baselines_and_four_vmp_vectors(
    tmp_path: Path,
):
    blender = tmp_path / "blender"
    blender.mkdir()
    fixtures = []
    for name in candidate.EXPECTED_FIXTURES:
        fixtures.append(
            {
                "fixture": name,
                "profileId": candidate.EXPECTED_PROFILE_ID[name],
                "profileScale": candidate.EXPECTED_PROFILE_SCALE[name],
                "authoritySuitability": {"passed": True},
                "authoritySha256": candidate.EXPECTED_AUTHORITY_SHA256[name],
                "reviewedCandidateMeshSha256": candidate.EXPECTED_FIXTURES[name],
                "adapterTransportHashMatchesLegacy": True,
                "semanticComparison": {"passed": True},
                "blenderSilhouetteIoU": candidate.EXPECTED_LIVE_BLENDER_IOU[name],
                "expectedForwardBaselineIoU": candidate.EXPECTED_LIVE_BLENDER_IOU[name],
                "forwardBaselineTolerance": candidate.LIVE_BASELINE_TOLERANCE,
                "forwardBaselineMatches": True,
                "vmp": {"probeAccepted": True},
            }
        )
    report = {
        "schemaVersion": "skyforge.v071-live-blender-preflight.v3",
        "sidecarVersion": "0.7.1",
        "authoritySuitabilityRequired": True,
        "passed": True,
        "blenderSilhouetteIoUMin": 0.94,
        "fixtures": fixtures,
    }
    (blender / "LIVE_BLENDER_PREFLIGHT.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    for index in range(4):
        (blender / f"fixture-{index}.sfmeshpack").write_bytes(b"fixture")
        (blender / f"fixture-{index}_IMPORT_RECEIPT.json").write_text(
            "{}", encoding="utf-8"
        )
    assert candidate.verify_blender(tmp_path)["passed"] is True

    fixtures[0]["blenderSilhouetteIoU"] = 0.939
    fixtures[0]["forwardBaselineMatches"] = False
    (blender / "LIVE_BLENDER_PREFLIGHT.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    with pytest.raises(candidate.CandidateAssemblyError, match="forward baseline"):
        candidate.verify_blender(tmp_path)


def test_authority_suitability_verifier_requires_exact_field_defect_and_measured_boundary(
    tmp_path: Path, monkeypatch,
):
    root = tmp_path / "authority_suitability"
    root.mkdir()
    accepted = [
        {"filename": f"fixture-{index}.png", "report": {"passed": True}}
        for index in range(4)
    ]
    defect_package = root / "v0.7.0_mbs155_field_defect_review_package.zip"
    defect_image = root / "rejected_three_quarter_beauty_mbs155.png"
    defect_package.write_bytes(b"review-package")
    defect_image.write_bytes(b"beauty")
    original_sha = candidate.sha256_file

    def fixture_sha(path: Path) -> str:
        if path == defect_package:
            return "cdfaf1c1c06ee1e54c7ede9d6d9869ed498c36e3088ae7876ed8ab82e52a5391"
        if path == defect_image:
            return "6a82feefadddce2f09ea318534b3c8d913470164d5ca6f784cb05d4972b50208"
        return original_sha(path)

    monkeypatch.setattr(candidate, "sha256_file", fixture_sha)
    monkeypatch.setattr(
        candidate,
        "decoded_rgba_sha256",
        lambda path: candidate.MBS155_REJECTED_FIXTURE_DECODED_RGBA_SHA256,
    )
    report = {
        "schemaVersion": "skyforge.authority-suitability-evidence.v2",
        "passed": True,
        "acceptedFixtures": accepted,
        "rejectedFieldDefect": {
            "finding": "MBS-155",
            "sha256": "6a82feefadddce2f09ea318534b3c8d913470164d5ca6f784cb05d4972b50208",
            "report": {
                "passed": False,
                "failures": [
                    {"code": "perspective_or_asymmetric_planform"},
                    {"code": "unstable_centerline"},
                    {"code": "not_nose_up"},
                ],
            },
        },
        "priorDefectArtifact": {
            "passed": True,
            "archiveSha256": candidate.V070_MBS155_REVIEW_PACKAGE_SHA256,
            "rejectedFixtureSha256": candidate.MBS155_REJECTED_FIXTURE_SHA256,
            "rejectedFixtureDecodedRgbaSha256": candidate.MBS155_REJECTED_FIXTURE_DECODED_RGBA_SHA256,
            "embeddedAuthoritySha256": candidate.V070_MBS155_EMBEDDED_AUTHORITY_SHA256,
            "embeddedAuthorityDecodedRgbaSha256": candidate.MBS155_REJECTED_FIXTURE_DECODED_RGBA_SHA256,
            "embeddedAuthorityPixelsMatchRejectedFixture": True,
            "v070JobStatus": "rendered",
            "v070BlenderSilhouetteIoU": 0.972942,
        },
        "executionBoundary": {
            "endpoint": "/api/jobs",
            "responseStatus": 422,
            "responseOk": False,
            "reportedSuitabilityPassed": False,
            "jobDirectoriesCreated": [],
            "callCounts": {
                "createJob": 0,
                "resolveProvider": 0,
                "resolveBlender": 0,
                "startJobThread": 0,
                "governedApiRequest": 0,
            },
            "passed": True,
        },
    }
    (root / "authority_suitability_evidence.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    assert candidate.verify_authority_suitability(tmp_path)["passed"] is True
    report["executionBoundary"]["callCounts"]["createJob"] = 1
    (root / "authority_suitability_evidence.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    with pytest.raises(candidate.CandidateAssemblyError, match="pre-job execution boundary"):
        candidate.verify_authority_suitability(tmp_path)


def test_release_reproducibility_verifier_binds_both_double_builds_to_shipped_archives(
    tmp_path: Path,
):
    release_set = tmp_path / "release-set"
    release_set.mkdir()
    source = release_set / "fixture_SOURCE.zip"
    release = release_set / "fixture_RELEASE.zip"
    source.write_bytes(b"source")
    release.write_bytes(b"release")
    source_sha = candidate.sha256_file(source)
    release_sha = candidate.sha256_file(release)
    payload = {
        "schemaVersion": "skyforge.release-reproducibility-evidence.v1",
        "artifactClass": "producer",
        "passed": True,
        "sourceArchive": {
            "normalBuildSha256": source_sha,
            "modeAndTimestampPerturbedBuildSha256": source_sha,
            "shippedSha256": source_sha,
            "byteIdentical": True,
        },
        "releaseArchive": {
            "firstBuildSha256": release_sha,
            "secondBuildSha256": release_sha,
            "shippedSha256": release_sha,
            "byteIdentical": True,
        },
    }
    (release_set / "PRODUCER_RELEASE_REPRODUCIBILITY.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    assert candidate.verify_release_reproducibility(release_set, producer=True)["passed"] is True
    payload["releaseArchive"]["secondBuildSha256"] = "0" * 64
    (release_set / "PRODUCER_RELEASE_REPRODUCIBILITY.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    with pytest.raises(candidate.CandidateAssemblyError, match="release hashes"):
        candidate.verify_release_reproducibility(release_set, producer=True)



def test_migration_verifier_requires_explicit_idempotent_read_only_evidence(tmp_path: Path):
    root = tmp_path / "migration"
    root.mkdir()
    report = {
        "passed": True,
        "sourceEvidenceByteIdentical": True,
        "sourceEvidenceMode": "0o444",
        "assetRole": "air_moving",
        "providerId": "local_deterministic",
        "collisionHintAuthoritative": False,
        "inferencesMade": [],
        "idempotentAssetBytes": True,
    }
    (root / "migration_report.json").write_text(json.dumps(report), encoding="utf-8")
    assert candidate.verify_migration(tmp_path)["passed"] is True
    report["inferencesMade"] = ["role"]
    (root / "migration_report.json").write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(candidate.CandidateAssemblyError, match="inferred"):
        candidate.verify_migration(tmp_path)

def test_meshy_test_mode_verifier_rejects_any_promotion_or_paid_signal(tmp_path: Path):
    root = tmp_path / "meshy_test_mode"
    root.mkdir()
    result = {
        "productionCredentialRead": False,
        "paidLedgerEntryCreated": False,
        "promotionPermitted": False,
        "approvedAssetProduced": False,
        "vmpProduced": False,
        "geometryQualityClaimPermitted": False,
        "authorityPreservationClaimPermitted": False,
        "evidenceClass": "transport_lifecycle_only",
        "consumedCreditsInformational": "0",
    }
    pep = {
        "promotionPermitted": False,
        "evidenceClass": "transport_lifecycle_only",
        "sanitization": {
            "secretsRemoved": True,
            "signedUrlsRemoved": True,
            "localPathsRemoved": True,
        },
    }
    (root / "diagnostic_result.json").write_text(json.dumps(result), encoding="utf-8")
    (root / "provider_evidence_package.json").write_text(json.dumps(pep), encoding="utf-8")
    assert candidate.verify_meshy_test_mode(tmp_path)["promotionPermitted"] is False
    result["vmpProduced"] = True
    (root / "diagnostic_result.json").write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(candidate.CandidateAssemblyError, match="promotable"):
        candidate.verify_meshy_test_mode(tmp_path)
