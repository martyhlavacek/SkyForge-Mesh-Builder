from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image

from app.authority_mesh import generate_authority_mesh
from app.geometry_v2 import GENERATOR_ID, GENERATOR_VERSION, generate_multivolume_experiment
from app.geometry_v2.evidence import sha256_file, verify_manifest
from app.geometry_v2.recipes import UnsupportedGeometryProfile, load_recipe

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
GUNSHIP = PACKAGE_ROOT / "samples" / "approved_gunship_authority.png"
INTERCEPTOR = PACKAGE_ROOT / "samples" / "interceptor_openai_authority_regression.png"
BASELINE_COMMIT = "d38dd5d1638eae0942929a4ed568edb048220894"


@pytest.fixture(scope="module")
def experiment_results(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("geometry_v2")
    gunship = generate_multivolume_experiment(GUNSHIP, "enemy_gunship", root / "gunship")
    interceptor = generate_multivolume_experiment(INTERCEPTOR, "enemy_interceptor", root / "interceptor")
    return gunship, interceptor


def _added_components(result) -> list[dict]:
    return [component for component in result.report["components"] if component["name"] != "base_shell"]


def test_recipe_schema_and_unsupported_profile_fail_closed():
    gunship, digest = load_recipe("enemy_gunship")
    assert gunship["recipeVersion"] == 1
    assert len(digest) == 64
    with pytest.raises(UnsupportedGeometryProfile, match="No unique geometry recipe"):
        load_recipe("enemy_bomber")


def test_identical_inputs_have_deterministic_byte_and_semantic_outputs(experiment_results, tmp_path: Path):
    first, _ = experiment_results
    second = generate_multivolume_experiment(GUNSHIP, "enemy_gunship", tmp_path / "repeat")
    assert sha256_file(first.mesh_path) == sha256_file(second.mesh_path)
    assert sha256_file(first.obj_path) == sha256_file(second.obj_path)
    assert first.report == second.report


def test_legacy_generator_is_unchanged_and_all_original_gates_pass(experiment_results, tmp_path: Path):
    gunship, _ = experiment_results
    direct = generate_authority_mesh(GUNSHIP, tmp_path / "direct")
    assert direct.report["gateResults"]["passed"] is True
    assert direct.report["mesh"]["sha256"] == gunship.report["legacyBase"]["meshSha256"]
    assert hashlib.sha256(direct.report_path.read_bytes()).hexdigest() == gunship.report["legacyBase"]["reportSha256"]


def test_albedo_changes_with_identical_alpha_do_not_change_geometry(tmp_path: Path):
    with Image.open(GUNSHIP) as source:
        original = source.convert("RGBA")
    changed = original.copy()
    pixels = np.asarray(changed).copy()
    pixels[:, :, :3] = np.where(pixels[:, :, 3:4] > 0, np.array([20, 90, 210]), pixels[:, :, :3])
    changed = Image.fromarray(pixels.astype(np.uint8), "RGBA")
    changed_path = tmp_path / "changed_albedo.png"
    changed.save(changed_path)
    original_result = generate_multivolume_experiment(GUNSHIP, "enemy_gunship", tmp_path / "original")
    changed_result = generate_multivolume_experiment(changed_path, "enemy_gunship", tmp_path / "changed")
    original_records = _added_components(original_result)
    changed_records = _added_components(changed_result)
    for first, second in zip(original_records, changed_records, strict=True):
        for field in ("name", "shape", "transform", "dimensionsLengthWidthHeight", "vertexCount", "triangleCount", "volume"):
            assert first[field] == second[field]
    assert original_result.report["albedoGeometryInfluence"] is False
    assert changed_result.report["albedoGeometryInfluence"] is False


def test_expected_semantic_component_registries(experiment_results):
    gunship, interceptor = experiment_results
    assert {component["name"] for component in gunship.report["components"]} == {
        "base_shell", "fuselage", "cockpit_left", "cockpit_right", "engine_left", "engine_right",
        "weapon_left", "weapon_right", "belly",
    }
    assert {component["name"] for component in interceptor.report["components"]} == {
        "base_shell", "fuselage", "cockpit", "engine_left", "engine_right", "weapon_left", "weapon_right",
    }


def test_individual_components_are_watertight_and_edge_audited(experiment_results):
    for result in experiment_results:
        for component in _added_components(result):
            assert component["watertight"] is True
            assert component["windingConsistent"] is True
            assert component["boundaryEdgeCount"] == 0
            assert component["nonManifoldEdgeCount"] == 0


def test_glb_reload_preserves_component_registry_and_coordinate_bounds(experiment_results):
    for result in experiment_results:
        reload = result.report["assemblyReload"]
        assert reload["componentCountBefore"] == reload["componentCountAfter"]
        assert set(reload["geometryNamesAfter"]) == {component["name"] for component in result.report["components"]}
        assert reload["coordinateBoundsDelta"] <= 1e-5
        scene = trimesh.load(result.mesh_path, force="scene", process=False)
        assert len(scene.geometry) == reload["componentCountAfter"]


def test_no_components_float_or_hide_inside_another(experiment_results):
    for result in experiment_results:
        assert result.report["whollyContainedComponents"] == []
        assert all(component["attachmentPenetration"] > 0 for component in _added_components(result))
        assert result.report["gateResults"]["checks"]["positiveAttachmentPenetration"] is True


def test_authority_exterior_spill_and_identity_gates(experiment_results):
    for result in experiment_results:
        metrics = result.report["identityMetrics"]
        assert metrics["silhouetteIoU"] >= 0.94
        assert metrics["authorityExteriorSpillFraction"] <= 0.005
        assert metrics["widthProfileMAE"] <= 0.045


def test_engines_and_weapons_have_real_three_dimensional_extents(experiment_results):
    for result in experiment_results:
        selected = [
            component for component in _added_components(result)
            if component["name"].startswith(("engine_", "weapon_"))
        ]
        assert len(selected) == 4
        for component in selected:
            assert min(component["dimensionsLengthWidthHeight"]) > 0.02
            assert component["volume"] > 0
            assert component["triangleCount"] >= component["minimumTriangles"]


def test_distinct_semantic_height_bands(experiment_results):
    for result in experiment_results:
        bands = result.report["semanticHeightBands"]
        assert bands["bandCount"] >= 3
        assert bands["ordered"] is True
        assert bands["minimumAdjacentSeparation"] > 0


def test_experiment_has_no_network_provider_or_integration_imports():
    sources = list((PACKAGE_ROOT / "app" / "geometry_v2").glob("*.py"))
    sources.append(PACKAGE_ROOT / "scripts" / "run_multivolume_geometry_experiment.py")
    forbidden = ("requests", "urllib", "socket", "app.server", "app.pipeline", "app.providers", "app.vmp")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    assert not any(token in combined for token in forbidden)
    assert os.environ.get("SKYFORGE_PAID_PROVIDER_AUTHORIZED") is None


def test_import_probe_tree_has_no_changes():
    completed = subprocess.run(
        ["git", "diff", "--quiet", BASELINE_COMMIT, "--", "import-probe"],
        cwd=PACKAGE_ROOT.parent,
        check=False,
    )
    assert completed.returncode == 0


def test_evidence_manifest_verifies_every_generated_file(experiment_results):
    for result in experiment_results:
        assert verify_manifest(result.output_dir, result.manifest_path) is True
        records = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        assert result.mesh_path.name in records
        assert result.report_path.name in records
        assert result.registry_path.name in records
        assert all(path.relative_to(result.output_dir).as_posix() in records for path in result.preview_paths)


def test_report_governance_flags_and_limitations_are_fail_closed(experiment_results):
    for result in experiment_results:
        assert result.report["generator"] == {"id": GENERATOR_ID, "version": GENERATOR_VERSION}
        assert result.report["gateResults"]["passed"] is True
        assert result.report["vmpExportAuthorized"] is False
        assert result.report["userTestingAuthorized"] is False
        assert result.report["paidProviderWorkAuthorized"] is False
        assert any("MBS-150" in limitation for limitation in result.report["limitations"])
