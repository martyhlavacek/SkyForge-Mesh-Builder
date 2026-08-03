from __future__ import annotations

import numpy as np
import trimesh


def create_primitive(shape: str, dimensions: tuple[float, float, float], subdivisions: int = 2) -> trimesh.Trimesh:
    length, width, height = dimensions
    if min(dimensions) <= 0:
        raise ValueError("Primitive dimensions must be positive")
    if shape == "ellipsoid":
        mesh = trimesh.creation.icosphere(subdivisions=subdivisions, radius=1.0)
        mesh.apply_scale([width / 2.0, length / 2.0, height / 2.0])
    elif shape == "capsule":
        radius = 0.5
        cylindrical_height = max(length / max(width, height) - 1.0, 0.25)
        mesh = trimesh.creation.capsule(height=cylindrical_height, radius=radius, count=[16, 16])
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2.0, [1.0, 0.0, 0.0]))
        extents = np.asarray(mesh.extents, dtype=np.float64)
        mesh.apply_scale([width / extents[0], length / extents[1], height / extents[2]])
    elif shape == "box":
        mesh = trimesh.creation.box(extents=[width, length, height])
    else:
        raise ValueError(f"Unsupported deterministic primitive: {shape}")
    mesh.remove_unreferenced_vertices()
    if not mesh.is_watertight or not mesh.is_winding_consistent:
        raise RuntimeError(f"Generated {shape} primitive is not a closed consistent shell")
    return mesh
