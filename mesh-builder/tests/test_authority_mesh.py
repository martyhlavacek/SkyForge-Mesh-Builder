from __future__ import annotations

import hashlib
import json
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image

from app.authority_mesh import (
    ACCEPTANCE_GATES,
    GENERATOR_ID,
    _build_mesh,
    _distance_inside,
    _edge_audit,
    _gate_results,
    _select_mesh_grid_size,
    _two_sided_fields,
    generate_authority_mesh,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = PACKAGE_ROOT / 'samples' / 'approved_gunship_authority.png'


def independent_obj_audit(path: Path) -> dict[str, int]:
    vertices = 0
    faces: list[tuple[int, int, int]] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('v '):
            vertices += 1
        elif line.startswith('f '):
            indices = tuple(int(token.split('/')[0]) for token in line.split()[1:])
            assert len(indices) == 3
            faces.append(indices)
    edges: Counter[tuple[int, int]] = Counter()
    for a, b, c in faces:
        for first, second in ((a, b), (b, c), (c, a)):
            edges[tuple(sorted((first, second)))] += 1
    return {
        'vertexCount': vertices,
        'triangleCount': len(faces),
        'boundaryEdgeCount': sum(value == 1 for value in edges.values()),
        'nonManifoldEdgeCount': sum(value > 2 for value in edges.values()),
    }


def test_real_approved_gunship_generates_watertight_identity_bound_mesh(tmp_path: Path):
    result = generate_authority_mesh(AUTHORITY, tmp_path)
    report = json.loads(result.report_path.read_text(encoding='utf-8'))
    audit = independent_obj_audit(result.obj_path)

    assert report['generator']['id'] == GENERATOR_ID
    assert report['source']['authorityPixelsConsumed'] is True
    assert report['source']['authoritySha256'] == hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
    assert report['gateResults']['passed'] is True
    assert report['identityMetricSource'] == 'target_mesh_and_emulated_blender_gltf_import_top_projection'
    assert report['mesh']['glbReloadWatertight'] is True
    assert report['mesh']['glbReloadWindingConsistent'] is True
    assert report['identityMetrics']['silhouetteIoU'] >= ACCEPTANCE_GATES['silhouetteIoUMin']
    assert report['identityMetrics']['aspectError'] <= ACCEPTANCE_GATES['aspectErrorMax']
    assert report['identityMetrics']['centroidDistance'] <= ACCEPTANCE_GATES['centroidDistanceMax']
    assert report['identityMetrics']['widthProfileMAE'] <= ACCEPTANCE_GATES['widthProfileMAEMax']
    coordinate = report['mesh']['coordinateContract']
    assert coordinate['encoding'] == 'target_xyz_to_gltf_x_z_neg_y'
    assert coordinate['blenderImportBoundsDelta'] <= ACCEPTANCE_GATES['blenderImportBoundsDeltaMax']
    assert coordinate['blenderImportHeightToPlanformRatio'] <= ACCEPTANCE_GATES['heightToPlanformRatioMax']
    assert report['blenderImportIdentityMetrics']['silhouetteIoU'] >= ACCEPTANCE_GATES['blenderImportSilhouetteIoUMin']
    assert audit['vertexCount'] == report['mesh']['vertexCount']
    assert audit['triangleCount'] == report['mesh']['triangleCount']
    assert audit['boundaryEdgeCount'] == 0
    assert audit['nonManifoldEdgeCount'] == 0
    assert result.obj_path.stat().st_size > 500_000
    assert result.mesh_path.suffix == '.glb'
    assert result.mesh_path.stat().st_size > 500_000
    for preview in result.preview_paths:
        assert preview.is_file() and preview.stat().st_size > 400


def test_generation_is_deterministic_for_same_authority(tmp_path: Path):
    first = generate_authority_mesh(AUTHORITY, tmp_path / 'first')
    second = generate_authority_mesh(AUTHORITY, tmp_path / 'second')
    assert first.report['mesh']['sha256'] == second.report['mesh']['sha256']
    assert first.report['identityMetrics'] == second.report['identityMetrics']


def test_blank_authority_is_rejected_before_mesh_creation(tmp_path: Path):
    blank = tmp_path / 'blank.png'
    Image.new('RGBA', (128, 128), (0, 0, 0, 0)).save(blank)
    with pytest.raises(ValueError, match='no usable foreground|no foreground'):
        generate_authority_mesh(blank, tmp_path / 'output')


def test_small_disconnected_noise_is_not_exported_as_extra_mesh_component(tmp_path: Path):
    image = Image.new('RGBA', (128, 128), (0, 0, 0, 0))
    for y in range(20, 110):
        for x in range(42, 86):
            image.putpixel((x, y), (90, 110, 130, 255))
    image.putpixel((3, 3), (255, 255, 255, 255))
    source = tmp_path / 'noise.png'
    image.save(source)
    result = generate_authority_mesh(source, tmp_path / 'output')
    assert result.report['mesh']['componentCount'] == 1
    assert result.report['mesh']['watertightByEdgeIncidence'] is True


def test_contact_sheet_visibly_contains_four_panels(tmp_path: Path):
    result = generate_authority_mesh(AUTHORITY, tmp_path)
    contact = next(path for path in result.preview_paths if path.name == 'authority_mesh_generation_contact_sheet.png')
    with Image.open(contact) as image:
        assert image.size == (1024, 284)
        # Each image panel contains non-background colour variation.
        for panel in range(4):
            crop = image.crop((panel * 256, 28, (panel + 1) * 256, 284)).convert('RGB')
            assert len(crop.getcolors(maxcolors=1_000_000) or []) > 50


def test_user_test_gunship_survives_gltf_to_blender_coordinate_contract(tmp_path: Path):
    authority = PACKAGE_ROOT / 'samples' / 'user_test_gunship_authority.png'
    result = generate_authority_mesh(authority, tmp_path)
    report = result.report
    coordinate = report['mesh']['coordinateContract']
    assert report['gateResults']['passed'] is True
    assert report['blenderImportIdentityMetrics']['silhouetteIoU'] >= 0.94
    assert coordinate['blenderImportBoundsDelta'] <= 1e-5
    assert coordinate['blenderImportHeightToPlanformRatio'] < 0.20
    assert (tmp_path / 'authority_mesh_blender_import_silhouette.png').is_file()


def test_opaque_light_background_interceptor_authority_avoids_colour_distance_overflow(tmp_path: Path):
    authority = PACKAGE_ROOT / 'samples' / 'interceptor_openai_authority_regression.png'
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter('always')
        result = generate_authority_mesh(authority, tmp_path)
    assert not [warning for warning in captured if 'invalid value encountered' in str(warning.message)]
    report = result.report
    assert report['source']['maskMethod'] == 'corner_colour_distance_28'
    assert report['gateResults']['passed'] is True
    assert report['mesh']['boundaryEdgeCount'] == 0
    assert report['mesh']['nonManifoldEdgeCount'] == 0
    assert report['mesh']['glbReloadWatertight'] is True
    assert report['identityMetrics']['silhouetteIoU'] >= 0.94
    assert report['blenderImportIdentityMetrics']['silhouetteIoU'] >= 0.94


def test_v060_two_sided_field_replaces_flat_belly_and_vertical_extrusion(tmp_path: Path):
    authority = PACKAGE_ROOT / 'samples' / 'v060_field_gunship_authority.png'
    result = generate_authority_mesh(authority, tmp_path)
    geometry = result.report['geometryMetrics']
    assert geometry['representation'] == 'two_sided_planform_field_with_edge_convergence'
    assert geometry['albedoInfluencesGeometry'] is True
    assert geometry['albedoGeometryInfluenceScope'] == 'foreground_mask_derivation_only'
    assert geometry['workGridSize'] == 384
    assert geometry['meshGridSize'] == 256
    assert geometry['flatBellySurfaceFraction'] <= ACCEPTANCE_GATES['flatBellySurfaceFractionMax']
    assert geometry['verticalWallSurfaceFraction'] <= ACCEPTANCE_GATES['verticalWallSurfaceFractionMax']
    assert (
        geometry['combinedConstructionArtifactFraction']
        <= ACCEPTANCE_GATES['combinedConstructionArtifactFractionMax']
    )
    assert (
        geometry['sectionThickness']['tipToRootRatio']
        <= ACCEPTANCE_GATES['tipToRootThicknessRatioMax']
    )
    assert geometry['genus'] == 0
    assert result.report['source']['holeFilter']['filledHoleCount'] > 0
    independence = geometry['sectionThickness']['upperLowerIndependence']
    assert independence['relativeResidual'] >= ACCEPTANCE_GATES['lowerFieldRelativeResidualMin']


def test_component_and_edge_audits_are_measured_from_reloaded_glb(tmp_path: Path):
    result = generate_authority_mesh(AUTHORITY, tmp_path)
    mesh = result.report['mesh']
    assert mesh['componentCountSource'] == 'independent_reloaded_glb_split'
    assert mesh['componentCount'] == 1
    assert mesh['sourceReloadEdgeAuditAgreement'] is True
    assert mesh['sourceEdgeAudit'] == mesh['reloadedGlbEdgeAudit']
    assert mesh['boundaryEdgeCount'] == 0
    assert mesh['nonManifoldEdgeCount'] == 0


def test_geometry_is_invariant_to_rgba_albedo_when_alpha_planform_is_identical(tmp_path: Path):
    first = Image.new('RGBA', (96, 128), (0, 0, 0, 0))
    second = Image.new('RGBA', (96, 128), (0, 0, 0, 0))
    for y in range(12, 116):
        half_width = 12 + int(20 * (1.0 - abs(y - 64) / 64))
        for x in range(48 - half_width, 48 + half_width + 1):
            first.putpixel((x, y), (255, 80, 10, 255))
            second.putpixel((x, y), (15, 40, 220, 255))
    first_path = tmp_path / 'orange.png'
    second_path = tmp_path / 'blue.png'
    first.save(first_path)
    second.save(second_path)
    first_result = generate_authority_mesh(first_path, tmp_path / 'first')
    second_result = generate_authority_mesh(second_path, tmp_path / 'second')

    def geometry_lines(path: Path) -> list[str]:
        return [line for line in path.read_text(encoding='utf-8').splitlines() if line.startswith(('v ', 'f '))]

    assert geometry_lines(first_result.obj_path) == geometry_lines(second_result.obj_path)
    assert first_result.report['geometryMetrics'] == second_result.report['geometryMetrics']


def test_exact_distance_transform_matches_brute_force_on_small_mask():
    mask = np.zeros((7, 9), dtype=bool)
    mask[1:6, 2:8] = True
    mask[3, 5] = False
    measured = _distance_inside(mask)
    background = np.argwhere(~mask)
    expected = np.zeros_like(measured)
    for y, x in np.argwhere(mask):
        expected[y, x] = min(float(np.hypot(y - by, x - bx)) for by, bx in background)
    assert np.allclose(measured, expected, atol=1e-6)


def _passing_gate_payload() -> tuple[dict[str, float], dict[str, float], dict[str, int], dict[str, object]]:
    identity = {
        'silhouetteIoU': 1.0,
        'aspectError': 0.0,
        'centroidDistance': 0.0,
        'widthProfileMAE': 0.0,
    }
    audit = {'uniqueEdgeCount': 3, 'boundaryEdgeCount': 0, 'nonManifoldEdgeCount': 0}
    geometry: dict[str, object] = {
        'flatBellySurfaceFraction': 0.0,
        'verticalWallSurfaceFraction': 0.0,
        'combinedConstructionArtifactFraction': 0.0,
        'genus': 0.0,
        'sectionThickness': {
            'tipToRootRatio': 0.2,
            'upperLowerIndependence': {'relativeResidual': 0.2},
        },
    }
    return identity, identity.copy(), audit, geometry


def test_source_reload_edge_audit_disagreement_fails_gate():
    metrics, blender_metrics, reload_audit, geometry = _passing_gate_payload()
    gates = _gate_results(
        metrics,
        blender_metrics,
        reload_audit,
        triangle_count=10_000,
        component_count=1,
        blender_bounds_delta=0.0,
        height_to_planform_ratio=0.1,
        geometry_metrics=geometry,
        edge_audits_agree=False,
    )
    assert gates['checks']['sourceReloadEdgeAuditAgreement'] is False
    assert gates['passed'] is False


def test_component_count_is_provably_read_from_reloaded_glb(tmp_path: Path, monkeypatch):
    real_load = trimesh.load

    class ReloadProxy:
        def __init__(self, mesh: trimesh.Trimesh):
            self._mesh = mesh

        def __getattr__(self, name: str):
            return getattr(self._mesh, name)

        def split(self, only_watertight: bool = False):
            del only_watertight
            return [self._mesh, self._mesh]

        def copy(self):
            return self._mesh.copy()

    def controlled_load(path, *args, **kwargs):
        loaded = real_load(path, *args, **kwargs)
        if Path(path).suffix == '.glb':
            return ReloadProxy(loaded)
        return loaded

    monkeypatch.setattr('app.authority_mesh.trimesh.load', controlled_load)
    with pytest.raises(RuntimeError, match='components'):
        generate_authority_mesh(AUTHORITY, tmp_path)
    report = json.loads((tmp_path / 'authority_mesh_generation_report.json').read_text(encoding='utf-8'))
    assert report['mesh']['componentCount'] == 2
    assert report['mesh']['componentCountSource'] == 'independent_reloaded_glb_split'
    assert report['gateResults']['checks']['components'] is False


def test_small_enclosed_mask_holes_are_filled_and_genus_is_zero(tmp_path: Path):
    authority = PACKAGE_ROOT / 'samples' / 'v060_field_gunship_authority.png'
    result = generate_authority_mesh(authority, tmp_path)
    source = result.report['source']
    geometry = result.report['geometryMetrics']
    assert source['holeFilter']['detectedHoleCount'] >= 1
    assert source['holeFilter']['filledHoleCount'] == source['holeFilter']['detectedHoleCount']
    assert source['holeFilter']['retainedHoleCount'] == 0
    assert geometry['eulerNumber'] == 2
    assert geometry['genus'] == 0
    assert result.report['gateResults']['checks']['genus'] is True


def test_large_intentional_hole_is_not_silently_filled_and_fails_genus_gate(tmp_path: Path):
    image = Image.new('RGBA', (128, 128), (0, 0, 0, 0))
    for y in range(12, 116):
        for x in range(20, 108):
            image.putpixel((x, y), (90, 110, 130, 255))
    for y in range(48, 80):
        for x in range(48, 80):
            image.putpixel((x, y), (0, 0, 0, 0))
    source = tmp_path / 'intentional_hole.png'
    image.save(source)
    with pytest.raises(RuntimeError, match='genus'):
        generate_authority_mesh(source, tmp_path / 'output')
    report = json.loads(
        (tmp_path / 'output' / 'authority_mesh_generation_report.json').read_text(encoding='utf-8')
    )
    assert report['source']['holeFilter']['retainedHoleCount'] == 1
    assert report['geometryMetrics']['genus'] == 1
    assert report['gateResults']['checks']['genus'] is False


def test_opaque_mask_reports_colour_based_planform_dependency(tmp_path: Path):
    authority = PACKAGE_ROOT / 'samples' / 'interceptor_openai_authority_regression.png'
    result = generate_authority_mesh(authority, tmp_path)
    assert result.report['source']['albedoGeometryInfluence'] is True
    assert result.report['source']['albedoGeometryInfluenceScope'] == 'foreground_mask_derivation_only'
    assert result.report['geometryMetrics']['albedoInfluencesGeometry'] is True


def test_alpha_mask_reports_no_albedo_geometry_influence(tmp_path: Path):
    result = generate_authority_mesh(AUTHORITY, tmp_path)
    assert result.report['source']['maskMethod'] == 'alpha_threshold_16'
    assert result.report['source']['albedoGeometryInfluence'] is False
    assert result.report['geometryMetrics']['albedoInfluencesGeometry'] is False


def test_adaptive_export_grid_keeps_wide_planform_within_triangle_budget():
    mask = np.zeros((384, 384), dtype=bool)
    mask[8:376, 8:376] = True
    top, bottom, centre, _ = _two_sided_fields(mask)
    size, mesh_mask, mesh_top, mesh_bottom, mesh_centre, projected = _select_mesh_grid_size(
        mask, top, bottom, centre
    )
    _, _, faces, _ = _build_mesh(mesh_mask, mesh_top, mesh_bottom, mesh_centre)
    assert size < 256
    assert len(faces) <= ACCEPTANCE_GATES['triangleCountMax']
    assert len(faces) == projected


def test_edge_audit_distinguishes_closed_open_and_non_manifold_topology():
    closed = _edge_audit([(1, 2, 3), (1, 4, 2), (2, 4, 3), (1, 3, 4)])
    opened = _edge_audit([(1, 2, 3)])
    finned = _edge_audit([(1, 2, 3), (2, 1, 4), (1, 2, 5)])
    assert closed['boundaryEdgeCount'] == 0
    assert closed['nonManifoldEdgeCount'] == 0
    assert opened['boundaryEdgeCount'] == 3
    assert finned['nonManifoldEdgeCount'] == 1


def test_geometry_metrics_receive_independently_reloaded_target_frame_mesh(tmp_path: Path, monkeypatch):
    import app.authority_mesh as authority_mesh_module

    observed: dict[str, object] = {}
    real_convert = authority_mesh_module._to_blender_import_coordinates
    real_metrics = authority_mesh_module._geometry_metrics

    def tagged_convert(mesh):
        converted = real_convert(mesh)
        observed['converted'] = converted
        return converted

    def guarded_metrics(mesh, *args, **kwargs):
        assert mesh is observed['converted']
        observed['measured'] = mesh
        return real_metrics(mesh, *args, **kwargs)

    monkeypatch.setattr(authority_mesh_module, '_to_blender_import_coordinates', tagged_convert)
    monkeypatch.setattr(authority_mesh_module, '_geometry_metrics', guarded_metrics)
    result = generate_authority_mesh(AUTHORITY, tmp_path)
    assert observed['measured'] is observed['converted']
    assert result.report['geometryMetrics']['geometryMetricsSource'] == (
        'independent_reloaded_glb_in_target_frame'
    )


def test_two_sided_fields_preserve_deliberate_planform_asymmetry_without_image_centre_mirroring():
    mask = np.zeros((96, 96), dtype=bool)
    mask[10:86, 30:66] = True
    mask[28:66, 18:30] = True
    mask[42:58, 66:82] = True
    top, bottom, centre, summary = _two_sided_fields(mask)
    del centre

    for field in (top, bottom):
        values = field[mask]
        mirrored = np.fliplr(field)
        relative_mirror_residual = float(
            np.linalg.norm((field - mirrored)[mask])
            / max(float(np.linalg.norm(values)), 1e-12)
        )
        assert relative_mirror_residual >= 0.20

    independence = summary['upperLowerIndependence']
    assert independence['gateInterpretation'] == 'not_a_rescaled_copy'
    assert independence['binnedFunctionRelativeResidual'] > 0.0
    assert independence['binnedFunctionRelativeResidual'] <= independence['relativeResidual']
