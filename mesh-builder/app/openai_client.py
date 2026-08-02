from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .settings_store import load_api_key, migrated_budget_settings, migrated_stage_settings, read_config

OPENAI_GENERATIONS_URL = 'https://api.openai.com/v1/images/generations'
OPENAI_EDITS_URL = 'https://api.openai.com/v1/images/edits'


@dataclass(frozen=True)
class StageSettings:
    model: str
    quality: str
    size: str
    candidate_count: int


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str | None
    stages: dict[str, StageSettings]
    budget: dict[str, float]
    configured: bool

    def stage(self, name: str) -> StageSettings:
        try:
            return self.stages[name]
        except KeyError as exc:
            raise OpenAIImageError(f'Unknown governed image stage: {name}') from exc

    @property
    def image_model(self) -> str:
        return self.stage('beautyExplore').model

    @property
    def beauty_size(self) -> str:
        return self.stage('beautyExplore').size

    @property
    def authority_size(self) -> str:
        return self.stage('authorityDraft').size

    @property
    def beauty_count_default(self) -> int:
        return self.stage('beautyExplore').candidate_count

    @property
    def authority_count_default(self) -> int:
        return self.stage('authorityDraft').candidate_count


@dataclass(frozen=True)
class GeneratedImage:
    bytes_data: bytes
    mime_type: str
    source: str


@dataclass(frozen=True)
class ImageGenerationResponse:
    images: list[GeneratedImage]
    usage: dict[str, Any] | None
    request_id: str | None
    attempt_count: int = 1


class OpenAIImageError(RuntimeError):
    pass


class AmbiguousOpenAIError(OpenAIImageError):
    """The provider might have completed and billed a timed-out request."""


def load_openai_settings(package_root: Path) -> OpenAISettings:
    config = read_config(package_root)
    openai_config = config.get('openai', {}) if isinstance(config.get('openai'), dict) else {}
    api_key, _source = load_api_key(package_root)
    raw_stages = migrated_stage_settings(openai_config)
    stages = {
        key: StageSettings(
            model=str(value['model']),
            quality=str(value['quality']),
            size=str(value['size']),
            candidate_count=int(value['candidateCount']),
        )
        for key, value in raw_stages.items()
    }
    return OpenAISettings(
        api_key=api_key,
        stages=stages,
        budget=migrated_budget_settings(openai_config),
        configured=bool(api_key),
    )


def _headers(settings: OpenAISettings) -> dict[str, str]:
    if not settings.api_key:
        raise OpenAIImageError('OpenAI API key is not configured. Save it in Settings first.')
    return {'Authorization': f'Bearer {settings.api_key}'}


def _safe_provider_message(response: requests.Response, secret: str | None = None) -> str:
    try:
        payload = response.json()
        error = payload.get('error') if isinstance(payload, dict) else None
        message = error.get('message') if isinstance(error, dict) else None
    except ValueError:
        message = None
    safe = str(message or f'OpenAI image request failed with HTTP {response.status_code}')[:240]
    return safe.replace(secret, '[REDACTED]') if secret else safe


def _decode_item(item: dict[str, Any]) -> GeneratedImage:
    if not isinstance(item, dict):
        raise AmbiguousOpenAIError(
            'OpenAI returned an unreadable successful image item; the request may have been charged'
        )
    if item.get('b64_json'):
        try:
            data = base64.b64decode(item['b64_json'], validate=True)
        except (ValueError, TypeError) as exc:
            raise AmbiguousOpenAIError(
                'OpenAI returned invalid image bytes after success; the request may have been charged'
            ) from exc
        return GeneratedImage(bytes_data=data, mime_type='image/png', source='b64_json')
    raise AmbiguousOpenAIError(
        'OpenAI successful response omitted embedded image bytes; the request may have been charged'
    )


def _parse_response(
    response: requests.Response, empty_message: str, *, secret: str | None
) -> ImageGenerationResponse:
    if response.status_code >= 500:
        raise AmbiguousOpenAIError(
            f'{_safe_provider_message(response, secret)}; provider failure may have occurred after billing'
        )
    if response.status_code >= 400:
        raise OpenAIImageError(_safe_provider_message(response, secret))
    try:
        payload = response.json()
    except ValueError as exc:
        raise AmbiguousOpenAIError(
            'OpenAI returned an unreadable successful response; the request may have been charged'
        ) from exc
    data = payload.get('data')
    if not isinstance(data, list) or not data:
        raise AmbiguousOpenAIError(f'{empty_message}; the request may have been charged')
    usage = payload.get('usage') if isinstance(payload.get('usage'), dict) else None
    request_id = response.headers.get('x-request-id') or payload.get('id')
    return ImageGenerationResponse(
        images=[_decode_item(item) for item in data],
        usage=usage,
        request_id=str(request_id) if request_id else None,
    )


def generate_beauty_candidates(
    settings: OpenAISettings,
    *,
    prompt: str,
    model: str,
    quality: str,
    size: str,
    count: int,
) -> ImageGenerationResponse:
    payload = {
        'model': model,
        'prompt': prompt,
        'size': size,
        'n': count,
        'quality': quality,
        'output_format': 'png',
    }
    try:
        response = requests.post(OPENAI_GENERATIONS_URL, headers=_headers(settings), json=payload, timeout=240)
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise AmbiguousOpenAIError('OpenAI request timed out or lost connection; it may have been charged') from exc
    except requests.RequestException as exc:
        raise OpenAIImageError(f'OpenAI transport failed before a response was received: {type(exc).__name__}') from exc
    return _parse_response(
        response, 'OpenAI returned no generated beauty images', secret=settings.api_key
    )


def generate_authority_candidates(
    settings: OpenAISettings,
    *,
    prompt: str,
    reference_image: Path,
    model: str,
    quality: str,
    size: str,
    count: int,
) -> ImageGenerationResponse:
    mime_type = mimetypes.guess_type(reference_image.name)[0] or 'image/png'
    with reference_image.open('rb') as stream:
        files = {'image': (reference_image.name, stream, mime_type)}
        data = {
            'model': model,
            'prompt': prompt,
            'size': size,
            'n': str(count),
            'quality': quality,
            'background': 'auto',
            'output_format': 'png',
        }
        try:
            response = requests.post(
                OPENAI_EDITS_URL,
                headers=_headers(settings),
                data=data,
                files=files,
                timeout=240,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise AmbiguousOpenAIError('OpenAI authority edit timed out or lost connection; it may have been charged') from exc
        except requests.RequestException as exc:
            raise OpenAIImageError(
                f'OpenAI authority transport failed before a response was received: {type(exc).__name__}'
            ) from exc
    return _parse_response(
        response, 'OpenAI returned no generated authority images', secret=settings.api_key
    )


def test_openai_connection(api_key: str) -> dict[str, str | bool]:
    value = api_key.strip()
    if not value:
        raise OpenAIImageError('OpenAI API key is required for the connection test')
    try:
        response = requests.get(
            'https://api.openai.com/v1/models',
            headers={'Authorization': f'Bearer {value}'},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise OpenAIImageError(f'OpenAI connection failed: {type(exc).__name__}') from exc
    if response.status_code != 200:
        raise OpenAIImageError(_safe_provider_message(response, value))
    return {'ok': True, 'message': 'OpenAI API connection succeeded'}
