from __future__ import annotations

import json
from pathlib import Path

from app.macos_keychain import KeychainUserCancelled
from app.settings_store import (
    DEFAULT_BUDGET,
    DEFAULT_STAGE_SETTINGS,
    KEYCHAIN_SERVICE,
    load_api_key,
    read_config,
    read_keychain_key,
    sanitize_and_save_settings,
    save_keychain_key,
    settings_payload,
)


class FakeKeychain:
    def __init__(self):
        self.secret = None
        self.calls = []

    def write(self, service, account, secret):
        self.calls.append(('write', service, account))
        self.secret = secret

    def read(self, service, account):
        self.calls.append(('read', service, account))
        return self.secret

    def delete(self, service, account):
        self.calls.append(('delete', service, account))
        self.secret = None


def test_keychain_write_uses_native_backend_and_never_subprocess_argv():
    backend = FakeKeychain()

    def factory():
        return backend
    save_keychain_key('sk-secret-test', backend_factory=factory, system_name='Darwin')
    assert backend.secret == 'sk-secret-test'
    assert backend.calls[0][0] == 'write'
    assert KEYCHAIN_SERVICE in backend.calls[0]
    assert read_keychain_key(backend_factory=factory, system_name='Darwin') == 'sk-secret-test'
    root = Path(__file__).resolve().parents[1]
    source = (root / 'app' / 'settings_store.py').read_text(encoding='utf-8')
    legacy_script = (root / 'scripts' / 'configure_openai.command').read_text(encoding='utf-8')
    assert 'add-generic-password' not in source + legacy_script
    assert "['security'" not in source + legacy_script
    assert '-w "$OPENAI_KEY"' not in legacy_script


def test_saved_settings_strip_plaintext_api_keys_and_store_all_stage_controls(tmp_path: Path):
    (tmp_path / 'config.json').write_text(json.dumps({
        'openaiApiKey': 'sk-old-root',
        'openai': {'apiKey': 'sk-old-nested', 'imageModel': 'old-model'},
    }))
    sanitize_and_save_settings(
        tmp_path,
        blender_path='/Applications/Blender.app/Contents/MacOS/Blender',
        stages=DEFAULT_STAGE_SETTINGS,
        budget=DEFAULT_BUDGET,
    )
    config = read_config(tmp_path)
    assert 'openaiApiKey' not in config
    assert 'apiKey' not in config['openai']
    assert 'imageModel' not in config['openai']
    assert config['openai']['stages']['beautyExplore'] == DEFAULT_STAGE_SETTINGS['beautyExplore']
    assert config['openai']['stages']['authorityFinal']['quality'] == 'low'
    assert config['openai']['budget']['perRequestUsdMax'] == 0.05


def test_settings_payload_never_exposes_raw_key_or_absolute_blender_path(tmp_path: Path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-top-secret-1234')
    path = '/Applications/Blender.app/Contents/MacOS/Blender'
    payload = settings_payload(tmp_path, path)
    serialized = json.dumps(payload)
    assert 'sk-top-secret-1234' not in serialized
    assert path not in serialized
    assert payload['openai']['configured'] is True
    assert payload['openai']['maskedKey'].endswith('1234')
    assert payload['blender']['executableName'] == 'Blender'


def test_single_launcher_automates_setup_and_does_not_run_engineering_suite():
    package_root = Path(__file__).resolve().parents[1]
    launcher = (package_root / 'Launch SkyForge Mesh Builder.command').read_text(encoding='utf-8')
    assert 'python3 -m venv .venv' in launcher
    assert 'pip install -r requirements.txt' in launcher
    assert 'python -m app.bootstrap' in launcher
    assert 'python -m app.server' in launcher
    assert 'run_tests.command' not in launcher
    assert 'pytest' not in launcher


def test_plaintext_legacy_config_is_never_a_runtime_key_source(tmp_path: Path, monkeypatch):
    (tmp_path / 'config.json').write_text(
        json.dumps({'openaiApiKey': 'sk-legacy-plaintext'}), encoding='utf-8'
    )
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setattr('app.settings_store.read_keychain_key', lambda: None)
    key, source = load_api_key(tmp_path)
    assert key is None
    assert source is None


def test_cancelled_keychain_prompt_does_not_crash_runtime_key_loading(tmp_path: Path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)

    def cancelled():
        raise KeychainUserCancelled('macOS Keychain read failed (OSStatus -128)')

    monkeypatch.setattr('app.settings_store.read_keychain_key', cancelled)
    key, source = load_api_key(tmp_path)
    assert key is None
    assert source is None
