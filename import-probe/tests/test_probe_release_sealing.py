from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("seal_probe_release", ROOT / "scripts/seal_probe_release.py")
assert SPEC and SPEC.loader
seal_probe_release = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = seal_probe_release
SPEC.loader.exec_module(seal_probe_release)


def test_probe_source_zip_is_mode_and_timestamp_independent(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    readme = source / "README.md"
    readme.write_text("probe\n", encoding="utf-8")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    readme.chmod(0o600)
    seal_probe_release.build_source_zip(source, first)
    readme.chmod(0o644)
    seal_probe_release.build_source_zip(source, second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == [f"{seal_probe_release.PACKAGE_NAME}/README.md"]


def test_probe_release_sealer_fails_before_output_when_binding_fails(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "out"

    def fail(_root):
        raise seal_probe_release.ProbeBindingError("changed")

    monkeypatch.setattr(seal_probe_release, "verify_binding", fail)
    with pytest.raises(seal_probe_release.ProbeSealError, match="changed"):
        seal_probe_release.seal(source, output)
    assert list(output.iterdir()) == []


def test_probe_release_evidence_keeps_consumer_independent_and_testing_withheld(tmp_path: Path):
    payload = {
        "schemaVersion": "skyforge.import-probe-release-seal-evidence.v1",
        "producerSourcePresent": False,
        "networkRequired": False,
        "userTestingCleared": False,
        "pytest": {"zeroSkipsAsserted": True},
    }
    target = tmp_path / "evidence.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    loaded = json.loads(target.read_text())
    assert loaded["producerSourcePresent"] is False
    assert loaded["networkRequired"] is False
    assert loaded["userTestingCleared"] is False



def test_successful_probe_seal_emits_primary_double_build_evidence(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("probe\n", encoding="utf-8")
    (source / "IMPORT_PROBE_SOURCE_BINDING.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(
        seal_probe_release,
        "verify_binding",
        lambda _root: {
            "verified": True,
            "bindingFile": "IMPORT_PROBE_SOURCE_BINDING.json",
            "fileCount": 2,
            "treeManifestSha256": "1" * 64,
        },
    )
    monkeypatch.setattr(
        seal_probe_release,
        "assert_independent_environment",
        lambda _root: {
            "pythonPathEnvironmentEmpty": True,
            "producerSourceReachable": False,
        },
    )
    monkeypatch.setattr(
        seal_probe_release,
        "dependency_versions",
        lambda: dict(seal_probe_release.REQUIRED_DISTRIBUTIONS),
    )
    ruff = tmp_path / "ruff"
    ruff.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    ruff.chmod(0o755)
    monkeypatch.setattr(seal_probe_release, "resolve_ruff_executable", lambda: ruff)

    def fake_run(command, _cwd):
        for argument in command:
            if argument.startswith("--junitxml="):
                Path(argument.split("=", 1)[1]).write_text(
                    '<testsuite tests="38" skipped="0" failures="0" errors="0"/>',
                    encoding="utf-8",
                )
        return seal_probe_release.subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(seal_probe_release, "run", fake_run)
    release_set = seal_probe_release.seal(source, tmp_path / "out")
    assert release_set is not None
    source_zip = release_set / seal_probe_release.SOURCE_ARCHIVE_NAME
    release_zip = release_set / seal_probe_release.RELEASE_ARCHIVE_NAME
    report = json.loads(
        (release_set / "IMPORT_PROBE_RELEASE_REPRODUCIBILITY.json").read_text()
    )
    assert report["passed"] is True
    assert {
        report["sourceArchive"]["normalBuildSha256"],
        report["sourceArchive"]["modeAndTimestampPerturbedBuildSha256"],
        report["sourceArchive"]["shippedSha256"],
    } == {seal_probe_release.sha256_file(source_zip)}
    assert {
        report["releaseArchive"]["firstBuildSha256"],
        report["releaseArchive"]["secondBuildSha256"],
        report["releaseArchive"]["shippedSha256"],
    } == {seal_probe_release.sha256_file(release_zip)}

def test_probe_ruff_resolution_uses_target_python_environment_not_shell_path(
    tmp_path: Path, monkeypatch
):
    bin_dir = tmp_path / "clean_env" / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text("", encoding="utf-8")
    ruff = bin_dir / "ruff"
    ruff.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    ruff.chmod(0o755)
    monkeypatch.setattr(seal_probe_release.sys, "executable", str(python))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert seal_probe_release.resolve_ruff_executable() == ruff


def test_probe_ruff_resolution_fails_closed_when_clean_environment_executable_is_missing(
    tmp_path: Path, monkeypatch
):
    python = tmp_path / "clean_env" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    monkeypatch.setattr(seal_probe_release.sys, "executable", str(python))
    with pytest.raises(seal_probe_release.ProbeSealError, match="beside target Python"):
        seal_probe_release.resolve_ruff_executable()
