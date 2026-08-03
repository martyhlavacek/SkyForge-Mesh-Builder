from __future__ import annotations

import itertools
from typing import Any

import numpy as np
import trimesh
from PIL import Image, ImageDraw


class OrientationError(RuntimeError):
    pass


def proper_axis_rotations() -> list[np.ndarray]:
    rotations = []
    for permutation in itertools.permutations(range(3)):
        for signs in itertools.product((-1.0, 1.0), repeat=3):
            matrix = np.zeros((3, 3), dtype=np.float64)
            for row, column in enumerate(permutation):
                matrix[row, column] = signs[row]
            if round(float(np.linalg.det(matrix))) == 1:
                rotations.append(matrix)
    return sorted(rotations, key=lambda item: tuple(item.flatten()))


def rasterize(mesh: trimesh.Trimesh, role: str, size: int = 128) -> np.ndarray:
    axes = {"top": (0, 1), "front": (0, 2), "right": (1, 2)}[role]
    vertices = np.asarray(mesh.vertices, dtype=np.float64)[:, axes]
    minimum, maximum = vertices.min(axis=0), vertices.max(axis=0)
    span = np.maximum(maximum - minimum, 1e-9)
    pixels = (vertices - minimum) / span * (size - 9) + 4
    pixels[:, 1] = size - 1 - pixels[:, 1]
    image = Image.new("1", (size, size), 0)
    draw = ImageDraw.Draw(image)
    for face in np.asarray(mesh.faces, dtype=np.int64):
        draw.polygon([(float(pixels[index, 0]), float(pixels[index, 1])) for index in face], fill=1)
    return np.asarray(image, dtype=bool)


def _iou(first: np.ndarray, second: np.ndarray) -> float:
    union = np.logical_or(first, second).sum()
    return float(np.logical_and(first, second).sum() / union) if union else 0.0


def resolve_orientation(
    mesh: trimesh.Trimesh,
    authority_masks: dict[str, np.ndarray],
    *,
    ambiguity_margin: float = 0.002,
) -> tuple[trimesh.Trimesh, dict[str, Any]]:
    if set(authority_masks) != {"top", "front", "right"} or not all(mask.any() for mask in authority_masks.values()):
        raise OrientationError("Three non-empty authority masks are required")
    scores = []
    for index, rotation in enumerate(proper_axis_rotations()):
        candidate = mesh.copy()
        transform = np.eye(4)
        transform[:3, :3] = rotation
        candidate.apply_transform(transform)
        per_view = {role: round(_iou(rasterize(candidate, role), authority_masks[role]), 8) for role in authority_masks}
        scores.append({"rotationIndex": index, "matrix": rotation.tolist(), "perView": per_view, "combined": round(sum(per_view.values()) / 3, 8)})
    ranked = sorted(scores, key=lambda item: (-item["combined"], item["rotationIndex"]))
    margin = float(ranked[0]["combined"] - ranked[1]["combined"])
    if margin < ambiguity_margin:
        raise OrientationError(f"Ambiguous axis orientation: winner margin {margin:.8f}")
    winner = mesh.copy()
    transform = np.eye(4)
    transform[:3, :3] = np.asarray(ranked[0]["matrix"])
    winner.apply_transform(transform)
    bounds = winner.bounds
    span = max(float(np.max(bounds[1] - bounds[0])), 1e-9)
    winner.apply_translation(-winner.centroid)
    winner.apply_scale(1.0 / span)
    return winner, {"scores": scores, "winner": ranked[0], "runnerUp": ranked[1], "margin": round(margin, 8), "ambiguityThreshold": ambiguity_margin}
