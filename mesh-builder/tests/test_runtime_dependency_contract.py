from __future__ import annotations

import importlib.metadata
import os
import subprocess
import sys
from pathlib import Path

import networkx
import trimesh

from common.source_binding import PRODUCER_SCOPE, write_binding
from scripts import run_live_blender_preflight, seal_release

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_networkx_graph_engine_is_declared_pinned_and_operational():
    requirements = (PACKAGE_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert "networkx==3.6.1" in requirements
    assert seal_release.REQUIRED_DISTRIBUTIONS["networkx"] == "3.6.1"
    assert importlib.metadata.version("networkx") == "3.6.1"
    assert networkx.__version__ == "3.6.1"

    mesh = trimesh.creation.box()
    components = mesh.split(only_watertight=False)
    assert len(components) == 1


def test_live_preflight_uses_registered_profiles_and_frozen_forward_baselines():
    profiles = {
        item["id"]: item
        for item in __import__("json").loads(
            (PACKAGE_ROOT / "profiles" / "craft_profiles.json").read_text(encoding="utf-8")
        )
    }
    assert profiles["enemy_gunship"]["scale"] == 1.0
    assert profiles["enemy_interceptor"]["scale"] == 0.72
    assert run_live_blender_preflight.FIXTURES == (
        ("approved_gunship", "approved_gunship_authority.png", "enemy_gunship"),
        ("field_gunship", "v060_field_gunship_authority.png", "enemy_gunship"),
        ("interceptor", "interceptor_openai_authority_regression.png", "enemy_interceptor"),
    )
    assert run_live_blender_preflight.BLENDER_SILHOUETTE_IOU_MIN == 0.94
    assert run_live_blender_preflight.EXPECTED_LIVE_BLENDER_IOU == {
        "approved_gunship": 0.975865,
        "field_gunship": 0.947415,
        "interceptor": 0.952496,
    }
    assert run_live_blender_preflight.LIVE_BASELINE_TOLERANCE == 1e-6
    assert set(run_live_blender_preflight.EXPECTED_MESH_SHA256) == set(
        run_live_blender_preflight.EXPECTED_LIVE_BLENDER_IOU
    )


def test_live_preflight_direct_file_entrypoint_imports_project_packages(tmp_path: Path):
    script = PACKAGE_ROOT / "scripts" / "run_live_blender_preflight.py"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "ModuleNotFoundError" not in completed.stderr
    assert "--output" in completed.stdout


def test_live_preflight_exact_source_binding_detects_changed_file(tmp_path: Path):
    (tmp_path / "app").mkdir()
    source = tmp_path / "app" / "sample.py"
    source.write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("example==1.0.0\n", encoding="utf-8")
    write_binding(tmp_path, PRODUCER_SCOPE)
    verified = run_live_blender_preflight.verify_source_binding(tmp_path)
    assert verified["verified"] is True

    source.write_text("value = 2\n", encoding="utf-8")
    try:
        run_live_blender_preflight.verify_source_binding(tmp_path)
    except RuntimeError as exc:
        assert "Exact reviewed source binding failed" in str(exc)
    else:
        raise AssertionError("source-binding verification accepted a changed source file")


def test_live_preflight_probe_command_preserves_virtual_environment_symlink(tmp_path: Path):
    probe_root = tmp_path / "probe"
    (probe_root / "scripts").mkdir(parents=True)
    (probe_root / "scripts/run_import_probe.py").write_text("pass\n", encoding="utf-8")
    (probe_root / "IMPORT_PROBE_SOURCE_BINDING.json").write_text("{}\n", encoding="utf-8")
    environment_root = tmp_path / "probe_clean_env"
    interpreter = environment_root / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(sys.executable)
    command = run_live_blender_preflight._probe_command(
        PACKAGE_ROOT,
        probe_root,
        interpreter,
    )
    assert command[0] == str(interpreter.absolute())
    assert Path(command[0]).is_symlink()
