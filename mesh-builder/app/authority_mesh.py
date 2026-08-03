from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFilter, ImageOps

GENERATOR_ID = "skyforge.authority-two-sided-field"
GENERATOR_VERSION = "0.6.0"
WORK_GRID_SIZE = 384
MESH_GRID_SIZE = 256
PREVIEW_GRID_SIZE = 128
TEXTURE_SIZE = 512
MASK_MARGIN = 6
BACKGROUND_DISTANCE_THRESHOLD = 28
SMALL_ENCLOSED_HOLE_AREA_MAX = 12

# Internal generator geometry uses the same target convention as Blender/SkyForge:
# +X right, +Y forward, +Z up. glTF is semantically +Y up and -Z forward.
# Encode target coordinates as (x, z, -y) so Blender's glTF importer reconstructs
# the original target coordinates exactly.
TARGET_TO_GLTF = np.asarray(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, -1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ],
    dtype=np.float64,
)
GLTF_TO_BLENDER = np.asarray(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, -1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ],
    dtype=np.float64,
)

ACCEPTANCE_GATES = {
    "silhouetteIoUMin": 0.94,
    "aspectErrorMax": 0.035,
    "centroidDistanceMax": 0.02,
    "widthProfileMAEMax": 0.045,
    "boundaryEdgeCountMax": 0,
    "nonManifoldEdgeCountMax": 0,
    "componentCountMax": 1,
    "triangleCountMin": 1000,
    "triangleCountMax": 180000,
    "blenderImportSilhouetteIoUMin": 0.94,
    "blenderImportBoundsDeltaMax": 1e-5,
    "heightToPlanformRatioMax": 0.28,
    "flatBellySurfaceFractionMax": 0.06,
    "verticalWallSurfaceFractionMax": 0.045,
    "combinedConstructionArtifactFractionMax": 0.10,
    "tipToRootThicknessRatioMax": 0.40,
    "genusMax": 0,
    "lowerFieldRelativeResidualMin": 0.10,
    "sourceReloadEdgeAuditMustAgree": True,
}


@dataclass(frozen=True)
class GeneratedMesh:
    mesh_path: Path
    obj_path: Path
    material_path: Path
    texture_path: Path
    report_path: Path
    preview_paths: tuple[Path, ...]
    report: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rgba_and_mask(path: Path) -> tuple[Image.Image, Image.Image, str]:
    with Image.open(path) as source:
        rgba = source.convert("RGBA")
    alpha = rgba.getchannel("A")
    alpha_extrema = alpha.getextrema()
    if alpha_extrema and alpha_extrema[0] < 245:
        mask = alpha.point(lambda value: 255 if value >= 16 else 0)
        method = "alpha_threshold_16"
    else:
        rgb = rgba.convert("RGB")
        width, height = rgb.size
        corners = [
            rgb.getpixel((0, 0)),
            rgb.getpixel((width - 1, 0)),
            rgb.getpixel((0, height - 1)),
            rgb.getpixel((width - 1, height - 1)),
        ]
        background = tuple(int(round(sum(pixel[channel] for pixel in corners) / 4)) for channel in range(3))
        # Use float32 before squaring. int16 overflows for dark craft pixels on a light
        # opaque background (e.g. 240**2), producing negative sums and NaNs.
        pixels = np.asarray(rgb, dtype=np.float32)
        bg = np.asarray(background, dtype=np.float32)
        delta = pixels - bg
        distance = np.sqrt(np.sum(delta * delta, axis=2, dtype=np.float32))
        mask = Image.fromarray(np.where(distance >= BACKGROUND_DISTANCE_THRESHOLD, 255, 0).astype(np.uint8), "L")
        method = "corner_colour_distance_28"

    # Close one-pixel anti-aliased gaps without expanding the silhouette materially.
    mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    return rgba, mask, method


def _largest_component(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    best: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or seen[y, x]:
                continue
            queue: deque[tuple[int, int]] = deque([(y, x)])
            seen[y, x] = True
            component: list[tuple[int, int]] = []
            while queue:
                cy, cx = queue.popleft()
                component.append((cy, cx))
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        queue.append((ny, nx))
            if len(component) > len(best):
                best = component
    if not best:
        raise ValueError("Authority image contains no usable foreground silhouette")
    result = np.zeros_like(mask, dtype=bool)
    for y, x in best:
        result[y, x] = True
    return result


def _fill_small_enclosed_holes(
    mask: np.ndarray, area_max: int = SMALL_ENCLOSED_HOLE_AREA_MAX
) -> tuple[np.ndarray, dict[str, Any]]:
    """Fill only small enclosed background islands; preserve border-connected background."""
    if mask.ndim != 2:
        raise ValueError("mask must be two-dimensional")
    height, width = mask.shape
    background = ~mask
    exterior = np.zeros_like(background, dtype=bool)
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        for y in (0, height - 1):
            if background[y, x] and not exterior[y, x]:
                exterior[y, x] = True
                queue.append((y, x))
    for y in range(height):
        for x in (0, width - 1):
            if background[y, x] and not exterior[y, x]:
                exterior[y, x] = True
                queue.append((y, x))
    while queue:
        cy, cx = queue.popleft()
        for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
            if (
                0 <= ny < height
                and 0 <= nx < width
                and background[ny, nx]
                and not exterior[ny, nx]
            ):
                exterior[ny, nx] = True
                queue.append((ny, nx))

    enclosed = np.logical_and(background, ~exterior)
    seen = np.zeros_like(enclosed, dtype=bool)
    result = mask.copy()
    filled_areas: list[int] = []
    retained_areas: list[int] = []
    for y in range(height):
        for x in range(width):
            if not enclosed[y, x] or seen[y, x]:
                continue
            component: list[tuple[int, int]] = []
            seen[y, x] = True
            queue.append((y, x))
            while queue:
                cy, cx = queue.popleft()
                component.append((cy, cx))
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if (
                        0 <= ny < height
                        and 0 <= nx < width
                        and enclosed[ny, nx]
                        and not seen[ny, nx]
                    ):
                        seen[ny, nx] = True
                        queue.append((ny, nx))
            area = len(component)
            if area <= area_max:
                for cy, cx in component:
                    result[cy, cx] = True
                filled_areas.append(area)
            else:
                retained_areas.append(area)
    return result, {
        "areaThresholdPixels": area_max,
        "detectedHoleCount": len(filled_areas) + len(retained_areas),
        "filledHoleCount": len(filled_areas),
        "filledPixelCount": sum(filled_areas),
        "retainedHoleCount": len(retained_areas),
        "retainedHoleAreas": retained_areas,
    }


def _fit_authority(
    rgba: Image.Image, mask: Image.Image
) -> tuple[Image.Image, Image.Image, tuple[int, int, int, int], dict[str, Any]]:
    bbox = mask.getbbox()
    if not bbox:
        raise ValueError("Authority image contains no foreground silhouette")
    crop_mask = mask.crop(bbox)
    crop_rgba = rgba.crop(bbox)
    available = WORK_GRID_SIZE - 2 * MASK_MARGIN
    scale = min(available / crop_mask.width, available / crop_mask.height)
    size = (max(1, round(crop_mask.width * scale)), max(1, round(crop_mask.height * scale)))
    resized_mask = crop_mask.resize(size, Image.Resampling.NEAREST)
    resized_rgba = crop_rgba.resize(size, Image.Resampling.LANCZOS)
    canvas_mask = Image.new("L", (WORK_GRID_SIZE, WORK_GRID_SIZE), 0)
    canvas_rgba = Image.new("RGBA", (WORK_GRID_SIZE, WORK_GRID_SIZE), (0, 0, 0, 0))
    offset = ((WORK_GRID_SIZE - size[0]) // 2, (WORK_GRID_SIZE - size[1]) // 2)
    canvas_mask.paste(resized_mask, offset)
    canvas_rgba.alpha_composite(resized_rgba, offset)
    mask_array = _largest_component(np.asarray(canvas_mask, dtype=np.uint8) >= 128)
    mask_array, hole_filter = _fill_small_enclosed_holes(mask_array)
    final_mask = Image.fromarray(np.where(mask_array, 255, 0).astype(np.uint8), "L")
    final_rgba = canvas_rgba.copy()
    final_rgba.putalpha(final_mask)
    return final_rgba, final_mask, bbox, hole_filter


def _edt_1d_squared(values: np.ndarray) -> np.ndarray:
    """Exact one-dimensional squared Euclidean distance transform.

    This is the Felzenszwalb-Huttenlocher lower-envelope algorithm. It replaces
    the v0.5.3 per-pixel two-pass Python scan with a separable O(n) transform and
    makes the 384-pixel work grid practical without a SciPy dependency.
    """
    length = int(values.shape[0])
    sites = np.empty(length, dtype=np.int32)
    boundaries = np.empty(length + 1, dtype=np.float64)
    result = np.empty(length, dtype=np.float64)
    k = 0
    sites[0] = 0
    boundaries[0] = -np.inf
    boundaries[1] = np.inf
    for q in range(1, length):
        numerator = (values[q] + q * q) - (values[sites[k]] + sites[k] * sites[k])
        denominator = 2 * (q - sites[k])
        intersection = numerator / denominator
        while intersection <= boundaries[k]:
            k -= 1
            numerator = (values[q] + q * q) - (values[sites[k]] + sites[k] * sites[k])
            denominator = 2 * (q - sites[k])
            intersection = numerator / denominator
        k += 1
        sites[k] = q
        boundaries[k] = intersection
        boundaries[k + 1] = np.inf
    k = 0
    for q in range(length):
        while boundaries[k + 1] < q:
            k += 1
        delta = q - sites[k]
        result[q] = delta * delta + values[sites[k]]
    return result


def _distance_inside(mask: np.ndarray) -> np.ndarray:
    """Return exact Euclidean distance from each foreground cell to background."""
    if mask.ndim != 2:
        raise ValueError("mask must be two-dimensional")
    maximum_squared = float(mask.shape[0] * mask.shape[0] + mask.shape[1] * mask.shape[1] + 1)
    seed = np.where(mask, maximum_squared, 0.0).astype(np.float64)
    horizontal = np.empty_like(seed)
    for row in range(seed.shape[0]):
        horizontal[row, :] = _edt_1d_squared(seed[row, :])
    squared = np.empty_like(seed)
    for column in range(seed.shape[1]):
        squared[:, column] = _edt_1d_squared(horizontal[:, column])
    distance = np.sqrt(squared, dtype=np.float64).astype(np.float32)
    distance[~mask] = 0.0
    return distance


def _smooth(values: np.ndarray, mask: np.ndarray, passes: int = 3) -> np.ndarray:
    result = values.astype(np.float32)
    for _ in range(passes):
        padded = np.pad(result, 1, mode="edge")
        padded_mask = np.pad(mask.astype(np.float32), 1, mode="constant")
        total = np.zeros_like(result)
        weight = np.zeros_like(result)
        for oy in range(3):
            for ox in range(3):
                sample = padded[oy:oy + result.shape[0], ox:ox + result.shape[1]]
                sample_mask = padded_mask[oy:oy + result.shape[0], ox:ox + result.shape[1]]
                kernel_weight = 2.0 if (oy, ox) == (1, 1) else 1.0
                total += sample * sample_mask * kernel_weight
                weight += sample_mask * kernel_weight
        result = np.where(mask, total / np.maximum(weight, 1e-6), 0.0)
    return result


def _row_relative_lateral_coordinate(mask: np.ndarray) -> np.ndarray:
    """Measure lateral position relative to each row's occupied planform span."""
    height, width = mask.shape
    x_grid = np.arange(width, dtype=np.float32)[None, :]
    result = np.ones((height, width), dtype=np.float32)
    for row in range(height):
        occupied = np.flatnonzero(mask[row])
        if not len(occupied):
            continue
        centre = (float(occupied[0]) + float(occupied[-1])) * 0.5
        half_span = max((float(occupied[-1]) - float(occupied[0])) * 0.5, 1.0)
        result[row, :] = np.abs(x_grid[0] - centre) / half_span
    return np.clip(result, 0.0, 1.0)


def _longitudinal_coordinate(mask: np.ndarray) -> np.ndarray:
    """Return 0..1 from the first occupied row to the last occupied row."""
    occupied_rows = np.flatnonzero(mask.any(axis=1))
    if not len(occupied_rows):
        raise ValueError("Cannot measure longitudinal coordinate for an empty mask")
    first = float(occupied_rows[0])
    last = float(occupied_rows[-1])
    rows = np.arange(mask.shape[0], dtype=np.float32)[:, None]
    values = np.clip((rows - first) / max(last - first, 1.0), 0.0, 1.0)
    return np.broadcast_to(values, mask.shape).astype(np.float32)


def _field_independence_metrics(
    upper: np.ndarray, lower_depth: np.ndarray, mask: np.ndarray
) -> dict[str, float]:
    upper_values = upper[mask].astype(np.float64)
    lower_values = lower_depth[mask].astype(np.float64)
    denominator = float(np.dot(upper_values, upper_values))
    scale = float(np.dot(upper_values, lower_values) / max(denominator, 1e-12))
    residual = lower_values - scale * upper_values
    relative_residual = float(
        np.linalg.norm(residual) / max(float(np.linalg.norm(lower_values)), 1e-12)
    )
    correlation = float(np.corrcoef(upper_values, lower_values)[0, 1])

    # A stronger descriptive null: predict lower depth from upper height alone
    # using quantile bins. This is reported for honesty but is not a release
    # gate; the scalar residual remains the explicit anti-rescaling guard.
    quantiles = np.unique(np.quantile(upper_values, np.linspace(0.0, 1.0, 65)))
    if len(quantiles) <= 2:
        binned_relative_residual = relative_residual
    else:
        bins = np.clip(np.digitize(upper_values, quantiles[1:-1], right=True), 0, len(quantiles) - 2)
        predicted = np.zeros_like(lower_values)
        global_mean = float(lower_values.mean())
        for index in range(len(quantiles) - 1):
            selected = bins == index
            predicted[selected] = float(lower_values[selected].mean()) if selected.any() else global_mean
        binned_relative_residual = float(
            np.linalg.norm(lower_values - predicted)
            / max(float(np.linalg.norm(lower_values)), 1e-12)
        )
    return {
        "bestFitLowerToUpperScale": scale,
        "pearsonCorrelation": correlation,
        "relativeResidual": relative_residual,
        "binnedFunctionRelativeResidual": binned_relative_residual,
        "gateInterpretation": "not_a_rescaled_copy",
    }


def _two_sided_fields(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Build distinct upper and lower fields from separate planform bases.

    The upper surface uses a broad distance hull and forward crown. The lower
    surface uses a steeper distance exponent, a narrow keel, a mid-aft belly
    bulge and a chine term. No RGB or luminance term is consumed, and neither
    surface is mirrored about the image centre.
    """
    distance = _distance_inside(mask)
    maximum = float(distance.max()) or 1.0
    distance_norm = np.clip(distance / maximum, 0.0, 1.0)
    lateral = _row_relative_lateral_coordinate(mask)
    longitudinal = _longitudinal_coordinate(mask)

    upper_hull = np.power(distance_norm, 0.68, dtype=np.float32)
    lower_hull = np.power(distance_norm, 1.08, dtype=np.float32)
    upper_crown = np.exp(-np.power(lateral / 0.34, 4.0)).astype(np.float32)
    lower_keel = np.exp(-np.power(lateral / 0.22, 2.0)).astype(np.float32)
    forward_spine = (
        np.exp(-np.square((longitudinal - 0.28) / 0.22)).astype(np.float32) * upper_crown
    )
    belly_bulge = (
        np.exp(-np.square((longitudinal - 0.62) / 0.20)).astype(np.float32) * lower_keel
    )
    chine = (
        np.exp(-np.square((lateral - 0.45) / 0.18)).astype(np.float32)
        * np.exp(-np.square((longitudinal - 0.55) / 0.32)).astype(np.float32)
    )

    upper = upper_hull * (0.40 + 0.19 * upper_crown + 0.045 * forward_spine)
    lower_depth = lower_hull * (0.14 + 0.07 * lower_keel + 0.025 * chine)
    lower_depth += np.power(distance_norm, 0.82, dtype=np.float32) * (0.055 * belly_bulge)
    centre = upper_hull * (
        0.012 * (0.5 - lateral) + 0.006 * (0.5 - longitudinal) * upper_crown
    )

    upper = _smooth(upper, mask, passes=2)
    lower_depth = _smooth(lower_depth, mask, passes=2)
    centre = _smooth(centre, mask, passes=1)

    top = centre + upper
    bottom = centre - lower_depth
    top[~mask] = 0.0
    bottom[~mask] = 0.0
    centre[~mask] = 0.0
    thickness = np.where(mask, top - bottom, 0.0)
    occupied = thickness[mask]
    root = thickness[np.logical_and(mask, lateral <= 0.25)]
    tip = thickness[np.logical_and(mask, lateral >= 0.75)]
    root_median = float(np.median(root)) if root.size else 0.0
    tip_median = float(np.median(tip)) if tip.size else 0.0
    summary: dict[str, Any] = {
        "minimum": float(np.min(occupied)),
        "p05": float(np.percentile(occupied, 5)),
        "median": float(np.median(occupied)),
        "p95": float(np.percentile(occupied, 95)),
        "maximum": float(np.max(occupied)),
        "rootMedian": root_median,
        "tipMedian": tip_median,
        "tipToRootRatio": tip_median / max(root_median, 1e-9),
        "upperLowerIndependence": _field_independence_metrics(upper, lower_depth, mask),
    }
    return top.astype(np.float32), bottom.astype(np.float32), centre.astype(np.float32), summary


def _resample_geometry_fields(
    mask: np.ndarray,
    top: np.ndarray,
    bottom: np.ndarray,
    centre: np.ndarray,
    size: int = MESH_GRID_SIZE,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Resample the high-resolution work field onto a bounded target grid."""
    mask_image = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), "L")
    mesh_mask_image = mask_image.resize((size, size), Image.Resampling.NEAREST)
    mesh_mask = _largest_component(np.asarray(mesh_mask_image, dtype=np.uint8) >= 128)

    def resize(values: np.ndarray) -> np.ndarray:
        image = Image.fromarray(values.astype(np.float32), "F")
        resized = image.resize((size, size), Image.Resampling.BILINEAR)
        array = np.asarray(resized, dtype=np.float32).copy()
        array[~mesh_mask] = 0.0
        return array

    return mesh_mask, resize(top), resize(bottom), resize(centre)


def _project_triangle_count(mask: np.ndarray) -> int:
    occupied = int(mask.sum())
    boundary_sides = 0
    height, width = mask.shape
    for y in range(height):
        for x in range(width):
            if not mask[y, x]:
                continue
            boundary_sides += int(y == 0 or not mask[y - 1, x])
            boundary_sides += int(y + 1 == height or not mask[y + 1, x])
            boundary_sides += int(x == 0 or not mask[y, x - 1])
            boundary_sides += int(x + 1 == width or not mask[y, x + 1])
    return occupied * 4 + boundary_sides * 2


def _select_mesh_grid_size(
    mask: np.ndarray, top: np.ndarray, bottom: np.ndarray, centre: np.ndarray
) -> tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    for size in (MESH_GRID_SIZE, 224, 192, 160):
        mesh_mask, mesh_top, mesh_bottom, mesh_centre = _resample_geometry_fields(
            mask, top, bottom, centre, size
        )
        projected = _project_triangle_count(mesh_mask)
        if projected <= ACCEPTANCE_GATES["triangleCountMax"]:
            return size, mesh_mask, mesh_top, mesh_bottom, mesh_centre, projected
    raise RuntimeError(
        "Authority planform exceeds the triangle budget even at a 160-pixel export grid"
    )


def _corner_heights(cell_height: np.ndarray, mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    total = np.zeros((height + 1, width + 1), dtype=np.float32)
    count = np.zeros((height + 1, width + 1), dtype=np.float32)
    for oy in (0, 1):
        for ox in (0, 1):
            total[oy:oy + height, ox:ox + width] += cell_height * mask
            count[oy:oy + height, ox:ox + width] += mask
    corners = np.where(count > 0, total / np.maximum(count, 1), 0)
    return corners


def _metrics(reference: np.ndarray, generated: np.ndarray) -> dict[str, float]:
    intersection = int(np.logical_and(reference, generated).sum())
    union = int(np.logical_or(reference, generated).sum())
    iou = intersection / union if union else 0.0

    def stats(mask: np.ndarray) -> tuple[float, float, float, float, np.ndarray]:
        ys, xs = np.nonzero(mask)
        if not len(xs):
            raise ValueError("Cannot measure an empty silhouette")
        width = float(xs.max() - xs.min() + 1)
        height = float(ys.max() - ys.min() + 1)
        centroid_x = float(xs.mean() / mask.shape[1])
        centroid_y = float(ys.mean() / mask.shape[0])
        row_widths = mask.sum(axis=1).astype(np.float32) / mask.shape[1]
        return width, height, centroid_x, centroid_y, row_widths

    rw, rh, rcx, rcy, rprofile = stats(reference)
    gw, gh, gcx, gcy, gprofile = stats(generated)
    aspect_error = abs((gw / gh) - (rw / rh)) / max(rw / rh, 1e-6)
    centroid_distance = math.hypot(gcx - rcx, gcy - rcy)
    width_mae = float(np.mean(np.abs(rprofile - gprofile)))
    return {
        "silhouetteIoU": round(iou, 6),
        "aspectError": round(aspect_error, 6),
        "centroidDistance": round(centroid_distance, 6),
        "widthProfileMAE": round(width_mae, 6),
    }


def _triangulate_quad(a: int, b: int, c: int, d: int) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    return (a, b, c), (a, c, d)


def _build_mesh(
    mask: np.ndarray,
    top_heights: np.ndarray,
    bottom_heights: np.ndarray,
    centre_heights: np.ndarray,
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float]], list[tuple[int, int, int]], list[str]]:
    """Build a closed two-sided mesh with a near-zero tapered perimeter seam."""
    height, width = mask.shape
    top_corners = _corner_heights(top_heights, mask)
    bottom_corners = _corner_heights(bottom_heights, mask)
    centre_corners = _corner_heights(centre_heights, mask)
    adjacent_count = np.zeros((height + 1, width + 1), dtype=np.uint8)
    for oy in (0, 1):
        for ox in (0, 1):
            adjacent_count[oy:oy + height, ox:ox + width] += mask.astype(np.uint8)

    vertices: list[tuple[float, float, float]] = []
    uvs: list[tuple[float, float]] = []
    vertex_map: dict[tuple[str, int, int], int] = {}
    faces: list[tuple[int, int, int]] = []
    face_kinds: list[str] = []
    max_span = float(max(width, height))
    edge_half_thickness = 0.003

    def vertex(layer: str, gx: int, gy: int) -> int:
        key = (layer, gx, gy)
        existing = vertex_map.get(key)
        if existing is not None:
            return existing
        x = (gx - width / 2) / max_span * 5.5
        y = (height / 2 - gy) / max_span * 5.5
        boundary = 0 < adjacent_count[gy, gx] < 4
        if boundary:
            centre = float(centre_corners[gy, gx])
            z = centre + edge_half_thickness if layer == "top" else centre - edge_half_thickness
        else:
            z = float(top_corners[gy, gx]) if layer == "top" else float(bottom_corners[gy, gx])
        vertices.append((x, y, z))
        uvs.append((gx / width, 1.0 - gy / height))
        index = len(vertices)  # OBJ is 1-based.
        vertex_map[key] = index
        return index

    def add_quad(a: int, b: int, c: int, d: int, kind: str) -> None:
        first, second = _triangulate_quad(a, b, c, d)
        faces.extend((first, second))
        face_kinds.extend((kind, kind))

    for y in range(height):
        for x in range(width):
            if not mask[y, x]:
                continue
            tl = vertex("top", x, y)
            tr = vertex("top", x + 1, y)
            br = vertex("top", x + 1, y + 1)
            bl = vertex("top", x, y + 1)
            btl = vertex("bottom", x, y)
            btr = vertex("bottom", x + 1, y)
            bbr = vertex("bottom", x + 1, y + 1)
            bbl = vertex("bottom", x, y + 1)
            add_quad(bl, br, tr, tl, "top")
            add_quad(btl, btr, bbr, bbl, "bottom")
            if y == 0 or not mask[y - 1, x]:
                add_quad(btl, tl, tr, btr, "side")
            if y + 1 == height or not mask[y + 1, x]:
                add_quad(bbl, bbr, br, bl, "side")
            if x == 0 or not mask[y, x - 1]:
                add_quad(btl, bbl, bl, tl, "side")
            if x + 1 == width or not mask[y, x + 1]:
                add_quad(btr, tr, br, bbr, "side")
    return vertices, uvs, faces, face_kinds


def _edge_audit(faces: Iterable[tuple[int, int, int]]) -> dict[str, int]:
    counts: Counter[tuple[int, int]] = Counter()
    for face in faces:
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            counts[tuple(sorted((a, b)))] += 1
    boundary = sum(1 for value in counts.values() if value == 1)
    non_manifold = sum(1 for value in counts.values() if value > 2)
    return {
        "uniqueEdgeCount": len(counts),
        "boundaryEdgeCount": boundary,
        "nonManifoldEdgeCount": non_manifold,
    }


def _trimesh_edge_audit(mesh: trimesh.Trimesh) -> dict[str, int]:
    faces = [tuple(int(index) + 1 for index in face) for face in np.asarray(mesh.faces, dtype=np.int64)]
    return _edge_audit(faces)


def _geometry_metrics(
    mesh: trimesh.Trimesh,
    thickness_summary: dict[str, Any],
    mask_method: str,
    mesh_grid_size: int,
) -> dict[str, Any]:
    normals = np.asarray(mesh.face_normals, dtype=np.float64)
    areas = np.asarray(mesh.area_faces, dtype=np.float64)
    total_area = float(areas.sum()) or 1.0
    angle = math.radians(3.0)
    flat_belly = normals[:, 2] <= -math.cos(angle)
    vertical_wall = np.abs(normals[:, 2]) <= math.sin(angle)
    combined = np.logical_or(flat_belly, vertical_wall)
    components = len(mesh.split(only_watertight=False))
    euler_number = int(mesh.euler_number)
    genus = (2 * components - euler_number) / 2
    return {
        "representation": "two_sided_planform_field_with_edge_convergence",
        "workGridSize": WORK_GRID_SIZE,
        "meshGridSize": mesh_grid_size,
        "previewGridSize": PREVIEW_GRID_SIZE,
        "geometryMetricsSource": "independent_reloaded_glb_in_target_frame",
        "albedoInfluencesGeometry": mask_method != "alpha_threshold_16",
        "albedoGeometryInfluenceScope": (
            "none" if mask_method == "alpha_threshold_16" else "foreground_mask_derivation_only"
        ),
        "surfaceAngleToleranceDegrees": 3.0,
        "flatBellySurfaceFraction": round(float(areas[flat_belly].sum()) / total_area, 6),
        "verticalWallSurfaceFraction": round(float(areas[vertical_wall].sum()) / total_area, 6),
        "combinedConstructionArtifactFraction": round(float(areas[combined].sum()) / total_area, 6),
        "eulerNumber": euler_number,
        "genus": round(float(genus), 6),
        "sectionThickness": {
            key: (
                {
                    nested_key: (
                        round(float(nested_value), 6)
                        if isinstance(nested_value, (int, float, np.number))
                        else nested_value
                    )
                    for nested_key, nested_value in value.items()
                }
                if isinstance(value, dict)
                else round(float(value), 6)
            )
            for key, value in thickness_summary.items()
        },
    }


def _write_obj(
    output_dir: Path,
    vertices: list[tuple[float, float, float]],
    uvs: list[tuple[float, float]],
    faces: list[tuple[int, int, int]],
) -> tuple[Path, Path]:
    obj_path = output_dir / "authority_generated_mesh.obj"
    mtl_path = output_dir / "authority_generated_mesh.mtl"
    with obj_path.open("w", encoding="utf-8") as stream:
        stream.write(f"# Generated from approved top-down authority by {GENERATOR_ID} v{GENERATOR_VERSION}\n")
        stream.write("mtllib authority_generated_mesh.mtl\n")
        stream.write("o authority_generated_craft\n")
        for x, y, z in vertices:
            stream.write(f"v {x:.7f} {y:.7f} {z:.7f}\n")
        for u, v in uvs:
            stream.write(f"vt {u:.7f} {v:.7f}\n")
        stream.write("usemtl AuthorityAlbedo\n")
        for a, b, c in faces:
            stream.write(f"f {a}/{a} {b}/{b} {c}/{c}\n")
    mtl_path.write_text(
        "newmtl AuthorityAlbedo\n"
        "Ka 0.100000 0.100000 0.100000\n"
        "Kd 1.000000 1.000000 1.000000\n"
        "Ks 0.120000 0.120000 0.120000\n"
        "Ns 32.000000\n"
        "map_Kd authority_albedo.png\n",
        encoding="utf-8",
    )
    return obj_path, mtl_path


def _face_colour(texture: np.ndarray, face: tuple[int, int, int], uvs: list[tuple[float, float]], kind: str) -> tuple[int, int, int, int]:
    uv = np.mean(np.asarray([uvs[index - 1] for index in face]), axis=0)
    tx = int(np.clip(round(uv[0] * (texture.shape[1] - 1)), 0, texture.shape[1] - 1))
    ty = int(np.clip(round((1.0 - uv[1]) * (texture.shape[0] - 1)), 0, texture.shape[0] - 1))
    colour = texture[ty, tx, :3].astype(np.float32)
    factor = 1.0 if kind == "top" else (0.55 if kind == "side" else 0.28)
    colour = np.clip(colour * factor + (18 if kind == "side" else 0), 0, 255).astype(np.uint8)
    return int(colour[0]), int(colour[1]), int(colour[2]), 255


def _software_render(
    vertices: list[tuple[float, float, float]],
    uvs: list[tuple[float, float]],
    faces: list[tuple[int, int, int]],
    face_kinds: list[str],
    texture_image: Image.Image,
    bank_degrees: float,
    pitch_degrees: float,
    output_path: Path,
    size: int = 384,
) -> None:
    points = np.asarray(vertices, dtype=np.float32)
    bank = math.radians(bank_degrees)
    pitch = math.radians(pitch_degrees)
    ry = np.asarray(
        [[math.cos(bank), 0, math.sin(bank)], [0, 1, 0], [-math.sin(bank), 0, math.cos(bank)]],
        dtype=np.float32,
    )
    transformed = points @ ry.T
    screen_x = transformed[:, 0]
    screen_y = transformed[:, 1] * math.cos(pitch) - transformed[:, 2] * math.sin(pitch)
    depth = transformed[:, 1] * math.sin(pitch) + transformed[:, 2] * math.cos(pitch)
    margin = 30
    span_x = float(screen_x.max() - screen_x.min()) or 1.0
    span_y = float(screen_y.max() - screen_y.min()) or 1.0
    scale = min((size - 2 * margin) / span_x, (size - 2 * margin) / span_y)
    px = (screen_x - (screen_x.min() + screen_x.max()) / 2) * scale + size / 2
    py = size / 2 - (screen_y - (screen_y.min() + screen_y.max()) / 2) * scale
    texture = np.asarray(texture_image.convert("RGBA"), dtype=np.uint8)
    ordered = sorted(
        range(len(faces)),
        key=lambda index: float(np.mean([depth[vertex - 1] for vertex in faces[index]])),
    )
    canvas = Image.new("RGBA", (size, size), (18, 22, 28, 255))
    draw = ImageDraw.Draw(canvas, "RGBA")
    try:
        for face_index in ordered:
            face = faces[face_index]
            polygon = [(float(px[index - 1]), float(py[index - 1])) for index in face]
            colour = _face_colour(texture, face, uvs, face_kinds[face_index])
            draw.polygon(polygon, fill=colour)
        canvas.save(output_path)
    finally:
        del draw
        canvas.close()


def _contact_sheet(authority: Image.Image, previews: list[Path], output_path: Path) -> None:
    tile = 256
    labels = ["AUTHORITY", "GENERATED TOP", "BANK LEFT", "BANK RIGHT"]
    sheet = Image.new("RGBA", (tile * 4, tile + 28), (20, 24, 30, 255))
    draw = ImageDraw.Draw(sheet)
    images = [authority, *(Image.open(path).convert("RGBA") for path in previews)]
    try:
        for index, (label, image) in enumerate(zip(labels, images, strict=True)):
            draw.text((index * tile + 8, 7), label, fill=(240, 244, 248, 255))
            fitted = ImageOps.contain(image, (tile - 16, tile - 16), Image.Resampling.LANCZOS)
            x = index * tile + (tile - fitted.width) // 2
            y = 28 + (tile - fitted.height) // 2
            sheet.alpha_composite(fitted, (x, y))
    finally:
        for image in images[1:]:
            image.close()
    sheet.save(output_path)


def _to_blender_import_coordinates(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    result = mesh.copy()
    result.apply_transform(GLTF_TO_BLENDER)
    return result


def _bounds_delta(first: trimesh.Trimesh, second: trimesh.Trimesh) -> float:
    return float(np.max(np.abs(np.asarray(first.bounds) - np.asarray(second.bounds))))


def _height_to_planform_ratio(mesh: trimesh.Trimesh) -> float:
    extents = np.asarray(mesh.extents, dtype=np.float64)
    return float(extents[2] / max(extents[0], extents[1], 1e-9))


def _rasterize_target_top_silhouette(mesh: trimesh.Trimesh) -> np.ndarray:
    canvas = Image.new("L", (WORK_GRID_SIZE, WORK_GRID_SIZE), 0)
    draw = ImageDraw.Draw(canvas)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    projected = np.column_stack((
        vertices[:, 0] / 5.5 * WORK_GRID_SIZE + WORK_GRID_SIZE / 2,
        WORK_GRID_SIZE / 2 - vertices[:, 1] / 5.5 * WORK_GRID_SIZE,
    ))
    for face in np.asarray(mesh.faces, dtype=np.int64):
        polygon = [(float(projected[index, 0]), float(projected[index, 1])) for index in face]
        draw.polygon(polygon, fill=255)
    return np.asarray(canvas, dtype=np.uint8) >= 128


def _gate_results(
    metrics: dict[str, float],
    blender_metrics: dict[str, float],
    reload_audit: dict[str, int],
    triangle_count: int,
    component_count: int,
    blender_bounds_delta: float,
    height_to_planform_ratio: float,
    geometry_metrics: dict[str, Any],
    edge_audits_agree: bool,
) -> dict[str, Any]:
    checks = {
        "silhouetteIoU": metrics["silhouetteIoU"] >= ACCEPTANCE_GATES["silhouetteIoUMin"],
        "aspectError": metrics["aspectError"] <= ACCEPTANCE_GATES["aspectErrorMax"],
        "centroidDistance": metrics["centroidDistance"] <= ACCEPTANCE_GATES["centroidDistanceMax"],
        "widthProfileMAE": metrics["widthProfileMAE"] <= ACCEPTANCE_GATES["widthProfileMAEMax"],
        "blenderImportSilhouetteIoU": (
            blender_metrics["silhouetteIoU"] >= ACCEPTANCE_GATES["blenderImportSilhouetteIoUMin"]
        ),
        "blenderImportBoundsDelta": blender_bounds_delta <= ACCEPTANCE_GATES["blenderImportBoundsDeltaMax"],
        "heightToPlanformRatio": height_to_planform_ratio <= ACCEPTANCE_GATES["heightToPlanformRatioMax"],
        "boundaryEdges": reload_audit["boundaryEdgeCount"] <= ACCEPTANCE_GATES["boundaryEdgeCountMax"],
        "nonManifoldEdges": (
            reload_audit["nonManifoldEdgeCount"] <= ACCEPTANCE_GATES["nonManifoldEdgeCountMax"]
        ),
        "components": component_count <= ACCEPTANCE_GATES["componentCountMax"],
        "triangleCountMinimum": triangle_count >= ACCEPTANCE_GATES["triangleCountMin"],
        "triangleCountMaximum": triangle_count <= ACCEPTANCE_GATES["triangleCountMax"],
        "flatBellySurfaceFraction": (
            geometry_metrics["flatBellySurfaceFraction"]
            <= ACCEPTANCE_GATES["flatBellySurfaceFractionMax"]
        ),
        "verticalWallSurfaceFraction": (
            geometry_metrics["verticalWallSurfaceFraction"]
            <= ACCEPTANCE_GATES["verticalWallSurfaceFractionMax"]
        ),
        "combinedConstructionArtifactFraction": (
            geometry_metrics["combinedConstructionArtifactFraction"]
            <= ACCEPTANCE_GATES["combinedConstructionArtifactFractionMax"]
        ),
        "tipToRootThicknessRatio": (
            geometry_metrics["sectionThickness"]["tipToRootRatio"]
            <= ACCEPTANCE_GATES["tipToRootThicknessRatioMax"]
        ),
        "genus": geometry_metrics["genus"] <= ACCEPTANCE_GATES["genusMax"],
        "lowerFieldIndependence": (
            geometry_metrics["sectionThickness"]["upperLowerIndependence"]["relativeResidual"]
            >= ACCEPTANCE_GATES["lowerFieldRelativeResidualMin"]
        ),
        "sourceReloadEdgeAuditAgreement": (
            edge_audits_agree if ACCEPTANCE_GATES["sourceReloadEdgeAuditMustAgree"] else True
        ),
    }
    return {"checks": checks, "passed": all(checks.values())}


def generate_authority_mesh(authority_path: Path, output_dir: Path) -> GeneratedMesh:
    output_dir.mkdir(parents=True, exist_ok=True)
    rgba, raw_mask, mask_method = _rgba_and_mask(authority_path)
    fitted_rgba, fitted_mask_image, source_bbox, hole_filter = _fit_authority(rgba, raw_mask)
    fitted_mask = np.asarray(fitted_mask_image, dtype=np.uint8) >= 128

    top_work, bottom_work, centre_work, thickness_summary = _two_sided_fields(fitted_mask)
    (
        selected_mesh_grid_size,
        mesh_mask,
        top_mesh,
        bottom_mesh,
        centre_mesh,
        projected_triangle_count,
    ) = _select_mesh_grid_size(fitted_mask, top_work, bottom_work, centre_work)
    vertices, uvs, faces, face_kinds = _build_mesh(mesh_mask, top_mesh, bottom_mesh, centre_mesh)
    source_audit = _edge_audit(faces)

    texture_path = output_dir / "authority_albedo.png"
    texture = fitted_rgba.resize((TEXTURE_SIZE, TEXTURE_SIZE), Image.Resampling.LANCZOS)
    texture.save(texture_path)
    obj_path, mtl_path = _write_obj(output_dir, vertices, uvs, faces)
    loaded_mesh = trimesh.load(obj_path, force="mesh", process=False)
    if not loaded_mesh.is_watertight or not loaded_mesh.is_winding_consistent:
        raise RuntimeError("Independent GLB export validation rejected the generated OBJ topology")
    glb_path = output_dir / "authority_generated_mesh.glb"
    gltf_mesh = loaded_mesh.copy()
    gltf_mesh.apply_transform(TARGET_TO_GLTF)
    glb_path.write_bytes(trimesh.exchange.gltf.export_glb(gltf_mesh))
    reloaded_glb = trimesh.load(glb_path, force="mesh", process=False)
    if not reloaded_glb.is_watertight or len(reloaded_glb.faces) != len(faces):
        raise RuntimeError("Generated GLB failed independent reload validation")

    reload_audit = _trimesh_edge_audit(reloaded_glb)
    edge_audits_agree = source_audit == reload_audit
    component_count = len(reloaded_glb.split(only_watertight=False))
    blender_import_mesh = _to_blender_import_coordinates(reloaded_glb)
    blender_bounds_delta = _bounds_delta(loaded_mesh, blender_import_mesh)
    height_to_planform_ratio = _height_to_planform_ratio(blender_import_mesh)
    geometry_metrics = _geometry_metrics(
        blender_import_mesh, thickness_summary, mask_method, selected_mesh_grid_size
    )

    generated_projection = _rasterize_target_top_silhouette(loaded_mesh)
    blender_projection = _rasterize_target_top_silhouette(blender_import_mesh)
    metrics = _metrics(fitted_mask, generated_projection)
    blender_metrics = _metrics(fitted_mask, blender_projection)
    silhouette_path = output_dir / "authority_mesh_glb_silhouette.png"
    blender_silhouette_path = output_dir / "authority_mesh_blender_import_silhouette.png"
    Image.fromarray(np.where(generated_projection, 255, 0).astype(np.uint8), "L").save(silhouette_path)
    Image.fromarray(np.where(blender_projection, 255, 0).astype(np.uint8), "L").save(blender_silhouette_path)
    gates = _gate_results(
        metrics,
        blender_metrics,
        reload_audit,
        len(faces),
        component_count,
        blender_bounds_delta,
        height_to_planform_ratio,
        geometry_metrics,
        edge_audits_agree,
    )

    preview_mask, preview_top, preview_bottom, preview_centre = _resample_geometry_fields(
        fitted_mask, top_work, bottom_work, centre_work, PREVIEW_GRID_SIZE
    )
    preview_vertices, preview_uvs, preview_faces, preview_face_kinds = _build_mesh(
        preview_mask, preview_top, preview_bottom, preview_centre
    )
    top_preview = output_dir / "authority_mesh_preview_top.png"
    left_preview = output_dir / "authority_mesh_preview_bank_left.png"
    right_preview = output_dir / "authority_mesh_preview_bank_right.png"
    _software_render(
        preview_vertices, preview_uvs, preview_faces, preview_face_kinds, texture, 0, 0, top_preview
    )
    _software_render(
        preview_vertices, preview_uvs, preview_faces, preview_face_kinds, texture, -18, 20, left_preview
    )
    _software_render(
        preview_vertices, preview_uvs, preview_faces, preview_face_kinds, texture, 18, 20, right_preview
    )
    contact_sheet = output_dir / "authority_mesh_generation_contact_sheet.png"
    _contact_sheet(rgba, [top_preview, left_preview, right_preview], contact_sheet)

    report = {
        "schemaVersion": "skyforge.authority-mesh-generation.v2",
        "generator": {"id": GENERATOR_ID, "version": GENERATOR_VERSION},
        "source": {
            "authorityFile": authority_path.name,
            "authoritySha256": _sha256(authority_path),
            "maskMethod": mask_method,
            "sourceBounds": list(source_bbox),
            "authorityPixelsConsumed": True,
            "geometryInputs": [
                "foreground_planform_mask",
                "distance_to_silhouette",
                "row_relative_lateral_coordinate",
                "longitudinal_coordinate",
            ],
            "holeFilter": hole_filter,
            "albedoGeometryInfluence": mask_method != "alpha_threshold_16",
            "albedoGeometryInfluenceScope": (
                "none" if mask_method == "alpha_threshold_16" else "foreground_mask_derivation_only"
            ),
        },
        "mesh": {
            "path": glb_path.name,
            "sha256": _sha256(glb_path),
            "intermediateObjPath": obj_path.name,
            "intermediateObjSha256": _sha256(obj_path),
            "materialPath": mtl_path.name,
            "texturePath": texture_path.name,
            "vertexCount": len(vertices),
            "triangleCount": len(faces),
            "projectedTriangleCount": projected_triangle_count,
            "selectedMeshGridSize": selected_mesh_grid_size,
            "componentCount": component_count,
            "componentCountSource": "independent_reloaded_glb_split",
            **reload_audit,
            "sourceEdgeAudit": source_audit,
            "reloadedGlbEdgeAudit": reload_audit,
            "sourceReloadEdgeAuditAgreement": edge_audits_agree,
            "watertightByEdgeIncidence": (
                reload_audit["boundaryEdgeCount"] == 0 and reload_audit["nonManifoldEdgeCount"] == 0
            ),
            "glbReloadWatertight": bool(reloaded_glb.is_watertight),
            "glbReloadWindingConsistent": bool(reloaded_glb.is_winding_consistent),
            "coordinateContract": {
                "internalTargetAxes": {"right": "+X", "forward": "+Y", "up": "+Z"},
                "glTFSemanticAxes": {"right": "+X", "up": "+Y", "forward": "-Z"},
                "encoding": "target_xyz_to_gltf_x_z_neg_y",
                "blenderImportReconstruction": "gltf_xyz_to_blender_x_neg_z_y",
                "blenderImportBoundsDelta": round(blender_bounds_delta, 9),
                "blenderImportHeightToPlanformRatio": round(height_to_planform_ratio, 9),
            },
        },
        "geometryMetrics": geometry_metrics,
        "identityMetrics": metrics,
        "blenderImportIdentityMetrics": blender_metrics,
        "identityMetricSource": "target_mesh_and_emulated_blender_gltf_import_top_projection",
        "acceptanceGates": ACCEPTANCE_GATES,
        "gateResults": gates,
        "previews": [
            path.name
            for path in (
                top_preview,
                left_preview,
                right_preview,
                contact_sheet,
                silhouette_path,
                blender_silhouette_path,
            )
        ],
    }
    report_path = output_dir / "authority_mesh_generation_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    texture.close()
    fitted_rgba.close()
    fitted_mask_image.close()
    raw_mask.close()
    rgba.close()
    if not gates["passed"]:
        failed = [name for name, passed in gates["checks"].items() if not passed]
        raise RuntimeError("Authority-to-mesh generation failed strict gates: " + ", ".join(failed))
    return GeneratedMesh(
        mesh_path=glb_path,
        obj_path=obj_path,
        material_path=mtl_path,
        texture_path=texture_path,
        report_path=report_path,
        preview_paths=(
            top_preview,
            left_preview,
            right_preview,
            contact_sheet,
            silhouette_path,
            blender_silhouette_path,
        ),
        report=report,
    )
