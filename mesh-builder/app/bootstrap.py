from __future__ import annotations

import os
import shutil
from pathlib import Path

from .settings_store import (
    DEFAULT_BLENDER_PATH,
    DEFAULT_BUDGET,
    DEFAULT_STAGE_SETTINGS,
    read_config,
    save_keychain_key,
    write_config,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def detect_blender() -> str | None:
    configured = read_config(PACKAGE_ROOT).get('blenderPath')
    candidates = [configured, DEFAULT_BLENDER_PATH, shutil.which('blender')]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate)).expanduser().resolve()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def ensure_config() -> Path:
    config = read_config(PACKAGE_ROOT)
    blender = detect_blender()
    if blender:
        config['blenderPath'] = blender
    openai = config.get('openai') if isinstance(config.get('openai'), dict) else {}
    legacy_key = openai.get('apiKey') or config.get('openaiApiKey')
    if isinstance(legacy_key, str) and legacy_key.strip():
        try:
            save_keychain_key(legacy_key.strip())
        except RuntimeError:
            # Fail closed: a legacy plaintext credential is never retained or
            # used as a runtime fallback. The user can re-enter it in Settings.
            pass
        finally:
            openai.pop('apiKey', None)
            config.pop('openaiApiKey', None)
    # v0.5.2 deliberately replaces legacy expensive defaults rather than carrying
    # them forward silently. User-defined stage settings remain untouched.
    if not isinstance(openai.get('stages'), dict):
        openai['stages'] = DEFAULT_STAGE_SETTINGS
    if not isinstance(openai.get('budget'), dict):
        openai['budget'] = DEFAULT_BUDGET
    for legacy_name in ('imageModel', 'beautySize', 'authoritySize', 'beautyCountDefault', 'authorityCountDefault'):
        openai.pop(legacy_name, None)
    config['openai'] = openai
    return write_config(PACKAGE_ROOT, config)


if __name__ == '__main__':
    path = ensure_config()
    print(f'Configuration ready: {path}')
