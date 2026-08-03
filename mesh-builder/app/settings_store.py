from __future__ import annotations

import getpass
import json
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .macos_keychain import KeychainUserCancelled, MacOSKeychain

KEYCHAIN_SERVICE = 'com.skyforge.mesh-builder.openai'
DEFAULT_BLENDER_PATH = '/Applications/Blender.app/Contents/MacOS/Blender'
ALLOWED_IMAGE_SIZES = {'1024x1024', '1536x1024', '1024x1536'}
ALLOWED_QUALITIES = {'low', 'medium', 'high'}
STAGE_KEYS = ('beautyExplore', 'beautyRefine', 'authorityDraft', 'authorityFinal')
DEFAULT_STAGE_SETTINGS: dict[str, dict[str, Any]] = {
    'beautyExplore': {'model': 'gpt-image-2', 'quality': 'low', 'size': '1536x1024', 'candidateCount': 2},
    'beautyRefine': {'model': 'gpt-image-2', 'quality': 'medium', 'size': '1536x1024', 'candidateCount': 1},
    'authorityDraft': {'model': 'gpt-image-2', 'quality': 'low', 'size': '1024x1024', 'candidateCount': 2},
    'authorityFinal': {'model': 'gpt-image-2', 'quality': 'low', 'size': '1024x1024', 'candidateCount': 1},
}
DEFAULT_BUDGET = {
    'perRequestUsdMax': 0.05,
    'perAssetUsdMax': 0.50,
    'perSessionUsdMax': 2.00,
    'confirmationThresholdUsd': 0.02,
}


@dataclass(frozen=True)
class KeyStatus:
    configured: bool
    source: str | None
    masked: str | None


def read_config(package_root: Path) -> dict[str, Any]:
    path = package_root / 'config.json'
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_config(package_root: Path, payload: dict[str, Any]) -> Path:
    path = package_root / 'config.json'
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)
    return path


def _account_name() -> str:
    return getpass.getuser() or 'skyforge-user'


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    suffix = key[-4:] if len(key) >= 4 else key
    return f'••••••••{suffix}'


class KeychainBackend(Protocol):
    def read(self, service: str, account: str) -> str | None: ...

    def write(self, service: str, account: str, secret: str) -> None: ...

    def delete(self, service: str, account: str) -> None: ...


def _keychain_backend() -> KeychainBackend:
    return MacOSKeychain()


def read_keychain_key(
    *,
    backend_factory: Callable[[], KeychainBackend] = _keychain_backend,
    system_name: str | None = None,
) -> str | None:
    if (system_name or platform.system()) != 'Darwin':
        return None
    return backend_factory().read(KEYCHAIN_SERVICE, _account_name())


def save_keychain_key(
    key: str,
    *,
    backend_factory: Callable[[], KeychainBackend] = _keychain_backend,
    system_name: str | None = None,
) -> None:
    if (system_name or platform.system()) != 'Darwin':
        raise RuntimeError('Secure API-key storage is currently supported on macOS only')
    value = key.strip()
    if not value:
        raise ValueError('OpenAI API key cannot be empty')
    # Native SecItem* calls keep the secret out of process arguments, the
    # environment, shell history, and temporary files.
    backend_factory().write(KEYCHAIN_SERVICE, _account_name(), value)


def delete_keychain_key(
    *,
    backend_factory: Callable[[], KeychainBackend] = _keychain_backend,
    system_name: str | None = None,
) -> None:
    if (system_name or platform.system()) != 'Darwin':
        return
    backend_factory().delete(KEYCHAIN_SERVICE, _account_name())


def load_api_key(package_root: Path) -> tuple[str | None, str | None]:
    environment_key = os.environ.get('OPENAI_API_KEY')
    if environment_key:
        return environment_key, 'environment'
    try:
        keychain_key = read_keychain_key()
    except KeychainUserCancelled:
        # A cancelled authorization prompt must not crash the local server or
        # health endpoint. The credential remains secure and unavailable until
        # the user explicitly grants access on a later request.
        return None, None
    if keychain_key:
        return keychain_key, 'macOS Keychain'
    # Legacy plaintext configuration is migration input only. Runtime use is
    # intentionally denied so a failed Keychain migration cannot silently retain
    # an insecure credential path.
    return None, None


def key_status(package_root: Path) -> KeyStatus:
    key, source = load_api_key(package_root)
    return KeyStatus(configured=bool(key), source=source, masked=_mask_key(key))


def _positive_money(value: Any, field: str) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field} must be a number') from exc
    if amount < 0:
        raise ValueError(f'{field} cannot be negative')
    return round(amount, 6)


def _sanitize_stage(stage_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    defaults = DEFAULT_STAGE_SETTINGS[stage_key]
    model = str(payload.get('model') or defaults['model']).strip()
    quality = str(payload.get('quality') or defaults['quality']).strip()
    size = str(payload.get('size') or defaults['size']).strip()
    try:
        count = int(payload.get('candidateCount') or defaults['candidateCount'])
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{stage_key} candidate count must be an integer') from exc
    if not model:
        raise ValueError(f'{stage_key} model is required')
    if quality not in ALLOWED_QUALITIES:
        raise ValueError(f'Unsupported {stage_key} quality: {quality}')
    if size not in ALLOWED_IMAGE_SIZES:
        raise ValueError(f'Unsupported {stage_key} image size: {size}')
    if not 1 <= count <= 4:
        raise ValueError(f'{stage_key} candidate count must be between 1 and 4')
    return {'model': model, 'quality': quality, 'size': size, 'candidateCount': count}


def migrated_stage_settings(openai_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    configured = openai_config.get('stages') if isinstance(openai_config.get('stages'), dict) else {}
    stages: dict[str, dict[str, Any]] = {}
    for key in STAGE_KEYS:
        candidate = configured.get(key) if isinstance(configured.get(key), dict) else {}
        stages[key] = _sanitize_stage(key, candidate)
    return stages


def migrated_budget_settings(openai_config: dict[str, Any]) -> dict[str, float]:
    configured = openai_config.get('budget') if isinstance(openai_config.get('budget'), dict) else {}
    result = {
        key: _positive_money(configured.get(key, default), key)
        for key, default in DEFAULT_BUDGET.items()
    }
    if result['confirmationThresholdUsd'] > result['perRequestUsdMax']:
        raise ValueError('Confirmation threshold cannot exceed the per-request maximum')
    return result


def sanitize_and_save_settings(
    package_root: Path,
    *,
    blender_path: str,
    stages: dict[str, Any],
    budget: dict[str, Any],
) -> dict[str, Any]:
    sanitized_stages = {
        key: _sanitize_stage(key, stages.get(key) if isinstance(stages.get(key), dict) else {})
        for key in STAGE_KEYS
    }
    sanitized_budget = {
        key: _positive_money(budget.get(key, default), key)
        for key, default in DEFAULT_BUDGET.items()
    }
    if sanitized_budget['confirmationThresholdUsd'] > sanitized_budget['perRequestUsdMax']:
        raise ValueError('Confirmation threshold cannot exceed the per-request maximum')

    config = read_config(package_root)
    openai_config = config.get('openai') if isinstance(config.get('openai'), dict) else {}
    openai_config.pop('apiKey', None)
    config.pop('openaiApiKey', None)
    for legacy_key in ('imageModel', 'beautySize', 'authoritySize', 'beautyCountDefault', 'authorityCountDefault'):
        openai_config.pop(legacy_key, None)
    openai_config.update({'stages': sanitized_stages, 'budget': sanitized_budget})
    config['openai'] = openai_config
    # A blank browser field means "keep the current value" so the server never
    # has to echo the saved absolute path back to the client.
    if blender_path.strip():
        config['blenderPath'] = str(Path(blender_path).expanduser())
    write_config(package_root, config)
    return config


def settings_payload(package_root: Path, detected_blender_path: str | None) -> dict[str, Any]:
    config = read_config(package_root)
    openai_config = config.get('openai') if isinstance(config.get('openai'), dict) else {}
    status = key_status(package_root)
    return {
        'openai': {
            'configured': status.configured,
            'keySource': status.source,
            'maskedKey': status.masked,
            'stages': migrated_stage_settings(openai_config),
            'budget': migrated_budget_settings(openai_config),
        },
        'blender': {
            'configured': bool(config.get('blenderPath')),
            'available': bool(detected_blender_path),
            'executableName': Path(detected_blender_path).name if detected_blender_path else None,
        },
        'storage': {
            'apiKey': 'macOS Keychain (native Security framework)',
            'nonSecretSettings': 'config.json',
            'spendLedger': 'workspace/_concepts/spend_ledger.json',
        },
    }


def test_blender_executable(path_value: str) -> dict[str, str | bool]:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError('Blender executable is missing or not executable')
    result = subprocess.run(
        [str(path), '--version'],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or 'Blender version check failed')
    first_line = (result.stdout.strip().splitlines() or ['Blender detected'])[0]
    return {'ok': True, 'executableName': path.name, 'version': first_line}
