from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from app.openai_client import GeneratedImage, ImageGenerationResponse, load_openai_settings
from app.server import create_app
from tests.test_server import csrf_client, make_test_root, png_bytes, valid_job_form


def test_openai_settings_ignore_legacy_plaintext_and_use_environment(tmp_path: Path, monkeypatch):
    root = make_test_root(tmp_path)
    (root / 'config.json').write_text(json.dumps({'openai': {'apiKey': 'sk-legacy-config', 'imageModel': 'gpt-image-1'}}))
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    settings = load_openai_settings(root)
    assert settings.configured is True
    assert settings.api_key == 'sk-test'
    assert settings.stage('beautyExplore').model == 'gpt-image-2'
    assert settings.stage('beautyExplore').quality == 'low'


def test_beauty_and_authority_routes_can_feed_mesh_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = make_test_root(tmp_path)
    (root / 'config.json').write_text(json.dumps({'openai': {}}))
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    monkeypatch.setattr('app.server.resolve_blender_path', lambda _root: None)
    workspace = tmp_path / 'workspace'
    app = create_app(root, workspace)
    client = csrf_client(app)

    def fake_beauty(*_args, **_kwargs):
        return ImageGenerationResponse(
            images=[GeneratedImage(bytes_data=png_bytes((256, 256)), mime_type='image/png', source='b64_json')],
            usage={'input_tokens': 10, 'output_tokens': 20, 'input_tokens_details': {'text_tokens': 10, 'image_tokens': 0}},
            request_id='req-test',
        )

    def fake_authority(*_args, **_kwargs):
        return ImageGenerationResponse(
            images=[GeneratedImage(bytes_data=png_bytes((256, 256)), mime_type='image/png', source='b64_json')],
            usage={'input_tokens': 10, 'output_tokens': 20, 'input_tokens_details': {'text_tokens': 10, 'image_tokens': 0}},
            request_id='req-test',
        )

    monkeypatch.setattr('app.server.generate_beauty_candidates', fake_beauty)
    monkeypatch.setattr('app.server.generate_authority_candidates', fake_authority)

    beauty_response = client.post(
        '/api/concepts/beauty',
        data={'profileId': 'enemy_gunship', 'assetId': 'enemy.test', 'userPrompt': 'heavy military gunship'},
        headers={'X-SkyForge-CSRF': 'test-token'},
    )
    assert beauty_response.status_code == 200
    beauty_payload = beauty_response.get_json()
    assert beauty_payload['ok'] is True
    beauty_filename = beauty_payload['images'][0]['filename']
    assert beauty_payload['metadata']['openai']['quality'] == 'low'
    assert beauty_payload['metadata']['openai']['model'] == 'gpt-image-2'

    authority_response = client.post(
        '/api/concepts/authority',
        data={
            'profileId': 'enemy_gunship',
            'assetId': 'enemy.test',
            'beautyRunId': beauty_payload['runId'],
            'beautyFilename': beauty_filename,
        },
        headers={'X-SkyForge-CSRF': 'test-token'},
    )
    assert authority_response.status_code == 200
    authority_payload = authority_response.get_json()
    assert authority_payload['ok'] is True
    authority_filename = authority_payload['images'][0]['filename']
    assert authority_payload['metadata']['openai']['quality'] == 'low'
    assert authority_payload['metadata']['openai']['estimate']['lowerBound'] is True

    form = valid_job_form(authority=(io.BytesIO(b''), 'unused.png'))
    del form['authority']
    form['authorityGeneratedPath'] = f"{authority_payload['runId']}/images/{authority_filename}"
    form['beautyRunId'] = beauty_payload['runId']
    form['beautyFilename'] = beauty_filename
    form['authorityRunId'] = authority_payload['runId']
    form['authorityFilename'] = authority_filename
    form['conceptPrompt'] = 'heavy military gunship'

    job_response = client.post(
        '/api/jobs',
        data=form,
        headers={'X-SkyForge-CSRF': 'test-token'},
        content_type='multipart/form-data',
    )
    assert job_response.status_code == 201
    job_id = job_response.get_json()['jobId']
    manifest = json.loads((workspace / job_id / 'manifest.json').read_text())
    assert manifest['conceptWorkflow']['beautyRunId'] == beauty_payload['runId']
    assert manifest['conceptWorkflow']['authorityRunId'] == authority_payload['runId']
    assert manifest['mesh']['generatedFromAuthority'] is True
    report = json.loads(
        (workspace / job_id / 'source' / 'authority_suitability_report.json').read_text()
    )
    assert report['passed'] is True
    assert report['sourceKind'] == 'governed_generated'
    assert report['lineage']['verified'] is True
    assert report['lineage']['runId'] == authority_payload['runId']
    assert report['lineage']['sourceBeauty']['runId'] == beauty_payload['runId']


def test_governed_authority_lineage_tamper_is_rejected_before_job_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = make_test_root(tmp_path)
    workspace = tmp_path / 'workspace'
    concepts = workspace / '_concepts'
    beauty_root = concepts / 'beauty-run'
    authority_root = concepts / 'authority-run'
    (beauty_root / 'images').mkdir(parents=True)
    (authority_root / 'images').mkdir(parents=True)
    beauty_path = beauty_root / 'images' / 'beauty.png'
    authority_path = authority_root / 'images' / 'authority.png'
    beauty_path.write_bytes(png_bytes((256, 256)))
    authority_path.write_bytes(png_bytes((256, 256)))

    import hashlib

    beauty_sha = hashlib.sha256(beauty_path.read_bytes()).hexdigest()
    authority_sha = hashlib.sha256(authority_path.read_bytes()).hexdigest()
    (beauty_root / 'metadata.json').write_text(
        json.dumps(
            {
                'schemaVersion': 'skyforge.concept-run.v2',
                'runType': 'beauty',
                'stage': 'beautyExplore',
                'runId': beauty_root.name,
                'profileId': 'enemy_gunship',
                'assetId': 'enemy.test',
                'images': [
                    {
                        'filename': beauty_path.name,
                        'path': f'images/{beauty_path.name}',
                        'sha256': beauty_sha,
                    }
                ],
            }
        ),
        encoding='utf-8',
    )
    (authority_root / 'metadata.json').write_text(
        json.dumps(
            {
                'schemaVersion': 'skyforge.concept-run.v2',
                'runType': 'authority',
                'stage': 'authorityFinal',
                'runId': authority_root.name,
                'profileId': 'enemy_gunship',
                'assetId': 'enemy.test',
                'sourceBeauty': {
                    'runId': beauty_root.name,
                    'filename': beauty_path.name,
                    'sha256': beauty_sha,
                },
                'images': [
                    {
                        'filename': authority_path.name,
                        'path': f'images/{authority_path.name}',
                        'sha256': authority_sha,
                    }
                ],
            }
        ),
        encoding='utf-8',
    )

    # Tamper the approved beauty after authority generation. The authority image
    # remains geometrically valid, so only full lineage re-verification can catch it.
    beauty_path.write_bytes(beauty_path.read_bytes() + b'tamper')

    def provider_must_not_run(_provider_id):
        raise AssertionError('provider was resolved after governed-lineage tamper')

    monkeypatch.setattr('app.server.resolve_provider', provider_must_not_run)
    app = create_app(root, workspace)
    client = csrf_client(app)
    form = valid_job_form(authority=(io.BytesIO(b''), 'unused.png'))
    del form['authority']
    form['authorityGeneratedPath'] = 'authority-run/images/authority.png'
    response = client.post(
        '/api/jobs',
        data=form,
        headers={'X-SkyForge-CSRF': 'test-token'},
        content_type='multipart/form-data',
    )
    assert response.status_code == 400
    assert 'beauty lineage record does not match' in response.get_json()['error']
    assert not [
        path
        for path in workspace.iterdir()
        if path.is_dir() and not path.name.startswith('_')
    ]


def test_governed_authority_duplicate_image_record_is_rejected_before_job_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = make_test_root(tmp_path)
    workspace = tmp_path / 'workspace'
    concepts = workspace / '_concepts'
    beauty_root = concepts / 'beauty-run'
    authority_root = concepts / 'authority-run'
    (beauty_root / 'images').mkdir(parents=True)
    (authority_root / 'images').mkdir(parents=True)
    beauty_path = beauty_root / 'images' / 'beauty.png'
    authority_path = authority_root / 'images' / 'authority.png'
    beauty_path.write_bytes(png_bytes((256, 256)))
    authority_path.write_bytes(png_bytes((256, 256)))

    import hashlib

    beauty_sha = hashlib.sha256(beauty_path.read_bytes()).hexdigest()
    authority_sha = hashlib.sha256(authority_path.read_bytes()).hexdigest()
    beauty_record = {
        'filename': beauty_path.name,
        'path': f'images/{beauty_path.name}',
        'sha256': beauty_sha,
    }
    authority_record = {
        'filename': authority_path.name,
        'path': f'images/{authority_path.name}',
        'sha256': authority_sha,
    }
    (beauty_root / 'metadata.json').write_text(
        json.dumps(
            {
                'schemaVersion': 'skyforge.concept-run.v2',
                'runType': 'beauty',
                'stage': 'beautyExplore',
                'runId': beauty_root.name,
                'profileId': 'enemy_gunship',
                'assetId': 'enemy.test',
                'images': [beauty_record],
            }
        ),
        encoding='utf-8',
    )
    (authority_root / 'metadata.json').write_text(
        json.dumps(
            {
                'schemaVersion': 'skyforge.concept-run.v2',
                'runType': 'authority',
                'stage': 'authorityFinal',
                'runId': authority_root.name,
                'profileId': 'enemy_gunship',
                'assetId': 'enemy.test',
                'sourceBeauty': {
                    'runId': beauty_root.name,
                    'filename': beauty_path.name,
                    'sha256': beauty_sha,
                },
                'images': [authority_record, dict(authority_record)],
            }
        ),
        encoding='utf-8',
    )

    monkeypatch.setattr(
        'app.server.resolve_provider',
        lambda _provider_id: (_ for _ in ()).throw(
            AssertionError('provider was resolved after duplicate governed record')
        ),
    )
    app = create_app(root, workspace)
    client = csrf_client(app)
    form = valid_job_form(authority=(io.BytesIO(b''), 'unused.png'))
    del form['authority']
    form['authorityGeneratedPath'] = 'authority-run/images/authority.png'
    response = client.post(
        '/api/jobs',
        data=form,
        headers={'X-SkyForge-CSRF': 'test-token'},
        content_type='multipart/form-data',
    )
    assert response.status_code == 400
    assert 'exactly one governed concept-run record' in response.get_json()['error']
    assert not [
        path
        for path in workspace.iterdir()
        if path.is_dir() and not path.name.startswith('_')
    ]
