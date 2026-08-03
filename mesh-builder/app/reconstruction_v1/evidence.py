from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from app.geometry_v2.metrics import topology_record

from .orientation import rasterize


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_glb(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    if len(payload) < 20 or payload[:4] != b"glTF":
        raise ValueError("Corrupt or empty GLB")
    scene = trimesh.load(path, force="scene", process=False)
    if not scene.geometry:
        raise ValueError("GLB contains no geometry")
    records = [topology_record(name, mesh) for name, mesh in sorted(scene.geometry.items())]
    if not all(record["finiteCoordinates"] and record["triangleCount"] > 0 for record in records):
        raise ValueError("GLB contains invalid geometry")
    combined = trimesh.util.concatenate([mesh.copy() for mesh in scene.geometry.values()])
    return {
        "sha256": sha256_file(path),
        "byteCount": len(payload),
        "geometryCount": len(records),
        "geometry": records,
        "bounds": np.round(combined.bounds, 9).tolist(),
    }


def write_manifest(root: Path, target: Path) -> dict[str, str]:
    files = {path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(root.rglob("*")) if path.is_file() and path != target}
    target.write_text(json.dumps(files, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return files


def verify_manifest(root: Path, target: Path) -> bool:
    expected = json.loads(target.read_text(encoding="utf-8"))
    return expected == {path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(root.rglob("*")) if path.is_file() and path != target}


def save_silhouettes(mesh: trimesh.Trimesh, output: Path) -> list[Path]:
    from PIL import Image

    paths = []
    for role in ("top", "front", "right"):
        path = output / f"canonical_{role}_silhouette.png"
        Image.fromarray(np.where(rasterize(mesh, role), 255, 0).astype(np.uint8)).save(path)
        paths.append(path)
    return paths
