from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image

from app.server import create_app


def png_bytes(size=(320, 384)) -> bytes:
    stream = io.BytesIO()
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    mask = Image.new("L", size, 0)
    pixels = mask.load()
    width, height = size
    left_center = width // 2 - 1

    # Exact bilateral nose-up planform. Every filled left pixel is mirrored
    # around the half-pixel centreline, while the fore/aft width profile is
    # deliberately non-symmetric so the authority orientation is unambiguous.
    y_start = int(height * 0.06)
    y_end = int(height * 0.94)
    span = y_end - y_start
    for y in range(y_start, y_end):
        t = (y - y_start) / max(1, span - 1)
        if t < 0.25:
            half = int(width * (0.025 + 0.38 * (t / 0.25)))
        elif t < 0.48:
            half = int(width * (0.405 + 0.035 * ((t - 0.25) / 0.23)))
        elif t < 0.70:
            half = int(width * (0.44 - 0.25 * ((t - 0.48) / 0.22)))
        else:
            half = int(width * (0.19 - 0.11 * ((t - 0.70) / 0.30)))
        half = max(6, min(left_center - 4, half))
        for x in range(left_center - half + 1, left_center + 1):
            pixels[x, y] = 255
            pixels[width - 1 - x, y] = 255

    image.paste((90, 110, 125, 255), mask=mask)
    image.save(stream, format="PNG")
    return stream.getvalue()


def perspective_beauty_bytes(size=(512, 512)) -> bytes:
    stream = io.BytesIO()
    image = Image.new('RGB', size, (230, 220, 202))
    pixels = image.load()
    # Deliberately diagonal, asymmetric perspective-like craft silhouette.
    for y in range(70, 440):
        center = 90 + int(0.72 * y)
        half = 18 + int(0.11 * (440 - y))
        for x in range(max(8, center - half), min(size[0] - 8, center + half)):
            shade = 35 + int(80 * (x / size[0]))
            pixels[x, y] = (shade, shade + 10, shade + 15)
    for y in range(190, 330):
        center = 90 + int(0.72 * y)
        for x in range(max(8, center - 120), min(size[0] - 8, center + 54)):
            pixels[x, y] = (50, 62, 68)
    image.save(stream, format='PNG')
    return stream.getvalue()


def make_test_root(tmp_path: Path) -> Path:
    root = tmp_path / 'package'
    (root / 'profiles').mkdir(parents=True)
    source_profiles = Path(__file__).resolve().parents[1] / 'profiles' / 'craft_profiles.json'
    (root / 'profiles' / 'craft_profiles.json').write_bytes(source_profiles.read_bytes())
    return root


def csrf_client(app):
    client = app.test_client()
    with client.session_transaction() as session:
        session['csrf_token'] = 'test-token'
    return client


def valid_job_form(**overrides):
    data = {
        'experiment': 'authority_mesh',
        'profileId': 'enemy_gunship',
        'assetId': 'enemy.test',
        'authority': (io.BytesIO(png_bytes()), 'authority.png'),
        'manualAuthorityCertified': 'on',
        'provider': 'Fixture',
        'providerVersion': '1.0',
        'license': 'internal-test',
        'retrievedDate': '2026-07-30',
        'bankDegrees': '18',
        'masterResolution': '384',
        'cameraPitchDegrees': '20',
        'forwardAxis': '+Y',
        'upAxis': '+Z',
    }
    data.update(overrides)
    return data


def test_endpoint_requires_csrf(tmp_path: Path):
    app = create_app(make_test_root(tmp_path), tmp_path / 'workspace')
    response = app.test_client().post('/api/jobs', data=valid_job_form(), content_type='multipart/form-data')
    assert response.status_code == 403


def test_manual_authority_requires_explicit_certification_before_job_allocation(tmp_path: Path):
    workspace = tmp_path / 'workspace'
    app = create_app(make_test_root(tmp_path), workspace)
    client = csrf_client(app)
    form = valid_job_form()
    del form['manualAuthorityCertified']

    response = client.post(
        '/api/jobs',
        data=form,
        headers={'X-SkyForge-CSRF': 'test-token'},
        content_type='multipart/form-data',
    )

    assert response.status_code == 422
    assert 'strict top-down authority' in response.get_json()['error']
    assert not [path for path in workspace.iterdir() if path.is_dir() and not path.name.startswith('_')]


def test_perspective_beauty_is_rejected_before_job_allocation(tmp_path: Path):
    workspace = tmp_path / 'workspace'
    app = create_app(make_test_root(tmp_path), workspace)
    client = csrf_client(app)

    response = client.post(
        '/api/jobs',
        data=valid_job_form(authority=(io.BytesIO(perspective_beauty_bytes()), 'beauty.png')),
        headers={'X-SkyForge-CSRF': 'test-token'},
        content_type='multipart/form-data',
    )

    assert response.status_code == 422
    payload = response.get_json()
    assert 'rejected before mesh generation' in payload['error']
    assert payload['authoritySuitability']['passed'] is False
    assert payload['authoritySuitability']['checks']['bilateralPlanform'] is False
    assert payload['authoritySuitability']['checks']['noseUpPlanformOrientation'] is False
    assert not [path for path in workspace.iterdir() if path.is_dir() and not path.name.startswith('_')]



def test_exact_user_reported_three_quarter_beauty_is_rejected_before_provider_or_job(
    tmp_path: Path, monkeypatch
):
    workspace = tmp_path / 'workspace'
    app = create_app(make_test_root(tmp_path), workspace)
    client = csrf_client(app)
    fixture = Path(__file__).resolve().parents[1] / 'samples' / 'rejected_three_quarter_beauty_mbs155.png'

    def provider_must_not_run(_provider_id):
        raise AssertionError('provider was resolved for an invalid authority')

    monkeypatch.setattr('app.server.resolve_provider', provider_must_not_run)
    response = client.post(
        '/api/jobs',
        data=valid_job_form(authority=(io.BytesIO(fixture.read_bytes()), fixture.name)),
        headers={'X-SkyForge-CSRF': 'test-token'},
        content_type='multipart/form-data',
    )

    assert response.status_code == 422
    payload = response.get_json()
    assert payload['ok'] is False
    assert payload['authoritySuitability']['passed'] is False
    codes = {item['code'] for item in payload['authoritySuitability']['failures']}
    assert {'perspective_or_asymmetric_planform', 'unstable_centerline', 'not_nose_up'} <= codes
    assert not [path for path in workspace.iterdir() if path.is_dir() and not path.name.startswith('_')]

def test_authority_validation_endpoint_reports_pass_without_allocating_job(tmp_path: Path):
    workspace = tmp_path / 'workspace'
    app = create_app(make_test_root(tmp_path), workspace)
    client = csrf_client(app)

    response = client.post(
        '/api/authority/validate',
        data={
            'profileId': 'enemy_gunship',
            'authority': (io.BytesIO(png_bytes()), 'authority.png'),
            'manualAuthorityCertified': 'on',
        },
        headers={'X-SkyForge-CSRF': 'test-token'},
        content_type='multipart/form-data',
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['passed'] is True
    assert payload['report']['metrics']['bilateralSilhouetteIoU'] == 1.0
    assert not [path for path in workspace.iterdir() if path.is_dir() and not path.name.startswith('_')]


def test_endpoint_queues_when_blender_is_available(tmp_path: Path, monkeypatch):
    root = make_test_root(tmp_path)
    workspace = tmp_path / 'workspace'
    blender = tmp_path / 'Blender'
    blender.write_text('fixture', encoding='utf-8')
    started = []
    monkeypatch.setattr('app.server.resolve_blender_path', lambda _root: blender)
    monkeypatch.setattr(
        'app.server.start_job_thread',
        lambda package_root, job, manifest, executable: started.append(
            (package_root, job.root, manifest, executable)
        ),
    )
    app = create_app(root, workspace)
    client = csrf_client(app)

    response = client.post(
        '/api/jobs',
        data=valid_job_form(),
        headers={'X-SkyForge-CSRF': 'test-token'},
        content_type='multipart/form-data',
    )

    assert response.status_code == 202
    payload = response.get_json()
    assert payload['status'] == 'queued'
    assert payload['warning'] is None
    assert len(started) == 1
    assert started[0][0] == root
    assert started[0][1] == workspace / payload['jobId']
    assert started[0][3] == blender


def test_endpoint_clamps_settings_and_returns_clear_unknown_profile_error(
    tmp_path: Path,
    monkeypatch,
):
    root = make_test_root(tmp_path)
    workspace = tmp_path / 'workspace'
    monkeypatch.setattr('app.server.resolve_blender_path', lambda _root: None)
    app = create_app(root, workspace)
    client = csrf_client(app)
    response = client.post(
        '/api/jobs',
        data=valid_job_form(masterResolution='99999', bankDegrees='-5'),
        headers={'X-SkyForge-CSRF': 'test-token'},
        content_type='multipart/form-data',
    )
    assert response.status_code == 201
    job_id = response.get_json()['jobId']
    manifest = json.loads((workspace / job_id / 'manifest.json').read_text())
    assert manifest['settings']['masterResolution'] == 512
    assert manifest['settings']['bankDegrees'] == 0
    assert manifest['settings']['canonicalOrthoScale'] > 8.8
    assert manifest['experiment']['id'] == 'authority_mesh'
    assert manifest['mesh']['origin'] == 'generated_from_authority'
    assert manifest['authority']['suitabilityReport'] == 'authority_suitability_report.json'
    suitability = json.loads((workspace / job_id / 'source' / 'authority_suitability_report.json').read_text())
    assert suitability['passed'] is True
    assert suitability['sourceKind'] == 'manual_upload'
    assert manifest['settings']['forwardAxis'] == '+Y'
    assert manifest['settings']['upAxis'] == '+Z'
    report = json.loads((workspace / job_id / 'source' / manifest['mesh']['generationReport']).read_text())
    assert report['gateResults']['passed'] is True
    assert report['source']['authorityPixelsConsumed'] is True

    response = client.post(
        '/api/jobs',
        data=valid_job_form(profileId='unknown'),
        headers={'X-SkyForge-CSRF': 'test-token'},
        content_type='multipart/form-data',
    )
    assert response.status_code == 400
    assert 'Unknown craft profile' in response.get_json()['error']


def test_download_traversal_is_rejected(tmp_path: Path):
    app = create_app(make_test_root(tmp_path), tmp_path / 'workspace')
    client = app.test_client()
    assert client.get('/api/jobs/%2e%2e/download').status_code == 404
    assert client.get('/api/jobs/../download').status_code == 404


def test_provider_mesh_mode_requires_mesh_without_workspace_residue(tmp_path: Path):
    workspace = tmp_path / 'workspace'
    app = create_app(make_test_root(tmp_path), workspace)
    client = csrf_client(app)
    response = client.post(
        '/api/jobs',
        data=valid_job_form(experiment='provider_mesh'),
        headers={'X-SkyForge-CSRF': 'test-token'},
        content_type='multipart/form-data',
    )
    assert response.status_code == 422
    assert 'Provider mesh is required' in response.get_json()['error']
    assert not [path for path in workspace.iterdir() if path.is_dir() and not path.name.startswith('_')]


def test_authority_mesh_mode_rejects_uploaded_mesh_without_workspace_residue(tmp_path: Path):
    workspace = tmp_path / 'workspace'
    app = create_app(make_test_root(tmp_path), workspace)
    client = csrf_client(app)
    response = client.post(
        '/api/jobs',
        data=valid_job_form(mesh=(io.BytesIO(b'v 0 0 0\n'), 'manual.obj')),
        headers={'X-SkyForge-CSRF': 'test-token'},
        content_type='multipart/form-data',
    )
    assert response.status_code == 422
    assert 'generates its own mesh' in response.get_json()['error']
    assert not [path for path in workspace.iterdir() if path.is_dir() and not path.name.startswith('_')]


def test_authority_mode_forces_verified_axes(tmp_path: Path, monkeypatch):
    root = make_test_root(tmp_path)
    workspace = tmp_path / 'workspace'
    monkeypatch.setattr('app.server.resolve_blender_path', lambda _root: None)
    app = create_app(root, workspace)
    client = csrf_client(app)
    response = client.post(
        '/api/jobs',
        data=valid_job_form(forwardAxis='+Z', upAxis='-Y'),
        headers={'X-SkyForge-CSRF': 'test-token'},
        content_type='multipart/form-data',
    )
    assert response.status_code == 201
    job_id = response.get_json()['jobId']
    manifest = json.loads((workspace / job_id / 'manifest.json').read_text())
    assert manifest['settings']['forwardAxis'] == '+Y'
    assert manifest['settings']['upAxis'] == '+Z'


def test_settings_route_saves_key_via_keychain_and_not_config(tmp_path: Path, monkeypatch):
    root = make_test_root(tmp_path)
    workspace = tmp_path / 'workspace'
    app = create_app(root, workspace)
    client = csrf_client(app)
    saved_keys = []
    monkeypatch.setattr('app.server.save_keychain_key', lambda key: saved_keys.append(key))
    monkeypatch.setattr('app.settings_store.read_keychain_key', lambda: 'sk-saved-test')

    response = client.post(
        '/api/settings',
        json={
            'openai': {
                'apiKey': 'sk-saved-test',
                'removeApiKey': False,
                'stages': {
                    'beautyExplore': {'model': 'gpt-image-2', 'quality': 'low', 'size': '1536x1024', 'candidateCount': 2},
                    'beautyRefine': {'model': 'gpt-image-2', 'quality': 'medium', 'size': '1536x1024', 'candidateCount': 1},
                    'authorityDraft': {'model': 'gpt-image-2', 'quality': 'low', 'size': '1024x1024', 'candidateCount': 2},
                    'authorityFinal': {'model': 'gpt-image-2', 'quality': 'low', 'size': '1024x1024', 'candidateCount': 1},
                },
                'budget': {'perRequestUsdMax': 0.05, 'perAssetUsdMax': 0.50, 'perSessionUsdMax': 2.00, 'confirmationThresholdUsd': 0.02},
            },
            'blender': {'path': '/Applications/Blender.app/Contents/MacOS/Blender'},
        },
        headers={'X-SkyForge-CSRF': 'test-token'},
    )
    assert response.status_code == 200
    assert saved_keys == ['sk-saved-test']
    config_text = (root / 'config.json').read_text(encoding='utf-8')
    assert 'sk-saved-test' not in config_text
    assert 'apiKey' not in config_text
    payload_text = json.dumps(response.get_json())
    assert 'sk-saved-test' not in payload_text


def test_openai_connection_route_accepts_unsaved_ui_key(tmp_path: Path, monkeypatch):
    app = create_app(make_test_root(tmp_path), tmp_path / 'workspace')
    client = csrf_client(app)
    observed = []

    def fake_test(key):
        observed.append(key)
        return {'ok': True, 'message': 'connected'}

    monkeypatch.setattr('app.server.test_openai_connection', fake_test)
    response = client.post(
        '/api/settings/test-openai',
        json={'apiKey': 'sk-unsaved-test'},
        headers={'X-SkyForge-CSRF': 'test-token'},
    )
    assert response.status_code == 200
    assert observed == ['sk-unsaved-test']
    assert response.get_json()['message'] == 'connected'


def test_browser_payloads_do_not_disclose_absolute_paths(tmp_path: Path):
    root = make_test_root(tmp_path)
    workspace = tmp_path / 'private-workspace'
    (root / 'config.json').write_text(json.dumps({'blenderPath': '/private/Applications/Blender'}))
    app = create_app(root, workspace)
    client = csrf_client(app)
    health = json.dumps(client.get('/api/health').get_json())
    settings = json.dumps(client.get('/api/settings').get_json())
    rejected = client.post(
        '/api/jobs',
        data=valid_job_form(mesh=(io.BytesIO(b'v 0 0 0\n'), 'manual.obj')),
        headers={'X-SkyForge-CSRF': 'test-token'},
        content_type='multipart/form-data',
    )
    combined = health + settings + json.dumps(rejected.get_json())
    assert str(root) not in combined
    assert str(workspace) not in combined
    assert '/private/Applications/Blender' not in combined
    assert 'jobPath' not in combined
    assert 'preparationLog' not in combined


def test_rejected_concept_validation_allocates_no_run_or_ledger(tmp_path: Path, monkeypatch):
    root = make_test_root(tmp_path)
    (root / 'config.json').write_text(json.dumps({'openai': {}}))
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    workspace = tmp_path / 'workspace'
    app = create_app(root, workspace)
    client = csrf_client(app)
    called = []
    monkeypatch.setattr('app.server.generate_beauty_candidates', lambda *_args, **_kwargs: called.append(True))
    response = client.post(
        '/api/concepts/beauty',
        data={'profileId': 'enemy_gunship', 'assetId': 'enemy.test', 'userPrompt': ''},
        headers={'X-SkyForge-CSRF': 'test-token'},
    )
    assert response.status_code == 400
    assert called == []
    concept_root = workspace / '_concepts'
    assert not [path for path in concept_root.iterdir() if path.is_dir() and path.name != '_cache']
    assert not (concept_root / 'spend_ledger.json').exists()
