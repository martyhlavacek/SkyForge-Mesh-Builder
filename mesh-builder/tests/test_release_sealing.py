from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts import seal_release


def evidence() -> seal_release.PreflightEvidence:
    command = seal_release.CommandEvidence(
        command=["fixture"], returncode=0, stdout="ok", stderr=""
    )
    return seal_release.PreflightEvidence(
        machine_environment={
            "operatingSystem": "Darwin",
            "operatingSystemRelease": "fixture",
            "architecture": "arm64",
            "pythonVersion": "3.13.0",
            "pythonImplementation": "CPython",
            "pythonExecutableName": "python",
        },
        dependency_versions=dict(seal_release.REQUIRED_DISTRIBUTIONS),
        binding={
            "verified": True,
            "bindingFile": "PRODUCER_SOURCE_BINDING.json",
            "fileCount": 2,
            "treeManifestSha256": "1" * 64,
            "dependencyContract": {"exactPinCount": 12},
        },
        lint=command,
        tests=command,
        test_count=200,
        skipped_count=0,
        failures=0,
        errors=0,
    )


def test_archive_hygiene_rejects_runtime_and_compiled_residue(tmp_path: Path):
    (tmp_path / "safe.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "job.json").write_text("{}", encoding="utf-8")
    (tmp_path / "module.pyc").write_bytes(b"compiled")
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    findings = seal_release.archive_hygiene_findings(tmp_path)
    assert any("workspace" in finding for finding in findings)
    assert any("module.pyc" in finding for finding in findings)
    assert not any(".venv" in finding for finding in findings)


def test_source_zip_has_one_versioned_root_and_excludes_residue(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("fixture\n", encoding="utf-8")
    (source / "package.py").write_text("value = 1\n", encoding="utf-8")
    (source / ".venv" / "bin").mkdir(parents=True)
    destination = tmp_path / "candidate.zip"
    seal_release.build_source_zip(source, destination)
    with zipfile.ZipFile(destination) as archive:
        assert sorted(archive.namelist()) == [
            f"{seal_release.PACKAGE_NAME}/README.md",
            f"{seal_release.PACKAGE_NAME}/package.py",
        ]


def test_source_zip_is_byte_reproducible_and_mode_normalized(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    document = source / "README.md"
    launcher = source / "Run.command"
    document.write_text("fixture\n", encoding="utf-8")
    launcher.write_text("#!/bin/zsh\n", encoding="utf-8")
    document.chmod(0o600)
    launcher.chmod(0o600)
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    seal_release.build_source_zip(source, first)
    document.chmod(0o644)
    launcher.chmod(0o755)
    seal_release.build_source_zip(source, second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        document_mode = archive.getinfo(f"{seal_release.PACKAGE_NAME}/README.md").external_attr >> 16
        launcher_mode = archive.getinfo(f"{seal_release.PACKAGE_NAME}/Run.command").external_attr >> 16
    assert document_mode & 0o777 == 0o644
    assert launcher_mode & 0o777 == 0o755


def test_preflight_failure_leaves_no_release_set(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("fixture\n", encoding="utf-8")

    def fail(*_args, **_kwargs):
        raise seal_release.SealError("fixture failure")

    monkeypatch.setattr(seal_release, "run_preflight", fail)
    with pytest.raises(seal_release.SealError, match="fixture failure"):
        seal_release.seal_release(source, tmp_path / "out")
    assert list((tmp_path / "out").iterdir()) == []


def test_successful_seal_builds_separate_deterministic_source_and_release(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("fixture\n", encoding="utf-8")
    (source / "PRODUCER_SOURCE_BINDING.json").write_text("{}\n", encoding="utf-8")
    def fake_preflight(_root, evidence_dir):
        (evidence_dir / "producer-ruff.log").write_text("ok\n", encoding="utf-8")
        (evidence_dir / "producer-pytest.log").write_text("200 passed\n", encoding="utf-8")
        (evidence_dir / "producer-pytest-junit.xml").write_text(
            '<testsuite tests="200" skipped="0" failures="0" errors="0"/>',
            encoding="utf-8",
        )
        return evidence()

    monkeypatch.setattr(seal_release, "run_preflight", fake_preflight)
    release_set = seal_release.seal_release(source, tmp_path / "out")
    assert release_set is not None

    source_zip = release_set / seal_release.SOURCE_ARCHIVE_NAME
    release_zip = release_set / seal_release.RELEASE_ARCHIVE_NAME
    assert source_zip.is_file() and release_zip.is_file()
    assert (release_set / f"{source_zip.name}.sha256").read_text().startswith(
        seal_release.sha256_file(source_zip)
    )
    assert (release_set / f"{release_zip.name}.sha256").read_text().startswith(
        seal_release.sha256_file(release_zip)
    )
    summary = json.loads((release_set / "PRODUCER_RELEASE_SEAL_EVIDENCE.json").read_text())
    assert summary["pytest"]["zeroSkipsAsserted"] is True
    assert summary["reproducibility"] == {
        "releaseZipDoubleBuild": "pass",
        "sourceZipModeAndTimestampPerturbation": "pass",
    }
    assert summary["userTestingCleared"] is False
    reproducibility = json.loads(
        (release_set / "PRODUCER_RELEASE_REPRODUCIBILITY.json").read_text()
    )
    assert reproducibility["passed"] is True
    assert reproducibility["sourceArchive"] == {
        "normalBuildSha256": seal_release.sha256_file(source_zip),
        "modeAndTimestampPerturbedBuildSha256": seal_release.sha256_file(source_zip),
        "shippedSha256": seal_release.sha256_file(source_zip),
        "modePerturbation": "all copied regular files chmod 0600 before normalized ZIP write",
        "timestampPerturbation": "all copied regular files set to Unix time 1700000000 before normalized ZIP write",
        "byteIdentical": True,
    }
    assert reproducibility["releaseArchive"]["firstBuildSha256"] == seal_release.sha256_file(release_zip)
    assert reproducibility["releaseArchive"]["secondBuildSha256"] == seal_release.sha256_file(release_zip)
    assert reproducibility["releaseArchive"]["shippedSha256"] == seal_release.sha256_file(release_zip)
    assert reproducibility["releaseArchive"]["byteIdentical"] is True
    with zipfile.ZipFile(release_zip) as archive:
        names = set(archive.namelist())
    assert source_zip.name in names
    assert "PRODUCER_SOURCE_BINDING.json" in names
    assert "PRODUCER_RELEASE_SEAL_EVIDENCE.json" in names


def test_seal_release_script_is_directly_invokable_from_package_root():
    package_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/seal_release.py", "--help"],
        cwd=package_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--package-root" in result.stdout


def test_ruff_resolution_uses_target_python_environment_not_shell_path(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "clean_env" / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text("", encoding="utf-8")
    ruff = bin_dir / "ruff"
    ruff.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    ruff.chmod(0o755)
    monkeypatch.setattr(seal_release.sys, "executable", str(python))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert seal_release.resolve_ruff_executable() == ruff


def test_ruff_resolution_fails_closed_when_clean_environment_executable_is_missing(
    tmp_path: Path, monkeypatch
):
    python = tmp_path / "clean_env" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    monkeypatch.setattr(seal_release.sys, "executable", str(python))
    with pytest.raises(seal_release.SealError, match="beside target Python"):
        seal_release.resolve_ruff_executable()
