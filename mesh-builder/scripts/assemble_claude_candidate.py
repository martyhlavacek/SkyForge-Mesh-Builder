#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from PIL import Image

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
BASELINE_SOURCE_SHA256 = "95cf7d790a9fab7c91b97d9140ad13227de02d3398f93411d3e0cf0373635d07"
REVIEWED_BASELINE_CANDIDATE_SHA256 = "a050946eafb4c00fc3c8f2189ac6be3e115a8931bffc9df9f208d2d1cdcd4abd"
EXPECTED_FIXTURES = {
    "approved_gunship": "2e2f5f68dfa91ac2611113c35b1b08d90dfdecc2d593f897d40963dd46a2705a",
    "field_gunship": "f4761acd9a1f7c78c4bedc3b9616b162e4a57c2d47a756eb29ad0446952d0e91",
    "interceptor": "97617de238dc451d4ca374e1c0b05461ab71e18cfd82643e0dd2358bf1a8f118",
}
EXPECTED_AUTHORITY_SHA256 = {
    "approved_gunship": "d33075df367c97399b7ed6262030ca8ca0080eda12ebe78eb3eb3fc901f7fc1e",
    "field_gunship": "81deecf91afdc833cdffdc10cba95706afe22484621ba575edb46583bddc5f08",
    "interceptor": "8eb3b788bb2932f3aafdf7051a41c668eec77bb655a84340c45213de378a782f",
}
EXPECTED_PROFILE_ID = {
    "approved_gunship": "enemy_gunship",
    "field_gunship": "enemy_gunship",
    "interceptor": "enemy_interceptor",
}
EXPECTED_PROFILE_SCALE = {
    "approved_gunship": 1.0,
    "field_gunship": 1.0,
    "interceptor": 0.72,
}
EXPECTED_LIVE_BLENDER_IOU = {
    "approved_gunship": 0.975865,
    "field_gunship": 0.947415,
    "interceptor": 0.952496,
}
LIVE_BASELINE_TOLERANCE = 1e-6
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
V070_MBS155_REVIEW_PACKAGE_SHA256 = "cdfaf1c1c06ee1e54c7ede9d6d9869ed498c36e3088ae7876ed8ab82e52a5391"
V070_MBS155_EMBEDDED_AUTHORITY_SHA256 = "9bba31bc544b6dd84d566d0c6b27b4b8fdc1a3d39f287665c5a8fc9e8f143e9e"
MBS155_REJECTED_FIXTURE_SHA256 = "6a82feefadddce2f09ea318534b3c8d913470164d5ca6f784cb05d4972b50208"
MBS155_REJECTED_FIXTURE_DECODED_RGBA_SHA256 = "4053c4b9322114b10a998f2f5ccaee50a7afd63f6107ce78177fa3a2ad7347f1"


class CandidateAssemblyError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decoded_rgba_sha256(path: Path) -> str:
    try:
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            digest = hashlib.sha256()
            digest.update(rgba.width.to_bytes(4, "big"))
            digest.update(rgba.height.to_bytes(4, "big"))
            digest.update(rgba.tobytes())
            return digest.hexdigest()
    except OSError as exc:
        raise CandidateAssemblyError(f"Required image evidence is unreadable: {path}") from exc


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise CandidateAssemblyError(f"Required evidence is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CandidateAssemblyError(f"Required evidence is invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise CandidateAssemblyError(f"Required evidence is not an object: {path}")
    return value


def verify_sidecar(path: Path) -> str:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.is_file():
        raise CandidateAssemblyError(f"Checksum sidecar is missing: {sidecar}")
    fields = sidecar.read_text(encoding="utf-8").strip().split()
    if len(fields) < 2 or fields[1].lstrip("*") != path.name:
        raise CandidateAssemblyError(f"Checksum sidecar does not bind {path.name}")
    actual = sha256_file(path)
    if fields[0] != actual:
        raise CandidateAssemblyError(f"Checksum mismatch for {path}")
    return actual


def find_one(root: Path, pattern: str) -> Path:
    values = sorted(root.glob(pattern))
    if len(values) != 1:
        raise CandidateAssemblyError(
            f"Expected exactly one {pattern!r} beneath {root}; found {len(values)}"
        )
    return values[0]


def verify_junit(path: Path, *, required_test_prefixes: tuple[str, ...] = ()) -> dict[str, object]:
    if not path.is_file():
        raise CandidateAssemblyError(f"JUnit evidence is missing: {path}")
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    counts = {
        "tests": sum(int(item.attrib.get("tests", "0")) for item in suites),
        "skipped": sum(int(item.attrib.get("skipped", "0")) for item in suites),
        "failures": sum(int(item.attrib.get("failures", "0")) for item in suites),
        "errors": sum(int(item.attrib.get("errors", "0")) for item in suites),
    }
    if counts["tests"] <= 0 or any(counts[name] for name in ("skipped", "failures", "errors")):
        raise CandidateAssemblyError(f"JUnit evidence is not zero-skip green: {path}: {counts}")
    names = {
        case.attrib.get("name", "")
        for suite in suites
        for case in suite.findall("testcase")
    }
    for prefix in required_test_prefixes:
        if not any(name.startswith(prefix) for name in names):
            raise CandidateAssemblyError(f"JUnit evidence is missing required test prefix: {prefix}")
    return counts


def verify_release_set(root: Path, *, producer: bool) -> dict[str, object]:
    if not root.is_dir():
        raise CandidateAssemblyError(f"Release set is missing: {root}")
    source = find_one(root, "*_SOURCE.zip")
    release = find_one(root, "*_RELEASE.zip")
    source_sha = verify_sidecar(source)
    release_sha = verify_sidecar(release)
    evidence_name = (
        "PRODUCER_RELEASE_SEAL_EVIDENCE.json"
        if producer
        else "IMPORT_PROBE_RELEASE_SEAL_EVIDENCE.json"
    )
    evidence = read_json(root / evidence_name)
    if evidence.get("sourceArchiveSha256") != source_sha:
        raise CandidateAssemblyError(f"{evidence_name} does not bind the exact source archive")
    pytest = evidence.get("pytest") or {}
    if not pytest.get("zeroSkipsAsserted") or any(
        int(pytest.get(name, -1)) != 0 for name in ("skipped", "failures", "errors")
    ):
        raise CandidateAssemblyError(f"{evidence_name} is not zero-skip green")
    if evidence.get("ruff", {}).get("returncode") != 0:
        raise CandidateAssemblyError(f"{evidence_name} does not prove Ruff green")
    reproducibility = evidence.get("reproducibility") or {}
    if set(reproducibility.values()) != {"pass"}:
        raise CandidateAssemblyError(f"{evidence_name} does not prove deterministic release sealing")
    if evidence.get("userTestingCleared") is not False:
        raise CandidateAssemblyError(f"{evidence_name} must keep user testing withheld")
    if producer:
        if evidence.get("importProbeSourceIncluded") is not False:
            raise CandidateAssemblyError("Producer release improperly includes Import Probe source")
    else:
        if evidence.get("producerSourcePresent") is not False or evidence.get("producerSourceReachable") is not False:
            raise CandidateAssemblyError("Import Probe release is not producer-independent")
        if evidence.get("pythonPathEnvironmentEmpty") is not True:
            raise CandidateAssemblyError("Import Probe clean environment used PYTHONPATH")
    return {
        "source": source,
        "sourceSha256": source_sha,
        "release": release,
        "releaseSha256": release_sha,
        "evidence": evidence,
    }


def verify_local_adapter(evidence_root: Path) -> dict:
    report = read_json(evidence_root / "local_adapter/local_adapter_three_fixture.json")
    if report.get("schemaVersion") != "skyforge.local-adapter-three-fixture-evidence.v2":
        raise CandidateAssemblyError("Local adapter evidence schema is not v2 semantic equivalence")
    if report.get("passed") is not True or report.get("paidOperationPerformed") is not False:
        raise CandidateAssemblyError("Local adapter report is not a passing no-charge result")
    found = {item.get("fixture"): item for item in report.get("fixtures", [])}
    if set(found) != set(EXPECTED_FIXTURES):
        raise CandidateAssemblyError("Local adapter report does not contain exactly the three cleared fixtures")
    for name in EXPECTED_FIXTURES:
        item = found[name]
        if item.get("authoritySha256") != EXPECTED_AUTHORITY_SHA256[name]:
            raise CandidateAssemblyError(f"Local adapter authority mismatch: {name}")
        if item.get("reviewedCandidateMeshSha256") != EXPECTED_FIXTURES[name]:
            raise CandidateAssemblyError(f"Local adapter reviewed-candidate reference mismatch: {name}")
        if item.get("adapterTransportHashMatchesLegacy") is not True:
            raise CandidateAssemblyError(f"Local adapter transport mismatch against legacy path: {name}")
        if item.get("semanticComparison", {}).get("passed") is not True:
            raise CandidateAssemblyError(f"Local adapter semantic mismatch: {name}")
        if item.get("providerCostZero") is not True:
            raise CandidateAssemblyError(f"Local adapter cost evidence is not zero: {name}")
    return report


def verify_blender(evidence_root: Path) -> dict:
    report = read_json(evidence_root / "blender/LIVE_BLENDER_PREFLIGHT.json")
    if report.get("schemaVersion") != "skyforge.v071-live-blender-preflight.v3":
        raise CandidateAssemblyError("Live Blender evidence schema is not v3 authority/profile bound")
    if report.get("sidecarVersion") != "0.7.1" or report.get("authoritySuitabilityRequired") is not True:
        raise CandidateAssemblyError("Live Blender evidence is not bound to v0.7.1 authority suitability")
    if report.get("passed") is not True or float(report.get("blenderSilhouetteIoUMin", 0)) != 0.94:
        raise CandidateAssemblyError("Mandatory live Blender report is not green at the 0.94 floor")
    found = {item.get("fixture"): item for item in report.get("fixtures", [])}
    if set(found) != set(EXPECTED_FIXTURES):
        raise CandidateAssemblyError("Live Blender report does not contain exactly the three cleared fixtures")
    for name in EXPECTED_FIXTURES:
        item = found[name]
        if item.get("authoritySha256") != EXPECTED_AUTHORITY_SHA256[name]:
            raise CandidateAssemblyError(f"Live Blender authority mismatch: {name}")
        if item.get("profileId") != EXPECTED_PROFILE_ID[name]:
            raise CandidateAssemblyError(f"Live Blender profile mismatch: {name}")
        if float(item.get("profileScale", -1)) != EXPECTED_PROFILE_SCALE[name]:
            raise CandidateAssemblyError(f"Live Blender profile scale mismatch: {name}")
        if item.get("authoritySuitability", {}).get("passed") is not True:
            raise CandidateAssemblyError(f"Live Blender authority suitability failed: {name}")
        if item.get("forwardBaselineMatches") is not True:
            raise CandidateAssemblyError(f"Live Blender forward baseline was not declared as matching: {name}")
        if abs(float(item.get("blenderSilhouetteIoU", 0)) - EXPECTED_LIVE_BLENDER_IOU[name]) > LIVE_BASELINE_TOLERANCE:
            raise CandidateAssemblyError(f"Live Blender forward baseline changed without recalibration: {name}")
        if item.get("reviewedCandidateMeshSha256") != EXPECTED_FIXTURES[name]:
            raise CandidateAssemblyError(f"Live Blender reviewed-candidate reference mismatch: {name}")
        if item.get("adapterTransportHashMatchesLegacy") is not True:
            raise CandidateAssemblyError(f"Live Blender local-adapter transport mismatch: {name}")
        if item.get("semanticComparison", {}).get("passed") is not True:
            raise CandidateAssemblyError(f"Live Blender local-adapter semantic mismatch: {name}")
        if float(item.get("blenderSilhouetteIoU", 0)) < 0.94:
            raise CandidateAssemblyError(f"Live Blender IoU below floor: {name}")
        if not item.get("vmp", {}).get("probeAccepted"):
            raise CandidateAssemblyError(f"Independent Import Probe did not accept live fixture VMP: {name}")
    if len(list((evidence_root / "blender").glob("*.sfmeshpack"))) < 4:
        raise CandidateAssemblyError("Live Blender evidence must contain three embedded and one hash-only VMP")
    if len(list((evidence_root / "blender").glob("*IMPORT_RECEIPT.json"))) < 4:
        raise CandidateAssemblyError("Live Blender evidence must contain four Import Receipts")
    return report



def verify_migration(evidence_root: Path) -> dict:
    report = read_json(evidence_root / "migration/migration_report.json")
    if report.get("passed") is not True:
        raise CandidateAssemblyError("Asset-v3 migration evidence is not green")
    if report.get("sourceEvidenceByteIdentical") is not True or report.get("sourceEvidenceMode") != "0o444":
        raise CandidateAssemblyError("Migration evidence did not preserve read-only byte-identical legacy bytes")
    if report.get("assetRole") != "air_moving" or report.get("providerId") != "local_deterministic":
        raise CandidateAssemblyError("Migration evidence does not prove explicit local air_moving semantics")
    if report.get("collisionHintAuthoritative") is not False:
        raise CandidateAssemblyError("Migration evidence made collision authoritative")
    if report.get("inferencesMade") != [] or report.get("idempotentAssetBytes") is not True:
        raise CandidateAssemblyError("Migration evidence is inferred or non-idempotent")
    return report

def verify_governance(evidence_root: Path) -> dict:
    report = read_json(evidence_root / "governance/governance_byte_identity.json")
    if report.get("passed") is not True or len(report.get("files", [])) != 12:
        raise CandidateAssemblyError("Governance byte-identity evidence must prove all 12 protected modules")
    return report


def verify_mock_provider(evidence_root: Path) -> dict:
    report = read_json(evidence_root / "mock_provider/mock_provider_fault_matrix_report.json")
    if report.get("productionCredentialsUsed") is not False or report.get("paidDispatchEnabled") is not False:
        raise CandidateAssemblyError("Mock-provider evidence does not preserve paid-work prohibition")
    cases = {item.get("case"): item for item in report.get("cases", [])}
    expected_states = {
        "success": ("reconciled", 1),
        "failure_refund": ("released", 1),
        "delayed": ("unresolved", 1),
        "timeout": ("unresolved", 1),
        "expiry": ("unresolved", 1),
        "capture_failure": ("unresolved", 1),
        "crash_after_intent": ("released", 0),
        "crash_after_reserve": ("released", 0),
        "orphan_unique": ("reconciled", 1),
        "orphan_ambiguous": ("unresolved", 2),
    }
    if report.get("mbs136RealProviderStatus") != "open" or set(cases) != set(expected_states):
        raise CandidateAssemblyError("Mock-provider report does not preserve MBS-136 or the required fault matrix")
    for name, (state, dispatches) in expected_states.items():
        if cases[name].get("finalReservationState") != state or cases[name].get("providerDispatchCount") != dispatches:
            raise CandidateAssemblyError(f"Mock-provider fault case is not fail-closed: {name}")
    return report


def verify_meshy_test_mode(evidence_root: Path) -> dict:
    result = read_json(evidence_root / "meshy_test_mode/diagnostic_result.json")
    required_false = (
        "productionCredentialRead",
        "paidLedgerEntryCreated",
        "promotionPermitted",
        "approvedAssetProduced",
        "vmpProduced",
        "geometryQualityClaimPermitted",
        "authorityPreservationClaimPermitted",
    )
    if any(result.get(name) is not False for name in required_false):
        raise CandidateAssemblyError("Meshy public test-mode evidence is promotable, paid, or overclaims")
    if result.get("evidenceClass") != "transport_lifecycle_only":
        raise CandidateAssemblyError("Meshy diagnostic is not transport/lifecycle-only evidence")
    if str(result.get("consumedCreditsInformational")) != "0":
        raise CandidateAssemblyError("Meshy public test-mode evidence did not report zero consumed credits")
    pep = read_json(evidence_root / "meshy_test_mode/provider_evidence_package.json")
    if pep.get("promotionPermitted") is not False or pep.get("evidenceClass") != "transport_lifecycle_only":
        raise CandidateAssemblyError("Meshy PEP does not fail closed")
    sanitization = pep.get("sanitization") or {}
    if any(sanitization.get(name) is not True for name in ("secretsRemoved", "signedUrlsRemoved", "localPathsRemoved")):
        raise CandidateAssemblyError("Meshy PEP sanitization evidence is incomplete")
    return result


def verify_authority_suitability(evidence_root: Path) -> dict:
    report = read_json(evidence_root / "authority_suitability/authority_suitability_evidence.json")
    if report.get("schemaVersion") != "skyforge.authority-suitability-evidence.v2" or report.get("passed") is not True:
        raise CandidateAssemblyError("MBS-155 authority-suitability evidence is not green")
    accepted = report.get("acceptedFixtures") or []
    if len(accepted) != 4 or any(item.get("report", {}).get("passed") is not True for item in accepted):
        raise CandidateAssemblyError("Cleared authority fixtures did not all pass the v0.7.1 gate")
    rejected = report.get("rejectedFieldDefect") or {}
    failures = {item.get("code") for item in (rejected.get("report") or {}).get("failures", [])}
    required = {"perspective_or_asymmetric_planform", "unstable_centerline", "not_nose_up"}
    if (
        rejected.get("finding") != "MBS-155"
        or rejected.get("sha256") != "6a82feefadddce2f09ea318534b3c8d913470164d5ca6f784cb05d4972b50208"
        or rejected.get("report", {}).get("passed") is not False
        or not required <= failures
    ):
        raise CandidateAssemblyError("The exact MBS-155 three-quarter beauty was not rejected for the required reasons")
    prior = report.get("priorDefectArtifact") or {}
    defect_package = evidence_root / "authority_suitability/v0.7.0_mbs155_field_defect_review_package.zip"
    defect_image = evidence_root / "authority_suitability/rejected_three_quarter_beauty_mbs155.png"
    if (
        prior.get("passed") is not True
        or prior.get("archiveSha256") != V070_MBS155_REVIEW_PACKAGE_SHA256
        or prior.get("rejectedFixtureSha256") != MBS155_REJECTED_FIXTURE_SHA256
        or prior.get("rejectedFixtureDecodedRgbaSha256")
        != MBS155_REJECTED_FIXTURE_DECODED_RGBA_SHA256
        or prior.get("embeddedAuthoritySha256")
        != V070_MBS155_EMBEDDED_AUTHORITY_SHA256
        or prior.get("embeddedAuthorityDecodedRgbaSha256")
        != MBS155_REJECTED_FIXTURE_DECODED_RGBA_SHA256
        or prior.get("embeddedAuthorityPixelsMatchRejectedFixture") is not True
        or prior.get("v070JobStatus") != "rendered"
        or float(prior.get("v070BlenderSilhouetteIoU", 0)) < 0.94
        or not defect_package.is_file()
        or sha256_file(defect_package) != prior.get("archiveSha256")
        or not defect_image.is_file()
        or sha256_file(defect_image) != prior.get("rejectedFixtureSha256")
        or decoded_rgba_sha256(defect_image)
        != prior.get("rejectedFixtureDecodedRgbaSha256")
    ):
        raise CandidateAssemblyError("MBS-155 prior field-defect evidence is incomplete or unbound")
    boundary = report.get("executionBoundary") or {}
    call_counts = boundary.get("callCounts") or {}
    if (
        boundary.get("passed") is not True
        or boundary.get("endpoint") != "/api/jobs"
        or boundary.get("responseStatus") != 422
        or boundary.get("responseOk") is not False
        or boundary.get("reportedSuitabilityPassed") is not False
        or boundary.get("jobDirectoriesCreated") != []
        or set(call_counts) != {
            "createJob",
            "resolveProvider",
            "resolveBlender",
            "startJobThread",
            "governedApiRequest",
        }
        or any(call_counts.values())
    ):
        raise CandidateAssemblyError("MBS-155 evidence crossed the pre-job execution boundary")
    return report


def verify_release_reproducibility(release_set: Path, *, producer: bool) -> dict:
    name = "PRODUCER_RELEASE_REPRODUCIBILITY.json" if producer else "IMPORT_PROBE_RELEASE_REPRODUCIBILITY.json"
    report = read_json(release_set / name)
    expected_class = "producer" if producer else "import_probe"
    if report.get("schemaVersion") != "skyforge.release-reproducibility-evidence.v1":
        raise CandidateAssemblyError(f"{name} schema is invalid")
    if report.get("artifactClass") != expected_class or report.get("passed") is not True:
        raise CandidateAssemblyError(f"{name} is not green")
    source = find_one(release_set, "*_SOURCE.zip")
    release = find_one(release_set, "*_RELEASE.zip")
    source_record = report.get("sourceArchive") or {}
    release_record = report.get("releaseArchive") or {}
    source_sha = sha256_file(source)
    release_sha = sha256_file(release)
    if source_record.get("byteIdentical") is not True or release_record.get("byteIdentical") is not True:
        raise CandidateAssemblyError(f"{name} does not prove byte-identical double builds")
    if {source_record.get(key) for key in ("normalBuildSha256", "modeAndTimestampPerturbedBuildSha256", "shippedSha256")} != {source_sha}:
        raise CandidateAssemblyError(f"{name} source hashes do not bind the shipped source")
    if {release_record.get(key) for key in ("firstBuildSha256", "secondBuildSha256", "shippedSha256")} != {release_sha}:
        raise CandidateAssemblyError(f"{name} release hashes do not bind the shipped release")
    return report


def verify_probe_mutations(probe_release_set: Path) -> dict[str, object]:
    junit = probe_release_set / "RAW_PREFLIGHT_LOGS/probe-pytest-junit.xml"
    prefixes = tuple(f"test_mutation_{number:02d}" for number in range(1, 19)) + (
        "test_mutation_03b_regular_file_parent_collision_is_rejected_with_rooted_diagnostic",
    )
    return verify_junit(junit, required_test_prefixes=prefixes)


def _zip_entries(path: Path) -> tuple[str, dict[str, bytes]]:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        roots = {PurePosixPath(name).parts[0] for name in names}
        if len(roots) != 1:
            raise CandidateAssemblyError(f"Archive does not have one root: {path}")
        root = next(iter(roots))
        return root, {
            PurePosixPath(name).relative_to(root).as_posix(): archive.read(name)
            for name in names
        }


def write_source_diff(baseline_zip: Path, candidate_zip: Path, output_dir: Path) -> dict[str, object]:
    _, baseline = _zip_entries(baseline_zip)
    _, candidate = _zip_entries(candidate_zip)
    paths = sorted(set(baseline) | set(candidate))
    changed: list[dict[str, object]] = []
    patch: list[str] = []
    for path in paths:
        before = baseline.get(path)
        after = candidate.get(path)
        if before == after:
            continue
        state = "added" if before is None else "removed" if after is None else "changed"
        changed.append(
            {
                "path": path,
                "state": state,
                "baselineSha256": hashlib.sha256(before).hexdigest() if before is not None else None,
                "candidateSha256": hashlib.sha256(after).hexdigest() if after is not None else None,
            }
        )
        try:
            before_text = (before or b"").decode("utf-8").splitlines(keepends=True)
            after_text = (after or b"").decode("utf-8").splitlines(keepends=True)
        except UnicodeDecodeError:
            patch.append(f"Binary file {path}: {state}\n")
            continue
        patch.extend(
            difflib.unified_diff(
                before_text,
                after_text,
                fromfile=f"v0.7.0/{path}",
                tofile=f"v0.7.1/{path}",
            )
        )
    manifest = {
        "schemaVersion": "skyforge.source-diff-manifest.v1",
        "baselineArchiveSha256": sha256_file(baseline_zip),
        "candidateArchiveSha256": sha256_file(candidate_zip),
        "changedFileCount": len(changed),
        "files": changed,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "SOURCE_DIFF_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "SOURCE_DIFF.patch").write_text("".join(patch), encoding="utf-8")
    return manifest


def copy_tree_contents(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise CandidateAssemblyError(f"Required directory is missing: {source}")
    shutil.copytree(source, destination)


def write_sha256sums(root: Path) -> None:
    lines = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative == "SHA256SUMS.txt":
            continue
        lines.append(f"{sha256_file(path)}  {relative}\n")
    (root / "SHA256SUMS.txt").write_text("".join(lines), encoding="utf-8")


def build_zip(root: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            info = zipfile.ZipInfo(path.relative_to(root).as_posix(), ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def assemble(
    *,
    baseline_zip: Path,
    reviewed_baseline_candidate: Path,
    producer_release_set: Path,
    probe_release_set: Path,
    evidence_root: Path,
    handoff_root: Path,
    output_dir: Path,
) -> Path:
    baseline_zip = baseline_zip.resolve()
    reviewed_baseline_candidate = reviewed_baseline_candidate.resolve()
    if sha256_file(baseline_zip) != BASELINE_SOURCE_SHA256:
        raise CandidateAssemblyError("Exact reviewed v0.7.0 source baseline identity failed")
    if sha256_file(reviewed_baseline_candidate) != REVIEWED_BASELINE_CANDIDATE_SHA256:
        raise CandidateAssemblyError("Exact reviewed v0.7.0 outer candidate identity failed")
    producer_release_set = producer_release_set.resolve()
    probe_release_set = probe_release_set.resolve()
    producer = verify_release_set(producer_release_set, producer=True)
    probe = verify_release_set(probe_release_set, producer=False)
    producer_repro = verify_release_reproducibility(producer_release_set, producer=True)
    probe_repro = verify_release_reproducibility(probe_release_set, producer=False)
    producer_junit = producer_release_set / "RAW_PREFLIGHT_LOGS/producer-pytest-junit.xml"
    producer_counts = verify_junit(
        producer_junit,
        required_test_prefixes=(
            "test_artifact_writer_preserves_read_only_byte_identical_legacy_copy",
            "test_build_job_payload",
            "test_core_test_suite_blocks_real_network",
            "test_exact_user_reported_three_quarter_beauty_is_rejected_before_provider_or_job",
            "test_all_cleared_authority_fixtures_pass_suitability_gate",
            "test_ninety_degree_rotated_authority_is_rejected_as_not_nose_up",
            "test_governed_authority_lineage_tamper_is_rejected_before_job_allocation",
            "test_successful_seal_builds_separate_deterministic_source_and_release",
        ),
    )
    probe_counts = verify_probe_mutations(probe_release_set)
    local = verify_local_adapter(evidence_root)
    blender = verify_blender(evidence_root)
    migration = verify_migration(evidence_root)
    governance = verify_governance(evidence_root)
    mock = verify_mock_provider(evidence_root)
    meshy = verify_meshy_test_mode(evidence_root)
    authority_suitability = verify_authority_suitability(evidence_root)

    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "SkyForge_Mesh_Builder_v0.7.1_EXACT_CANDIDATE_FOR_CLAUDE.zip"
    sidecar = destination.with_suffix(destination.suffix + ".sha256")
    if destination.exists() or sidecar.exists():
        raise CandidateAssemblyError("Candidate output already exists; exact packages are never overwritten")

    with tempfile.TemporaryDirectory(prefix="skyforge-v071-candidate-") as temporary:
        root = Path(temporary) / "candidate"
        (root / "BASELINE").mkdir(parents=True)
        (root / "CANDIDATE").mkdir()
        shutil.copy2(baseline_zip, root / "BASELINE" / baseline_zip.name)
        shutil.copy2(
            reviewed_baseline_candidate,
            root / "BASELINE" / reviewed_baseline_candidate.name,
        )
        for artifact in (producer["source"], producer["release"]):
            shutil.copy2(artifact, root / "CANDIDATE" / Path(artifact).name)
        for artifact in (probe["source"], probe["release"]):
            shutil.copy2(artifact, root / "CANDIDATE" / Path(artifact).name)
        copy_tree_contents(evidence_root, root / "EVIDENCE")
        repro_dir = root / "EVIDENCE/release_reproducibility"
        repro_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            producer_release_set / "PRODUCER_RELEASE_REPRODUCIBILITY.json",
            repro_dir / "producer.json",
        )
        shutil.copy2(
            probe_release_set / "IMPORT_PROBE_RELEASE_REPRODUCIBILITY.json",
            repro_dir / "import_probe.json",
        )
        tests_evidence = root / "EVIDENCE/tests"
        tests_evidence.mkdir(parents=True, exist_ok=True)
        copy_tree_contents(producer_release_set / "RAW_PREFLIGHT_LOGS", tests_evidence / "producer")
        copy_tree_contents(probe_release_set / "RAW_PREFLIGHT_LOGS", tests_evidence / "import_probe")
        copy_tree_contents(PACKAGE_ROOT / "contracts/vmp/v1", root / "CONTRACTS/vmp/v1")
        amendment = PACKAGE_ROOT / "docs/governance/SF-AM-0001.md"
        (root / "CONTRACTS/governance").mkdir(parents=True)
        shutil.copy2(amendment, root / "CONTRACTS/governance" / amendment.name)
        copy_tree_contents(PACKAGE_ROOT / "docs/v0.7.1", root / "DOCUMENTATION/v0.7.1")
        (root / "SOURCE_DIFF").mkdir()
        diff = write_source_diff(baseline_zip, Path(producer["source"]), root / "SOURCE_DIFF")
        (root / "AUTHORIZATION").mkdir()
        for relative in (
            "REVIEWS/MBS-CR-0021_v0.7.0_Exact_Candidate_Review.md",
            "REVIEWS/MBS-CR-0020_v0.7.0_No-Charge_Implementation_Plan_Adversarial_Review.md",
            "IMPLEMENTATION_PLAN/MBS-PLAN-0001_v0.7.0_No-Charge_Implementation_Plan_and_VMP_v1_Delivery.md",
            "ARCHITECTURE/MBS-PROP-0003_v0.7.0_Architecture_Freeze_and_Validated_Mesh_Package_v1.md",
        ):
            source = handoff_root / relative
            if not source.is_file():
                raise CandidateAssemblyError(f"Authorization document is missing: {source}")
            shutil.copy2(source, root / "AUTHORIZATION" / source.name)
        binding = {
            "schemaVersion": "skyforge.exact-candidate-review-binding.v1",
            "candidateVersion": "0.7.1",
            "baselineSourceArchiveSha256": BASELINE_SOURCE_SHA256,
            "reviewedBaselineCandidateSha256": REVIEWED_BASELINE_CANDIDATE_SHA256,
            "producerSourceArchiveSha256": producer["sourceSha256"],
            "producerReleaseArchiveSha256": producer["releaseSha256"],
            "importProbeSourceArchiveSha256": probe["sourceSha256"],
            "importProbeReleaseArchiveSha256": probe["releaseSha256"],
            "producerSourceBinding": producer["evidence"]["sourceBinding"],
            "importProbeSourceBinding": probe["evidence"]["sourceBinding"],
            "producerTestCounts": producer_counts,
            "probeTestCounts": probe_counts,
            "sourceDiffChangedFileCount": diff["changedFileCount"],
            "localAdapterPassed": local["passed"],
            "liveBlenderPassed": blender["passed"],
            "assetMigrationPassed": migration["passed"],
            "governanceByteIdentityPassed": governance["passed"],
            "governanceProtectedFileCount": len(governance["files"]),
            "authoritySuitabilityPassed": authority_suitability["passed"],
            "producerReleaseReproducibilityPassed": producer_repro["passed"],
            "importProbeReleaseReproducibilityPassed": probe_repro["passed"],
            "mockProviderPaidDispatchEnabled": mock["paidDispatchEnabled"],
            "meshyTestModePromotionPermitted": meshy["promotionPermitted"],
            "mbs136RealProviderStatus": mock["mbs136RealProviderStatus"],
            "paidProviderWorkAuthorized": False,
            "userTestingCleared": False,
            "clearanceAuthority": "Claude independent review of this exact outer archive",
        }
        (root / "REVIEW_BINDING.json").write_text(
            json.dumps(binding, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (root / "README_FIRST.md").write_text(
            "# Project SkyForge Mesh Builder v0.7.1 — exact implementation candidate\n\n"
            "Verify the outer SHA-256 sidecar, then every entry in `SHA256SUMS.txt`. This package is "
            "bound to the exact Claude-reviewed v0.7.0 source archive and exact v0.7.0 outer candidate; "
            "the nested v0.6.0 lineage remains available through that reviewed baseline. It contains "
            "separately sealed producer and Import Probe releases, complete source diff, exact clean-"
            "environment evidence, release double-build evidence, deterministic VMPs, mutation results, "
            "12-file governance byte-identity evidence, zero-credit Meshy lifecycle evidence, and mandatory "
            "three-fixture live Blender reports.\n\n"
            "MBS-144 is explicitly recalibrated: the interceptor uses `enemy_interceptor` at scale `0.72`, "
            "with forward Blender IoU baseline `0.952496`; approved and field gunship baselines remain "
            "`0.975865` and `0.947415`. MBS-155 is the blocking field defect fixed here: the exact three-"
            "quarter beauty that v0.7.0 incorrectly accepted must now be rejected at `/api/jobs` before job "
            "allocation, provider resolution, Blender launch, or governed API spend.\n\n"
            "MBS-150 through MBS-154 remain OPEN geometry-quality findings and are not claimed fixed. "
            "MBS-136 remains OPEN against a real provider; paid provider work is prohibited. "
            "`REVIEW_BINDING.json` declares `userTestingCleared: false`; only Claude review of this exact "
            "archive may authorize further Marty testing.\n",
            encoding="utf-8",
        )
        (root / "CLAUDE_REVIEW_PROMPT.txt").write_text(
            "Perform a fresh-clone adversarial implementation review of this exact checksum-bound Project "
            "SkyForge Mesh Builder Sidecar v0.7.1 candidate. Verify the outer checksum and SHA256SUMS first; "
            "stop on any integrity failure. Verify the exact reviewed v0.7.0 source and outer-candidate "
            "baseline identities, separately sealed producer/probe bindings, complete source diff, exact "
            "dependency proofs, Ruff and zero-skip suites, four release double-build records, deterministic "
            "VMPs, Import Receipts and mutation battery, 12-file governance identity, mock crash/recovery "
            "evidence, zero-credit Meshy isolation, and all three live Blender reports at IoU >= 0.94. "
            "Adjudicate MBS-144 through MBS-147 and confirm SF-AM-0001 itself closes MBS-130. Independently "
            "attack MBS-155 using the exact field-defect beauty and its v0.7.0 rendered review package; prove "
            "it is rejected before create_job, provider resolution, Blender, background work, or API spend, "
            "while all four cleared authorities still pass and accepted manifests bind the suitability "
            "report. Confirm MBS-150 through MBS-154 remain openly registered and no geometry-fix claim is "
            "made. Treat MBS-136 as OPEN against a real provider and do not authorize paid provider work. "
            "Return an explicit verdict and state whether this exact candidate is authorized for Marty user "
            "testing. Do not review any later, reconstructed, or equivalent tree.\n",
            encoding="utf-8",
        )
        write_sha256sums(root)
        build_zip(root, destination)
    sidecar.write_text(f"{sha256_file(destination)}  {destination.name}\n", encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble the exact checksum-bound Claude review candidate")
    parser.add_argument("--baseline-zip", type=Path, required=True)
    parser.add_argument("--reviewed-baseline-candidate", type=Path, required=True)
    parser.add_argument("--producer-release-set", type=Path, required=True)
    parser.add_argument("--probe-release-set", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--handoff-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        destination = assemble(
            baseline_zip=args.baseline_zip,
            reviewed_baseline_candidate=args.reviewed_baseline_candidate,
            producer_release_set=args.producer_release_set,
            probe_release_set=args.probe_release_set,
            evidence_root=args.evidence_root,
            handoff_root=args.handoff_root,
            output_dir=args.output_dir,
        )
    except CandidateAssemblyError as exc:
        print(f"CANDIDATE NOT ASSEMBLED: {exc}")
        return 1
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
