#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from common.source_binding import PRODUCER_SCOPE, SourceBindingError, verify_binding  # noqa: E402

VERSION = "0.7.1"
PACKAGE_NAME = f"SkyForge_Mesh_Builder_Sidecar_v{VERSION}"
SOURCE_ARCHIVE_NAME = f"{PACKAGE_NAME}_SOURCE.zip"
RELEASE_ARCHIVE_NAME = f"{PACKAGE_NAME}_RELEASE.zip"
REQUIRED_DISTRIBUTIONS = {
    "Flask": "3.1.1",
    "Werkzeug": "3.1.7",
    "blinker": "1.9.0",
    "Pillow": "11.3.0",
    "numpy": "2.3.5",
    "trimesh": "4.11.1",
    "networkx": "3.6.1",
    "pytest": "8.4.1",
    "ruff": "0.15.22",
    "requests": "2.32.3",
    "jsonschema": "4.26.0",
    "rfc8785": "0.1.4",
}
TRANSIENT_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache"}
EXCLUDED_LOCAL_DIRS = {".venv", ".git"}
FORBIDDEN_DIRS = {"workspace"}
FORBIDDEN_FILES = {"config.json", ".DS_Store"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo"}
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


class SealError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandEvidence:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class PreflightEvidence:
    machine_environment: dict[str, str]
    dependency_versions: dict[str, str]
    binding: dict[str, object]
    lint: CommandEvidence
    tests: CommandEvidence
    test_count: int
    skipped_count: int
    failures: int
    errors: int


def package_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def capture_machine_environment() -> dict[str, str]:
    return {
        "operatingSystem": platform.system(),
        "operatingSystemRelease": platform.release(),
        "architecture": platform.machine(),
        "pythonVersion": platform.python_version(),
        "pythonImplementation": platform.python_implementation(),
        "pythonExecutableName": Path(sys.executable).name,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: list[str], *, cwd: Path) -> CommandEvidence:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    evidence = CommandEvidence(
        command=command,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
    if result.returncode != 0:
        raise SealError(
            f"Preflight command failed ({' '.join(command)})\n{result.stdout}{result.stderr}"
        )
    return evidence


def verify_dependency_versions() -> dict[str, str]:
    installed: dict[str, str] = {}
    mismatches: list[str] = []
    for distribution, expected in REQUIRED_DISTRIBUTIONS.items():
        try:
            actual = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            mismatches.append(f"{distribution} is unavailable (expected {expected})")
            continue
        installed[distribution] = actual
        if actual != expected:
            mismatches.append(f"{distribution}=={actual} (expected {expected})")
    if mismatches:
        raise SealError("Target dependency set is not installed exactly:\n- " + "\n- ".join(mismatches))
    return installed


def resolve_ruff_executable() -> Path:
    ruff = Path(sys.executable).with_name("ruff")
    if not ruff.is_file() or not os.access(ruff, os.X_OK):
        raise SealError(f"ruff executable is unavailable beside target Python: {ruff}")
    return ruff


def _pytest_counts(report_path: Path) -> tuple[int, int, int, int]:
    try:
        root = ElementTree.parse(report_path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise SealError("pytest did not produce a readable JUnit report") from exc
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise SealError("pytest JUnit report contains no test suites")
    tests = sum(int(suite.attrib.get("tests", "0")) for suite in suites)
    skipped = sum(int(suite.attrib.get("skipped", "0")) for suite in suites)
    failures = sum(int(suite.attrib.get("failures", "0")) for suite in suites)
    errors = sum(int(suite.attrib.get("errors", "0")) for suite in suites)
    return tests, skipped, failures, errors


def run_preflight(package_root: Path, evidence_dir: Path) -> PreflightEvidence:
    try:
        binding = verify_binding(package_root, PRODUCER_SCOPE)
    except SourceBindingError as exc:
        raise SealError(str(exc)) from exc
    dependency_versions = verify_dependency_versions()
    ruff = resolve_ruff_executable()
    lint = _run([str(ruff), "check", "."], cwd=package_root)
    report_path = evidence_dir / "producer-pytest-junit.xml"
    tests = _run(
        [sys.executable, "-m", "pytest", "-q", f"--junitxml={report_path}"],
        cwd=package_root,
    )
    test_count, skipped_count, failures, errors = _pytest_counts(report_path)
    if test_count <= 0 or skipped_count or failures or errors:
        raise SealError(
            "pytest report is not release-green: "
            f"tests={test_count}, skipped={skipped_count}, failures={failures}, errors={errors}"
        )
    (evidence_dir / "producer-ruff.log").write_text(
        lint.stdout + lint.stderr, encoding="utf-8"
    )
    (evidence_dir / "producer-pytest.log").write_text(
        tests.stdout + tests.stderr, encoding="utf-8"
    )
    return PreflightEvidence(
        machine_environment=capture_machine_environment(),
        dependency_versions=dependency_versions,
        binding=binding,
        lint=lint,
        tests=tests,
        test_count=test_count,
        skipped_count=skipped_count,
        failures=failures,
        errors=errors,
    )


def cleanup_transient_residue(package_root: Path) -> None:
    for path in sorted(package_root.rglob("*"), reverse=True):
        relative = path.relative_to(package_root)
        if any(part in EXCLUDED_LOCAL_DIRS for part in relative.parts):
            continue
        if path.is_dir() and path.name in TRANSIENT_DIRS:
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file() and path.suffix in FORBIDDEN_SUFFIXES:
            path.unlink(missing_ok=True)


def archive_hygiene_findings(package_root: Path) -> list[str]:
    findings: list[str] = []
    for path in package_root.rglob("*"):
        relative = path.relative_to(package_root)
        if any(part in EXCLUDED_LOCAL_DIRS for part in relative.parts):
            continue
        if any(part in FORBIDDEN_DIRS or part in TRANSIENT_DIRS for part in relative.parts):
            findings.append(f"forbidden directory residue: {relative}")
        elif path.is_file() and path.name in FORBIDDEN_FILES:
            findings.append(f"forbidden file: {relative}")
        elif path.is_file() and path.suffix in FORBIDDEN_SUFFIXES:
            findings.append(f"compiled Python residue: {relative}")
    return sorted(set(findings))


def assert_archive_hygiene(package_root: Path) -> None:
    findings = archive_hygiene_findings(package_root)
    if findings:
        raise SealError("Archive hygiene failed:\n- " + "\n- ".join(findings))


def _iter_release_files(package_root: Path):
    for path in sorted(package_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(package_root)
        if any(
            part in FORBIDDEN_DIRS or part in EXCLUDED_LOCAL_DIRS or part in TRANSIENT_DIRS
            for part in relative.parts
        ):
            continue
        if path.name in FORBIDDEN_FILES or path.suffix in FORBIDDEN_SUFFIXES:
            continue
        yield path, relative


def _write_zip_bytes(archive: zipfile.ZipFile, data: bytes, arcname: str, *, executable: bool = False) -> None:
    info = zipfile.ZipInfo(arcname, ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100755 if executable else 0o100644) << 16
    archive.writestr(info, data)


def _write_reproducible_zip_entry(archive: zipfile.ZipFile, path: Path, arcname: str) -> None:
    executable = path.suffix == ".command" or path.name.endswith(".sh")
    _write_zip_bytes(archive, path.read_bytes(), arcname, executable=executable)


def build_source_zip(package_root: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, relative in _iter_release_files(package_root):
            _write_reproducible_zip_entry(
                archive, path, (Path(PACKAGE_NAME) / relative).as_posix()
            )
    with zipfile.ZipFile(destination) as archive:
        names = archive.namelist()
        if not names or any(not name.startswith(f"{PACKAGE_NAME}/") for name in names):
            raise SealError("Source ZIP root is invalid")


def _build_perturbed_source_zip(package_root: Path, destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="skyforge-producer-perturb-") as temporary:
        copied = Path(temporary) / "source"
        shutil.copytree(
            package_root,
            copied,
            ignore=shutil.ignore_patterns(".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__", "workspace"),
        )
        for path in copied.rglob("*"):
            if path.is_file():
                path.chmod(0o600)
                os.utime(path, (1_700_000_000, 1_700_000_000))
        build_source_zip(copied, destination)


def _stable_preflight_summary(evidence: PreflightEvidence, source_sha256: str) -> dict[str, object]:
    return {
        "schemaVersion": "skyforge.producer-release-seal-evidence.v1",
        "version": VERSION,
        "sourceArchiveSha256": source_sha256,
        "sourceBinding": evidence.binding,
        "dependencyVersions": evidence.dependency_versions,
        "ruff": {"returncode": evidence.lint.returncode},
        "pytest": {
            "executed": evidence.test_count,
            "skipped": evidence.skipped_count,
            "failures": evidence.failures,
            "errors": evidence.errors,
            "zeroSkipsAsserted": evidence.skipped_count == 0,
        },
        "archiveHygiene": "pass",
        "reproducibility": {
            "sourceZipModeAndTimestampPerturbation": "pass",
            "releaseZipDoubleBuild": "pass",
        },
        "paidOperationsPerformed": False,
        "importProbeSourceIncluded": False,
        "userTestingCleared": False,
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_release_zip(files: list[Path], destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files, key=lambda item: item.name):
            _write_reproducible_zip_entry(archive, path, path.name)


def seal_release(package_root: Path, output_dir: Path, *, preflight_only: bool = False) -> Path | None:
    package_root = package_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    release_set = output_dir / f"{PACKAGE_NAME}_RELEASE_SET"
    if release_set.exists():
        raise SealError(f"Release destination already exists: {release_set}")

    workspace_preexisting = (package_root / "workspace").exists()
    cleanup_transient_residue(package_root)
    assert_archive_hygiene(package_root)
    with tempfile.TemporaryDirectory(prefix="skyforge-v071-producer-seal-") as temp_name:
        temp = Path(temp_name)
        evidence = run_preflight(package_root, temp)
        if not workspace_preexisting:
            shutil.rmtree(package_root / "workspace", ignore_errors=True)
        cleanup_transient_residue(package_root)
        assert_archive_hygiene(package_root)
        if preflight_only:
            print(
                f"PREFLIGHT GREEN: ruff=0, pytest={evidence.test_count} passed, "
                f"skipped={evidence.skipped_count}, failures={evidence.failures}, errors={evidence.errors}"
            )
            return None

        staging = temp / release_set.name
        staging.mkdir()
        source_archive = staging / SOURCE_ARCHIVE_NAME
        source_perturbed = temp / "producer-source-perturbed.zip"
        build_source_zip(package_root, source_archive)
        _build_perturbed_source_zip(package_root, source_perturbed)
        if source_archive.read_bytes() != source_perturbed.read_bytes():
            raise SealError("Producer source ZIP changed under mode/timestamp perturbation")
        source_sha = sha256_file(source_archive)
        source_sidecar = staging / f"{source_archive.name}.sha256"
        source_sidecar.write_text(f"{source_sha}  {source_archive.name}\n", encoding="utf-8")
        binding_copy = staging / PRODUCER_SCOPE.binding_filename
        shutil.copy2(package_root / PRODUCER_SCOPE.binding_filename, binding_copy)
        summary_path = staging / "PRODUCER_RELEASE_SEAL_EVIDENCE.json"
        _write_json(summary_path, _stable_preflight_summary(evidence, source_sha))
        raw_dir = staging / "RAW_PREFLIGHT_LOGS"
        raw_dir.mkdir()
        for name in ("producer-ruff.log", "producer-pytest.log", "producer-pytest-junit.xml"):
            shutil.copy2(temp / name, raw_dir / name)
        release_archive = staging / RELEASE_ARCHIVE_NAME
        release_first = temp / "producer-release-first.zip"
        release_second = temp / "producer-release-second.zip"
        release_files = [source_archive, source_sidecar, binding_copy, summary_path]
        build_release_zip(release_files, release_first)
        build_release_zip(release_files, release_second)
        if release_first.read_bytes() != release_second.read_bytes():
            raise SealError("Producer release ZIP double-build mismatch")
        shutil.copy2(release_first, release_archive)
        release_sha = sha256_file(release_archive)
        (staging / f"{release_archive.name}.sha256").write_text(
            f"{release_sha}  {release_archive.name}\n", encoding="utf-8"
        )
        _write_json(
            staging / "PRODUCER_RELEASE_REPRODUCIBILITY.json",
            {
                "schemaVersion": "skyforge.release-reproducibility-evidence.v1",
                "artifactClass": "producer",
                "version": VERSION,
                "sourceArchive": {
                    "normalBuildSha256": source_sha,
                    "modeAndTimestampPerturbedBuildSha256": sha256_file(source_perturbed),
                    "shippedSha256": source_sha,
                    "modePerturbation": "all copied regular files chmod 0600 before normalized ZIP write",
                    "timestampPerturbation": "all copied regular files set to Unix time 1700000000 before normalized ZIP write",
                    "byteIdentical": source_archive.read_bytes() == source_perturbed.read_bytes(),
                },
                "releaseArchive": {
                    "firstBuildSha256": sha256_file(release_first),
                    "secondBuildSha256": sha256_file(release_second),
                    "shippedSha256": release_sha,
                    "byteIdentical": release_first.read_bytes() == release_second.read_bytes(),
                },
                "normalizedZipTimestamp": "2026-01-01T00:00:00",
                "normalizedModes": {"regular": "0644", "commandOrShell": "0755"},
                "passed": (
                    source_archive.read_bytes() == source_perturbed.read_bytes()
                    and release_first.read_bytes() == release_second.read_bytes()
                    and sha256_file(release_first) == release_sha
                ),
            },
        )
        os.replace(staging, release_set)
        return release_set


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Preflight and deterministically seal the SkyForge producer v{VERSION}"
    )
    parser.add_argument("--package-root", type=Path, default=package_root_from_script())
    parser.add_argument("--output-dir", type=Path, default=package_root_from_script().parent)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    try:
        result = seal_release(args.package_root, args.output_dir, preflight_only=args.preflight_only)
    except SealError as exc:
        print(f"RELEASE NOT SEALED: {exc}", file=sys.stderr)
        return 1
    if result:
        print(f"RELEASE SEALED: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
