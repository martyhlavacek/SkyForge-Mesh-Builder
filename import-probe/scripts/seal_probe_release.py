#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

PROBE_ROOT = Path(__file__).resolve().parents[1]
if str(PROBE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROBE_ROOT))

from probe.source_binding import SCOPE, ProbeBindingError, verify_binding  # noqa: E402

VERSION = "0.1.1"
PACKAGE_NAME = f"SkyForge_Sprite_Foundry_Import_Probe_v{VERSION}"
SOURCE_ARCHIVE_NAME = f"{PACKAGE_NAME}_SOURCE.zip"
RELEASE_ARCHIVE_NAME = f"{PACKAGE_NAME}_RELEASE.zip"
REQUIRED_DISTRIBUTIONS = {
    "Pillow": "11.3.0",
    "numpy": "2.3.5",
    "trimesh": "4.11.1",
    "networkx": "3.6.1",
    "jsonschema": "4.26.0",
    "rfc8785": "0.1.4",
    "pytest": "8.4.1",
    "ruff": "0.15.22",
}
IGNORED = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__"}
FORBIDDEN_FILES = {".DS_Store"}
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


class ProbeSealError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_independent_environment(root: Path) -> dict[str, object]:
    pythonpath = os.environ.get("PYTHONPATH", "").strip()
    reachable: list[str] = []
    for raw in sys.path:
        if not raw:
            candidate = Path.cwd().resolve()
        else:
            try:
                candidate = Path(raw).expanduser().resolve()
            except OSError:
                continue
        if candidate == root.resolve() or root.resolve() in candidate.parents:
            continue
        if (candidate / "app/vmp_builder.py").is_file() or (candidate / "common/source_binding.py").is_file():
            reachable.append(str(candidate))
    if pythonpath or reachable:
        raise ProbeSealError(
            "Import Probe clean environment is not producer-independent: "
            f"PYTHONPATH={'set' if pythonpath else 'empty'}, producerRoots={reachable}"
        )
    return {
        "pythonPathEnvironmentEmpty": True,
        "producerSourceReachable": False,
    }


def dependency_versions() -> dict[str, str]:
    found: dict[str, str] = {}
    failures: list[str] = []
    for name, expected in REQUIRED_DISTRIBUTIONS.items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            failures.append(f"{name} is unavailable (expected {expected})")
            continue
        found[name] = actual
        if actual != expected:
            failures.append(f"{name}=={actual} (expected {expected})")
    if failures:
        raise ProbeSealError("Probe dependency set is not exact:\n- " + "\n- ".join(failures))
    return found


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise ProbeSealError(
            f"Probe command failed ({' '.join(command)})\n{completed.stdout}{completed.stderr}"
        )
    return completed


def resolve_ruff_executable() -> Path:
    ruff = Path(sys.executable).with_name("ruff")
    if not ruff.is_file() or not os.access(ruff, os.X_OK):
        raise ProbeSealError(f"ruff executable is unavailable beside target Python: {ruff}")
    return ruff


def pytest_counts(path: Path) -> tuple[int, int, int, int]:
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return (
        sum(int(item.attrib.get("tests", "0")) for item in suites),
        sum(int(item.attrib.get("skipped", "0")) for item in suites),
        sum(int(item.attrib.get("failures", "0")) for item in suites),
        sum(int(item.attrib.get("errors", "0")) for item in suites),
    )


def iter_source(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED for part in relative.parts):
            continue
        if path.name in FORBIDDEN_FILES or path.suffix in {".pyc", ".pyo"}:
            continue
        yield path, relative


def write_entry(archive: zipfile.ZipFile, path: Path, name: str) -> None:
    info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100755 if path.name.endswith((".sh", ".command")) else 0o100644) << 16
    archive.writestr(info, path.read_bytes())


def build_source_zip(root: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, relative in iter_source(root):
            write_entry(archive, path, (Path(PACKAGE_NAME) / relative).as_posix())


def build_release_zip(files: list[Path], destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files, key=lambda item: item.name):
            write_entry(archive, path, path.name)


def perturbed_source_zip(root: Path, destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="skyforge-probe-perturb-") as temporary:
        copied = Path(temporary) / "source"
        shutil.copytree(root, copied, ignore=shutil.ignore_patterns(*IGNORED))
        for path in copied.rglob("*"):
            if path.is_file():
                path.chmod(0o600)
                os.utime(path, (1_700_000_000, 1_700_000_000))
        build_source_zip(copied, destination)


def seal(root: Path, output_dir: Path, *, preflight_only: bool = False) -> Path | None:
    root = root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    release_set = output_dir / f"{PACKAGE_NAME}_RELEASE_SET"
    if release_set.exists():
        raise ProbeSealError(f"Probe release destination already exists: {release_set}")
    try:
        binding = verify_binding(root)
    except ProbeBindingError as exc:
        raise ProbeSealError(str(exc)) from exc
    independence = assert_independent_environment(root)
    dependencies = dependency_versions()
    ruff = resolve_ruff_executable()
    with tempfile.TemporaryDirectory(prefix="skyforge-probe-seal-") as temporary:
        temp = Path(temporary)
        lint = run([str(ruff), "check", "."], root)
        junit = temp / "probe-pytest-junit.xml"
        tests = run([sys.executable, "-m", "pytest", "-q", f"--junitxml={junit}"], root)
        executed, skipped, failures, errors = pytest_counts(junit)
        if executed <= 0 or skipped or failures or errors:
            raise ProbeSealError(
                f"Probe suite is not release-green: tests={executed}, skipped={skipped}, "
                f"failures={failures}, errors={errors}"
            )
        if preflight_only:
            print(f"PROBE PREFLIGHT GREEN: ruff=0, pytest={executed}, skipped=0")
            return None
        staging = temp / release_set.name
        staging.mkdir()
        source = staging / SOURCE_ARCHIVE_NAME
        perturb = temp / "probe-source-perturbed.zip"
        build_source_zip(root, source)
        perturbed_source_zip(root, perturb)
        if source.read_bytes() != perturb.read_bytes():
            raise ProbeSealError("Probe source ZIP changed under mode/timestamp perturbation")
        source_sha = sha256_file(source)
        source_sidecar = staging / f"{source.name}.sha256"
        source_sidecar.write_text(f"{source_sha}  {source.name}\n", encoding="utf-8")
        binding_copy = staging / SCOPE.binding_filename
        shutil.copy2(root / SCOPE.binding_filename, binding_copy)
        evidence = staging / "IMPORT_PROBE_RELEASE_SEAL_EVIDENCE.json"
        evidence.write_text(
            json.dumps(
                {
                    "schemaVersion": "skyforge.import-probe-release-seal-evidence.v1",
                    "version": VERSION,
                    "sourceArchiveSha256": source_sha,
                    "sourceBinding": binding,
                    "dependencyVersions": dependencies,
                    "ruff": {"returncode": lint.returncode},
                    "pytest": {
                        "executed": executed,
                        "skipped": skipped,
                        "failures": failures,
                        "errors": errors,
                        "zeroSkipsAsserted": True,
                    },
                    "producerSourcePresent": False,
                    "producerSourceReachable": independence["producerSourceReachable"],
                    "pythonPathEnvironmentEmpty": independence["pythonPathEnvironmentEmpty"],
                    "networkRequired": False,
                    "reproducibility": {
                        "sourceZipModeAndTimestampPerturbation": "pass",
                        "releaseZipDoubleBuild": "pass",
                    },
                    "userTestingCleared": False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        logs = staging / "RAW_PREFLIGHT_LOGS"
        logs.mkdir()
        (logs / "probe-ruff.log").write_text(lint.stdout + lint.stderr, encoding="utf-8")
        (logs / "probe-pytest.log").write_text(tests.stdout + tests.stderr, encoding="utf-8")
        shutil.copy2(junit, logs / junit.name)
        first = temp / "probe-release-first.zip"
        second = temp / "probe-release-second.zip"
        build_release_zip([source, source_sidecar, binding_copy, evidence], first)
        build_release_zip([source, source_sidecar, binding_copy, evidence], second)
        if first.read_bytes() != second.read_bytes():
            raise ProbeSealError("Probe release ZIP double-build mismatch")
        release = staging / RELEASE_ARCHIVE_NAME
        shutil.copy2(first, release)
        release_sha = sha256_file(release)
        (staging / f"{release.name}.sha256").write_text(
            f"{release_sha}  {release.name}\n", encoding="utf-8"
        )
        (staging / "IMPORT_PROBE_RELEASE_REPRODUCIBILITY.json").write_text(
            json.dumps(
                {
                    "schemaVersion": "skyforge.release-reproducibility-evidence.v1",
                    "artifactClass": "import_probe",
                    "version": VERSION,
                    "sourceArchive": {
                        "normalBuildSha256": source_sha,
                        "modeAndTimestampPerturbedBuildSha256": sha256_file(perturb),
                        "shippedSha256": source_sha,
                        "modePerturbation": "all copied regular files chmod 0600 before normalized ZIP write",
                        "timestampPerturbation": "all copied regular files set to Unix time 1700000000 before normalized ZIP write",
                        "byteIdentical": source.read_bytes() == perturb.read_bytes(),
                    },
                    "releaseArchive": {
                        "firstBuildSha256": sha256_file(first),
                        "secondBuildSha256": sha256_file(second),
                        "shippedSha256": release_sha,
                        "byteIdentical": first.read_bytes() == second.read_bytes(),
                    },
                    "normalizedZipTimestamp": "2026-01-01T00:00:00",
                    "normalizedModes": {"regular": "0644", "commandOrShell": "0755"},
                    "passed": (
                        source.read_bytes() == perturb.read_bytes()
                        and first.read_bytes() == second.read_bytes()
                        and sha256_file(first) == release_sha
                    ),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(staging, release_set)
        return release_set


def main() -> int:
    parser = argparse.ArgumentParser(description="Seal the independent Sprite Foundry Import Probe")
    parser.add_argument("--probe-root", type=Path, default=PROBE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=PROBE_ROOT.parent)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    try:
        result = seal(args.probe_root, args.output_dir, preflight_only=args.preflight_only)
    except ProbeSealError as exc:
        print(f"PROBE RELEASE NOT SEALED: {exc}", file=sys.stderr)
        return 1
    if result:
        print(f"PROBE RELEASE SEALED: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
