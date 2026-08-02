from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .pipeline import _write_json, sha256_file


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def concepts_root(workspace_root: Path) -> Path:
    root = workspace_root / '_concepts'
    root.mkdir(parents=True, exist_ok=True)
    return root


def create_concept_run(workspace_root: Path, *, kind: str, profile_id: str, asset_id: str) -> Path:
    run_id = f'{kind}-{profile_id}-{uuid.uuid4().hex[:8]}'
    root = concepts_root(workspace_root) / run_id
    (root / 'images').mkdir(parents=True, exist_ok=False)
    return root


def save_generated_image(run_root: Path, stem: str, index: int, bytes_data: bytes, extension: str = '.png') -> Path:
    filename = f'{stem}_{index:02d}{extension}'
    path = run_root / 'images' / filename
    path.write_bytes(bytes_data)
    return path


def build_image_record(run_root: Path, path: Path, label: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    record = {
        'label': label,
        'path': str(path.relative_to(run_root)),
        'filename': path.name,
        'sha256': sha256_file(path),
        'url': f'/api/concepts/files/{run_root.name}/{path.name}',
    }
    if extra:
        record.update(extra)
    return record


def write_run_metadata(run_root: Path, payload: dict[str, Any]) -> Path:
    path = run_root / 'metadata.json'
    _write_json(path, payload)
    return path


def read_run_metadata(run_root: Path) -> dict[str, Any]:
    return json.loads((run_root / 'metadata.json').read_text(encoding='utf-8'))
