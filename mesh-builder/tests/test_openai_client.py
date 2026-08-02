from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from app.openai_client import (
    AmbiguousOpenAIError,
    OpenAIImageError,
    OpenAISettings,
    StageSettings,
    _parse_response,
    generate_beauty_candidates,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.headers = {}

    def json(self):
        return self._payload


def settings(secret: str) -> OpenAISettings:
    stage = StageSettings('gpt-image-2', 'low', '1536x1024', 2)
    return OpenAISettings(
        api_key=secret,
        stages={'beautyExplore': stage},
        budget={},
        configured=True,
    )


def test_provider_error_that_echoes_api_key_is_redacted(monkeypatch):
    secret = 'sk-super-secret'
    monkeypatch.setattr(
        requests,
        'post',
        lambda *_args, **_kwargs: FakeResponse(400, {'error': {'message': f'bad Authorization Bearer {secret}'}}),
    )
    with pytest.raises(OpenAIImageError) as captured:
        generate_beauty_candidates(
            settings(secret),
            prompt='safe prompt',
            model='gpt-image-2',
            quality='low',
            size='1536x1024',
            count=2,
        )
    assert secret not in str(captured.value)
    assert '[REDACTED]' in str(captured.value)


def test_source_and_examples_contain_no_plaintext_api_key():
    root = Path(__file__).resolve().parents[1]
    for path in root.rglob('*'):
        if (
            not path.is_file()
            or '.venv' in path.parts
            or 'workspace' in path.parts
            or '__pycache__' in path.parts
            or path.suffix == '.pyc'
        ):
            continue
        if path.suffix.lower() in {'.png', '.glb', '.obj', '.mtl', '.zip'}:
            continue
        text = path.read_text(encoding='utf-8', errors='ignore')
        live_key_prefix = 'sk-' + 'live-'
        authorization_prefix = 'Authorization: Bearer ' + 'sk-'
        assert live_key_prefix not in text
        assert authorization_prefix not in text
    example = json.loads((root / 'config.json.example').read_text(encoding='utf-8'))
    assert 'apiKey' not in json.dumps(example)


def test_success_without_images_is_classified_possibly_charged(monkeypatch):
    monkeypatch.setattr(
        requests,
        'post',
        lambda *_args, **_kwargs: FakeResponse(200, {'data': [], 'usage': {'output_tokens': 1}}),
    )
    with pytest.raises(AmbiguousOpenAIError, match='may have been charged'):
        generate_beauty_candidates(
            settings('sk-secret'),
            prompt='safe prompt',
            model='gpt-image-2',
            quality='low',
            size='1536x1024',
            count=2,
        )


def test_provider_5xx_is_classified_possibly_charged():
    response = FakeResponse(status_code=500, payload={'error': {'message': 'internal failure'}})
    with pytest.raises(AmbiguousOpenAIError, match='may have occurred after billing'):
        _parse_response(response, 'empty', secret='sk-test')
