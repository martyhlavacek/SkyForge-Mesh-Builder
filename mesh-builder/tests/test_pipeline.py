from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app.authority_mesh import generate_authority_mesh
from app.pipeline import (
    GENERATION_REQUIRED_OUTPUTS,
    OPAQUE_BG_DISTANCE_THRESHOLD,
    POSTPROCESS_REQUIRED_OUTPUTS,
    RENDER_REQUIRED_OUTPUTS,
    _alpha_mask,
    create_job,
    job_paths,
    package_job,
    postprocess_outputs,
    safe_name,
    save_upload,
    sha256_file,
    verify_generation_contract,
    verify_output_group,
    verify_required_outputs,
    write_job_status,
    write_manifest,
)
from common.mesh_math import (
    CANONICAL_ORTHO_MARGIN,
    CANONICAL_ORTHO_REQUIRED_MARGIN,
    canonical_frame_calibration,
    canonical_ortho_scale,
    clamp_float,
    clamp_int,
    is_valid_job_id,
    projected_pixel_span,
    target_span,
    validate_orientation,
)


class FakeUpload:
    def __init__(self, payload: bytes, filename: str):
        self.payload = payload
        self.filename = filename

    def save(self, destination):
        Path(destination).write_bytes(self.payload)


def png_bytes(size=(64, 64)) -> bytes:
    stream = io.BytesIO()
    Image.new('RGBA', size, (0, 0, 0, 0)).save(stream, format='PNG')
    return stream.getvalue()


def measurement_settings() -> dict:
    return {
        'authorityMaskMethod': 'alpha_threshold_else_corner_difference',
        'authorityMaskThreshold': OPAQUE_BG_DISTANCE_THRESHOLD,
    }


def test_safe_name_removes_path_components_and_separators():
    cleaned = safe_name('../nested\\bad name.glb')
    assert '/' not in cleaned and '\\' not in cleaned
    assert cleaned == 'bad_name.glb'


def test_hash(tmp_path: Path):
    path = tmp_path / 'x'
    path.write_bytes(b'abc')
    assert sha256_file(path) == 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'


def test_job_creation_and_id_shape(tmp_path: Path):
    job = create_job(tmp_path, {'id': 'enemy_gunship'}, 'enemy.test')
    assert (job.root / 'job.json').exists()
    assert is_valid_job_id(job.root.name)


def test_job_path_containment_rejects_traversal(tmp_path: Path):
    assert job_paths(tmp_path, '..') is None
    assert job_paths(tmp_path, '../anything') is None


def test_image_content_validation(tmp_path: Path):
    valid = FakeUpload(png_bytes(), 'authority.png')
    saved = save_upload(valid, tmp_path, {'.png'}, validate_image=True)
    assert saved.exists()
    invalid = FakeUpload(b'not a png', 'fake.png')
    with pytest.raises(ValueError, match='valid supported image'):
        save_upload(invalid, tmp_path, {'.png'}, validate_image=True)


def test_numeric_clamping_orientation_and_canonical_frame():
    assert clamp_int('99999', 256, 512, 'masterResolution') == 512
    assert clamp_float('-2', 0, 35, 'bankDegrees') == 0
    assert validate_orientation('+Y', '+Z') == ('+Y', '+Z')
    with pytest.raises(ValueError):
        validate_orientation('+Y', '-Y')
    assert target_span(1.15) == pytest.approx(6.325)
    assert canonical_ortho_scale(1.15) == pytest.approx(8.855)
    calibration = canonical_frame_calibration(1.15)
    assert calibration['chosenMargin'] == CANONICAL_ORTHO_MARGIN
    assert calibration['measuredRequiredMargin'] == CANONICAL_ORTHO_REQUIRED_MARGIN
    assert calibration['fixtureHeadroomFraction'] > 0.05




def test_canonical_frame_calibration_is_bound_to_profile_digest():
    with pytest.raises(RuntimeError, match='not bound'):
        canonical_frame_calibration(1.15, 5, 'wrong-digest')
    with pytest.raises(RuntimeError, match='profile count'):
        canonical_frame_calibration(1.15, 4)

def test_pinned_ortho_preserves_profile_pixel_scale():
    scales = {
        'bomber': 1.15,
        'gunship': 1.0,
        'fighter': 0.82,
        'interceptor': 0.72,
        'drone': 0.55,
    }
    ortho = canonical_ortho_scale(max(scales.values()))
    pixels = {
        name: projected_pixel_span(target_span(scale), ortho, 96)
        for name, scale in scales.items()
    }
    assert pixels['bomber'] > pixels['gunship'] > pixels['fighter'] > pixels['interceptor'] > pixels['drone']
    assert pixels['bomber'] / pixels['drone'] == pytest.approx(1.15 / 0.55)


def test_manifest_declares_provenance_scale_observed_settings_and_outputs(tmp_path: Path):
    job = create_job(tmp_path, {'id': 'enemy_gunship'}, 'enemy.test')
    authority = job.source / 'authority.png'
    authority.write_bytes(png_bytes())
    profile = {'id': 'enemy_gunship', 'scale': 1.0}
    settings = {
        'bankDegrees': 18,
        'masterResolution': 384,
        'cameraPitchDegrees': 20,
        'forwardAxis': '+Y',
        'upAxis': '+Z',
        'profileScale': 1.0,
        'canonicalOrthoScale': canonical_ortho_scale(1.15),
        'canonicalFrameCalibration': canonical_frame_calibration(1.15),
        'renderSamples': 64,
        'destruction': {'requested': False, 'implemented': False},
    }
    generated_dir = job.source / 'generated'
    generated_dir.mkdir()
    mesh = generated_dir / 'authority_generated_mesh.obj'
    mesh.write_text('v 0 0 0\n')
    report = generated_dir / 'authority_mesh_generation_report.json'
    report.write_text('{}')
    manifest_path = write_manifest(
        job,
        profile,
        'enemy.test',
        authority,
        mesh,
        'generated_from_authority',
        report,
        'authority_mesh',
        'Authority Mesh — local deterministic generation',
        settings,
        {
            'provider': 'SkyForge Authority Two-Sided Field',
            'providerVersion': '0.6.0',
            'license': 'internal-test',
            'approvedForDistribution': False,
        },
    )
    payload = json.loads(manifest_path.read_text())
    assert payload['profile']['scale'] == 1.0
    assert payload['settings']['canonicalOrthoScale'] == pytest.approx(8.855)
    assert payload['experiment']['id'] == 'authority_mesh'
    assert payload['mesh']['origin'] == 'generated_from_authority'
    assert payload['mesh']['generatedFromAuthority'] is True
    assert payload['generator']['provider'] == 'SkyForge Authority Two-Sided Field'
    assert set(payload['requiredConsumedSettings']) == set(settings)
    assert set(GENERATION_REQUIRED_OUTPUTS + RENDER_REQUIRED_OUTPUTS + POSTPROCESS_REQUIRED_OUTPUTS) == set(payload['requiredOutputs'])


def test_render_contract_rejects_missing_before_postprocessing(tmp_path: Path):
    job = create_job(tmp_path, {'id': 'enemy_gunship'}, 'enemy.test')
    with pytest.raises(RuntimeError, match='Blender render output contract failed: missing=preview_neutral_master.png'):
        verify_output_group(job, ['preview_neutral_master.png'], 'Blender render')


def test_output_contract_rejects_missing_files(tmp_path: Path):
    job = create_job(tmp_path, {'id': 'enemy_gunship'}, 'enemy.test')
    manifest = job.root / 'manifest.json'
    manifest.write_text(json.dumps({
        'requiredOutputs': ['asset.json'],
        'requiredConsumedSettings': ['masterResolution'],
    }))
    with pytest.raises(RuntimeError, match='missing=asset.json'):
        verify_required_outputs(job, manifest)


def test_output_contract_accepts_measured_complete_files(tmp_path: Path):
    job = create_job(tmp_path, {'id': 'enemy_gunship'}, 'enemy.test')
    (job.output / 'asset.json').write_text(json.dumps({'measurements': {'silhouetteIoU': {'value': 0.95}}}))
    (job.output / 'run_report.json').write_text(json.dumps({
        'consumedSettings': ['masterResolution'],
        'unconsumedSettings': [],
        'neutralPoseRestoredBeforeExport': True,
        'cleanExportContainsReviewRig': False,
        'meshMatricesIdentityAtExport': True,
        'meshWorldBoundsPreservedDuringBake': True,
        'normalizationBakedIntoMeshData': True,
        'rootTransformMustBeHonoured': False,
    }))
    manifest = job.root / 'manifest.json'
    manifest.write_text(json.dumps({
        'requiredOutputs': ['asset.json', 'run_report.json'],
        'requiredConsumedSettings': ['masterResolution'],
        'identityAcceptance': {
            'blenderSilhouetteIoUMin': 0.90,
            'generatedMeshMustUseAuthority': True,
        },
        'mesh': {'origin': 'generated_from_authority'},
    }))
    result = verify_required_outputs(job, manifest)
    assert result['requiredOutputCount'] == 2
    assert result['neutralPoseRestoredBeforeExport'] is True
    assert result['meshMatricesIdentityAtExport'] is True
    assert result['normalizationBakedIntoMeshData'] is True


def test_package_requires_verified_rendered_status(tmp_path: Path):
    workspace = tmp_path / 'workspace'
    job = create_job(workspace, {'id': 'enemy_gunship'}, 'enemy.test')
    with pytest.raises(RuntimeError, match='verified rendered'):
        package_job(job, workspace / '_archives')
    (job.output / 'asset.json').write_text('{}')
    write_job_status(job, 'rendered')
    archive = package_job(job, workspace / '_archives')
    assert archive.exists()
    with zipfile.ZipFile(archive) as package:
        assert 'output/asset.json' in package.namelist()


def test_opaque_authority_mask_is_vectorized_and_visible():
    image = Image.new('RGB', (32, 32), (20, 20, 20))
    for x in range(8, 24):
        for y in range(6, 26):
            image.putpixel((x, y), (110, 130, 150))
    mask = _alpha_mask(image)
    assert mask.getbbox() == (8, 6, 24, 26)


def test_postprocess_generates_native_outputs_contact_sheets_and_measurements(tmp_path: Path):
    job = create_job(tmp_path, {'id': 'enemy_gunship'}, 'enemy.test')
    authority = Image.new('RGBA', (128, 128), (0, 0, 0, 0))
    for x in range(28, 100):
        for y in range(18, 110):
            if abs(x - 64) < 22 or (45 < y < 90 and abs(x - 64) < 36):
                authority.putpixel((x, y), (80, 120, 150, 255))
    authority.save(job.source / 'authority.png')

    for name in (
        'preview_neutral_master.png',
        'preview_bank_left_master.png',
        'preview_bank_right_master.png',
        'silhouette_top_master.png',
    ):
        render = Image.new('RGBA', (384, 384), (0, 0, 0, 0))
        for x in range(90, 294):
            for y in range(54, 330):
                if abs(x - 192) < 66 or (138 < y < 270 and abs(x - 192) < 108):
                    render.putpixel((x, y), (80, 120, 150, 255))
        render.save(job.output / name)

    (job.output / 'asset.json').write_text(json.dumps({
        'schemaVersion': 'skyforge.asset.sidecar.v3.0',
        'anchors': None,
    }))
    manifest = job.root / 'manifest.json'
    manifest.write_text(json.dumps({
        'authority': {'path': 'authority.png'},
        'mesh': {'origin': 'generated_from_authority'},
        'experiment': {'id': 'authority_mesh', 'label': 'Authority Mesh — local deterministic generation'},
        'measurementSettings': measurement_settings(),
        'distributionGate': {'approved': False, 'warning': 'test'},
    }))

    postprocess_outputs(job, manifest)
    with Image.open(job.output / 'preview_neutral_96_lanczos.png') as preview:
        assert preview.size == (96, 96)
    assert (job.output / 'review_sheet_neutral_64.png').exists()
    assert (job.output / 'authority_mask.png').exists()
    assert (job.output / 'silhouette_comparison.png').exists()
    asset = json.loads((job.output / 'asset.json').read_text())
    silhouette = asset['measurements']['silhouetteIoU']
    assert 0 <= silhouette['value'] <= 1
    assert 0 < silhouette['achievableCeilingAtRenderResolution'] <= 1
    assert 'theoreticalCeiling' not in silhouette
    assert asset['pivot']['source'] == 'neutral_96_alpha_centroid'
    assert asset['collision']['source'] == 'neutral_96_alpha_bounds'
    review = json.loads((job.output / 'review.json').read_text())
    assert review['experiment']['id'] == 'authority_mesh'


def test_generated_authority_mesh_contract_reconciles_hashes_and_evidence(tmp_path: Path):
    package_root = Path(__file__).resolve().parents[1]
    authority_source = package_root / 'samples' / 'approved_gunship_authority.png'
    job = create_job(tmp_path, {'id': 'enemy_gunship'}, 'enemy.authority')
    authority = job.source / authority_source.name
    authority.write_bytes(authority_source.read_bytes())
    generated = generate_authority_mesh(authority, job.source / 'generated')
    for evidence in (*generated.preview_paths, generated.report_path):
        (job.output / evidence.name).write_bytes(evidence.read_bytes())
    profile = {'id': 'enemy_gunship', 'scale': 1.0}
    settings = {
        'bankDegrees': 18, 'masterResolution': 384, 'cameraPitchDegrees': 20,
        'forwardAxis': '+Y', 'upAxis': '+Z',
        'profileScale': 1.0, 'canonicalOrthoScale': canonical_ortho_scale(1.15),
        'canonicalFrameCalibration': canonical_frame_calibration(1.15),
        'renderSamples': 64,
        'destruction': {'requested': False, 'implemented': False},
    }
    manifest = write_manifest(
        job, profile, 'enemy.authority', authority, generated.mesh_path,
        'generated_from_authority', generated.report_path, 'authority_mesh',
        'Authority Mesh — local deterministic generation', settings,
        {'provider': 'SkyForge Authority Two-Sided Field', 'providerVersion': '0.6.0',
         'license': 'internal', 'approvedForDistribution': False},
    )
    evidence = verify_generation_contract(job, manifest)
    assert evidence['authorityGenerated'] is True
    assert evidence['meshOrigin'] == 'generated_from_authority'
    assert evidence['meshSha256'] == generated.report['mesh']['sha256']


def test_generation_contract_fails_if_mesh_is_modified_after_report(tmp_path: Path):
    package_root = Path(__file__).resolve().parents[1]
    authority_source = package_root / 'samples' / 'approved_gunship_authority.png'
    job = create_job(tmp_path, {'id': 'enemy_gunship'}, 'enemy.authority')
    authority = job.source / authority_source.name
    authority.write_bytes(authority_source.read_bytes())
    generated = generate_authority_mesh(authority, job.source / 'generated')
    for evidence in (*generated.preview_paths, generated.report_path):
        (job.output / evidence.name).write_bytes(evidence.read_bytes())
    manifest = write_manifest(
        job, {'id': 'enemy_gunship', 'scale': 1.0}, 'enemy.authority', authority,
        generated.mesh_path, 'generated_from_authority', generated.report_path,
        'authority_mesh', 'Authority Mesh — local deterministic generation',
        {'masterResolution': 384},
        {'provider': 'SkyForge Authority Two-Sided Field', 'providerVersion': '0.6.0',
         'license': 'internal', 'approvedForDistribution': False},
    )
    generated.mesh_path.write_bytes(generated.mesh_path.read_bytes() + b'tampered')
    with pytest.raises(RuntimeError, match='checksum mismatch'):
        verify_generation_contract(job, manifest)
