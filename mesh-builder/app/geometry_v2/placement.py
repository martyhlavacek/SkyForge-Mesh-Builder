from __future__ import annotations

import numpy as np
from PIL import Image

from app.authority_mesh import MASK_MARGIN, WORK_GRID_SIZE, _fit_authority, _rgba_and_mask

from .model import AuthorityPlanform

WORLD_SPAN = 5.5


def pixel_to_target(column: float, row: float) -> tuple[float, float]:
    return (
        (column - WORK_GRID_SIZE / 2) / WORK_GRID_SIZE * WORLD_SPAN,
        (WORK_GRID_SIZE / 2 - row) / WORK_GRID_SIZE * WORLD_SPAN,
    )


def target_to_pixel(x: float, y: float) -> tuple[float, float]:
    return (
        x / WORLD_SPAN * WORK_GRID_SIZE + WORK_GRID_SIZE / 2,
        WORK_GRID_SIZE / 2 - y / WORLD_SPAN * WORK_GRID_SIZE,
    )


def measure_planform(authority_path) -> AuthorityPlanform:
    rgba, raw_mask, _ = _rgba_and_mask(authority_path)
    fitted_rgba, fitted_mask, _, _ = _fit_authority(rgba, raw_mask)
    try:
        mask = np.asarray(fitted_mask, dtype=np.uint8) >= 128
    finally:
        fitted_rgba.close()
        fitted_mask.close()
        raw_mask.close()
        rgba.close()
    rows = np.flatnonzero(mask.any(axis=1))
    columns = np.flatnonzero(mask.any(axis=0))
    if not len(rows) or not len(columns):
        raise ValueError("Authority planform is empty")
    length = (float(rows[-1] - rows[0] + 1) / WORK_GRID_SIZE) * WORLD_SPAN
    width = (float(columns[-1] - columns[0] + 1) / WORK_GRID_SIZE) * WORLD_SPAN
    return AuthorityPlanform(mask, int(rows[0]), int(rows[-1]), length, width)


def row_span(planform: AuthorityPlanform, row: int) -> tuple[int, int]:
    occupied = np.flatnonzero(planform.mask[int(np.clip(row, 0, WORK_GRID_SIZE - 1))])
    if not len(occupied):
        raise ValueError(f"Recipe anchor selects an empty authority row: {row}")
    return int(occupied[0]), int(occupied[-1])


def normalized_anchor(planform: AuthorityPlanform, longitudinal: float, lateral: float) -> tuple[float, float]:
    row = int(round(planform.first_row + longitudinal * (planform.last_row - planform.first_row)))
    first, last = row_span(planform, row)
    centre = (first + last) * 0.5
    half_span = max((last - first) * 0.5, 1.0)
    column = centre + lateral * half_span
    return pixel_to_target(column, row)


def fit_planform_dimensions(
    planform: AuthorityPlanform,
    centre: tuple[float, float],
    desired_length: float,
    desired_width: float,
) -> tuple[float, float]:
    """Deterministically shrink a recipe footprint to remain inside measured row spans."""
    cx, cy = centre
    column, row = target_to_pixel(cx, cy)
    pixels_per_world = WORK_GRID_SIZE / WORLD_SPAN
    half_length_px = max(desired_length * pixels_per_world * 0.5, 2.0)
    first_row = max(planform.first_row + MASK_MARGIN // 2, int(np.floor(row - half_length_px)))
    last_row = min(planform.last_row - MASK_MARGIN // 2, int(np.ceil(row + half_length_px)))
    if first_row >= last_row:
        raise ValueError("Recipe component has no occupied longitudinal attachment span")
    margins: list[float] = []
    for sample_row in range(first_row, last_row + 1, max(1, (last_row - first_row) // 12)):
        occupied = np.flatnonzero(planform.mask[sample_row])
        if not len(occupied):
            margins.append(0.0)
            continue
        margins.append(min(column - float(occupied[0]), float(occupied[-1]) - column))
    safe_half_width = max(1.5, min(margins) * 0.86)
    safe_width = safe_half_width * 2.0 / pixels_per_world
    bounded_width = min(desired_width, safe_width)
    bounded_length = min(desired_length, (last_row - first_row) / pixels_per_world)
    if bounded_width <= 0.02 or bounded_length <= 0.05:
        raise ValueError("Recipe component cannot fit inside the authority planform")
    return bounded_length, bounded_width


def mask_image(planform: AuthorityPlanform) -> Image.Image:
    return Image.fromarray(np.where(planform.mask, 255, 0).astype(np.uint8), "L")
