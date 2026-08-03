from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import trimesh


@dataclass(frozen=True)
class AuthorityPlanform:
    mask: Any
    first_row: int
    last_row: int
    planform_length: float
    planform_width: float


@dataclass(frozen=True)
class PlacedComponent:
    name: str
    shape: str
    mesh: trimesh.Trimesh
    dimensions: tuple[float, float, float]
    centre: tuple[float, float, float]
    attachment_penetration: float
    minimum_volume: float
    minimum_triangles: int
    underside: bool


@dataclass(frozen=True)
class ExperimentResult:
    output_dir: Path
    mesh_path: Path
    clay_mesh_path: Path
    obj_path: Path
    report_path: Path
    registry_path: Path
    manifest_path: Path
    preview_paths: tuple[Path, ...]
    report: dict[str, Any]
