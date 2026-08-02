from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .authority_mesh import _largest_component, _rgba_and_mask

MIN_IMAGE_DIMENSION = 256
MIN_FOREGROUND_COVERAGE = 0.04
MAX_FOREGROUND_COVERAGE = 0.86
MIN_EDGE_MARGIN_RATIO = 0.01
MIN_LARGEST_COMPONENT_FRACTION = 0.985
MIN_BILATERAL_SILHOUETTE_IOU = 0.88
MAX_WEIGHTED_CENTERLINE_DRIFT = 0.04
MAX_MAJOR_AXIS_MISALIGNMENT_DEGREES = 15.0
MIN_VERTICAL_SYMMETRY_ADVANTAGE = 0.08
MAX_BILATERAL_COLOR_MEAN_DELTA = 0.12
ALLOWED_SOURCE_KINDS = {"manual_upload", "governed_generated", "cleared_fixture", "fixture"}


class AuthoritySuitabilityError(ValueError):
    """Raised when an image cannot serve as a strict top-down authority."""

    def __init__(self, report: dict[str, Any]):
        self.report = report
        reasons = report.get("reasons") or ["authority suitability checks failed"]
        super().__init__(
            "Authority image rejected before mesh generation: "
            + "; ".join(str(reason) for reason in reasons)
            + ". Use a strict top-down, nose-up, axis-aligned authority image with neutral lighting."
        )


def _largest_component_fraction(mask: np.ndarray) -> tuple[np.ndarray, float]:
    foreground_count = int(mask.sum())
    if foreground_count <= 0:
        raise ValueError("Authority image contains no usable foreground silhouette")
    largest = _largest_component(mask)
    return largest, float(largest.sum() / foreground_count)


def _bilateral_silhouette_iou(crop: np.ndarray) -> float:
    mirrored = np.fliplr(crop)
    union = np.logical_or(crop, mirrored)
    if not union.any():
        return 0.0
    return float(np.logical_and(crop, mirrored).sum() / union.sum())


def _weighted_centerline_drift(mask: np.ndarray, bbox: tuple[int, int, int, int]) -> float:
    x_min, y_min, x_max, y_max = bbox
    width = max(1, x_max - x_min)
    bbox_center = (x_min + x_max - 1) / 2.0
    weighted_drift = 0.0
    total_weight = 0.0
    for y in range(y_min, y_max):
        columns = np.flatnonzero(mask[y])
        if columns.size == 0:
            continue
        row_center = (float(columns[0]) + float(columns[-1])) / 2.0
        row_width = float(columns[-1] - columns[0] + 1)
        weighted_drift += abs(row_center - bbox_center) * row_width
        total_weight += row_width
    if total_weight <= 0:
        return 1.0
    return float((weighted_drift / total_weight) / width)


def _major_axis_misalignment(mask: np.ndarray) -> float:
    y_coords, x_coords = np.nonzero(mask)
    if x_coords.size < 3:
        return 90.0
    centered = np.column_stack((x_coords - x_coords.mean(), y_coords - y_coords.mean()))
    covariance = np.cov(centered, rowvar=False)
    _, eigenvectors = np.linalg.eigh(covariance)
    vector = eigenvectors[:, -1]
    norm = float(np.linalg.norm(vector))
    if norm <= 0:
        return 90.0
    angle_from_vertical = math.degrees(math.acos(min(1.0, abs(float(vector[1])) / norm)))
    return float(min(angle_from_vertical, abs(90.0 - angle_from_vertical)))


def _bilateral_color_delta(
    rgba: Image.Image,
    mask: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> float:
    x_min, y_min, x_max, y_max = bbox
    pixels = np.asarray(rgba.convert("RGB"), dtype=np.float32)[y_min:y_max, x_min:x_max] / 255.0
    crop_mask = mask[y_min:y_max, x_min:x_max]
    overlap = np.logical_and(crop_mask, np.fliplr(crop_mask))
    if not overlap.any():
        return 1.0
    delta = np.abs(pixels - np.fliplr(pixels)).mean(axis=2)
    return float(delta[overlap].mean())


def analyze_authority_suitability(
    path: Path,
    *,
    source_kind: str,
    lineage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return deterministic evidence that an image is a usable top-down authority.

    v0.7.1 supports bilateral, nose-up air-moving craft only.  This is intentionally
    conservative: a false rejection is preferable to silently converting a beauty
    perspective into an apparently valid mesh.
    """
    if source_kind not in ALLOWED_SOURCE_KINDS:
        raise ValueError(f"Unsupported authority source kind: {source_kind}")

    with Image.open(path) as source:
        width, height = source.size
    rgba, raw_mask_image, mask_method = _rgba_and_mask(path)
    raw_mask = np.asarray(raw_mask_image, dtype=np.uint8) >= 128
    mask, component_fraction = _largest_component_fraction(raw_mask)
    y_coords, x_coords = np.nonzero(mask)
    x_min = int(x_coords.min())
    y_min = int(y_coords.min())
    x_max = int(x_coords.max()) + 1
    y_max = int(y_coords.max()) + 1
    bbox = (x_min, y_min, x_max, y_max)
    crop = mask[y_min:y_max, x_min:x_max]
    coverage = float(mask.sum() / (width * height))
    margins = {
        "left": x_min / width,
        "right": (width - x_max) / width,
        "top": y_min / height,
        "bottom": (height - y_max) / height,
    }
    symmetry_iou = _bilateral_silhouette_iou(crop)
    centerline_drift = _weighted_centerline_drift(mask, bbox)
    horizontal_symmetry_iou = _bilateral_silhouette_iou(crop.T)
    symmetry_advantage = symmetry_iou - horizontal_symmetry_iou
    axis_misalignment = _major_axis_misalignment(mask)
    color_delta = _bilateral_color_delta(rgba, mask, bbox)

    failures: list[dict[str, str]] = []

    def fail(code: str, message: str) -> None:
        failures.append({"code": code, "message": message})

    if min(width, height) < MIN_IMAGE_DIMENSION:
        fail(
            "image_too_small",
            f"image is too small ({width}x{height}; minimum dimension {MIN_IMAGE_DIMENSION})",
        )
    if not MIN_FOREGROUND_COVERAGE <= coverage <= MAX_FOREGROUND_COVERAGE:
        fail(
            "foreground_coverage",
            f"foreground coverage {coverage:.3f} is outside {MIN_FOREGROUND_COVERAGE:.2f}–{MAX_FOREGROUND_COVERAGE:.2f}",
        )
    if min(margins.values()) < MIN_EDGE_MARGIN_RATIO:
        fail(
            "edge_margin",
            f"craft is clipped or too close to an edge (minimum margin {min(margins.values()):.3f}; required {MIN_EDGE_MARGIN_RATIO:.2f})",
        )
    if component_fraction < MIN_LARGEST_COMPONENT_FRACTION:
        fail(
            "fragmented_foreground",
            f"foreground is fragmented (largest component {component_fraction:.3f}; required {MIN_LARGEST_COMPONENT_FRACTION:.3f})",
        )
    if symmetry_iou < MIN_BILATERAL_SILHOUETTE_IOU:
        fail(
            "perspective_or_asymmetric_planform",
            f"silhouette is not a bilateral top-down planform (mirror IoU {symmetry_iou:.3f}; required {MIN_BILATERAL_SILHOUETTE_IOU:.2f})",
        )
    if centerline_drift > MAX_WEIGHTED_CENTERLINE_DRIFT:
        fail(
            "unstable_centerline",
            f"silhouette centerline drifts like a perspective view ({centerline_drift:.3f}; maximum {MAX_WEIGHTED_CENTERLINE_DRIFT:.2f})",
        )
    if symmetry_advantage < MIN_VERTICAL_SYMMETRY_ADVANTAGE:
        fail(
            "not_nose_up",
            f"left/right symmetry does not dominate top/bottom symmetry like a nose-up planform ({symmetry_advantage:.3f}; required {MIN_VERTICAL_SYMMETRY_ADVANTAGE:.2f})",
        )
    if axis_misalignment > MAX_MAJOR_AXIS_MISALIGNMENT_DEGREES:
        fail(
            "diagonal_presentation",
            f"craft is diagonally presented ({axis_misalignment:.1f} degrees from an image axis; maximum {MAX_MAJOR_AXIS_MISALIGNMENT_DEGREES:.0f})",
        )
    if color_delta > MAX_BILATERAL_COLOR_MEAN_DELTA:
        fail(
            "asymmetric_appearance",
            f"left/right appearance differs like perspective lighting or visible side faces ({color_delta:.3f}; maximum {MAX_BILATERAL_COLOR_MEAN_DELTA:.2f})",
        )

    checks = {
        "minimumImageSize": min(width, height) >= MIN_IMAGE_DIMENSION,
        "foregroundCoverage": MIN_FOREGROUND_COVERAGE <= coverage <= MAX_FOREGROUND_COVERAGE,
        "edgeMargins": min(margins.values()) >= MIN_EDGE_MARGIN_RATIO,
        "singleForegroundComponent": component_fraction >= MIN_LARGEST_COMPONENT_FRACTION,
        "bilateralPlanform": symmetry_iou >= MIN_BILATERAL_SILHOUETTE_IOU,
        "stableCenterline": centerline_drift <= MAX_WEIGHTED_CENTERLINE_DRIFT,
        "noseUpPlanformOrientation": symmetry_advantage >= MIN_VERTICAL_SYMMETRY_ADVANTAGE,
        "axisAligned": axis_misalignment <= MAX_MAJOR_AXIS_MISALIGNMENT_DEGREES,
        "neutralBilateralAppearance": color_delta <= MAX_BILATERAL_COLOR_MEAN_DELTA,
    }
    return {
        "schemaVersion": "skyforge.authority-suitability.v1",
        "validatorVersion": "0.7.1",
        "sourceKind": source_kind,
        "lineage": lineage,
        "image": {
            "width": width,
            "height": height,
            "maskMethod": mask_method,
            "foregroundBoundingBox": [x_min, y_min, x_max, y_max],
            "foregroundCoverage": round(coverage, 6),
            "edgeMarginRatios": {key: round(value, 6) for key, value in margins.items()},
            "largestComponentFraction": round(component_fraction, 6),
        },
        "metrics": {
            "bilateralSilhouetteIoU": round(symmetry_iou, 6),
            "weightedCenterlineDrift": round(centerline_drift, 6),
            "horizontalMirrorIoU": round(horizontal_symmetry_iou, 6),
            "verticalSymmetryAdvantage": round(symmetry_advantage, 6),
            "majorAxisMisalignmentDegrees": round(axis_misalignment, 6),
            "bilateralColorMeanDelta": round(color_delta, 6),
        },
        "thresholds": {
            "minimumImageDimension": MIN_IMAGE_DIMENSION,
            "foregroundCoverageMinimum": MIN_FOREGROUND_COVERAGE,
            "foregroundCoverageMaximum": MAX_FOREGROUND_COVERAGE,
            "minimumEdgeMarginRatio": MIN_EDGE_MARGIN_RATIO,
            "minimumLargestComponentFraction": MIN_LARGEST_COMPONENT_FRACTION,
            "minimumBilateralSilhouetteIoU": MIN_BILATERAL_SILHOUETTE_IOU,
            "maximumWeightedCenterlineDrift": MAX_WEIGHTED_CENTERLINE_DRIFT,
            "minimumVerticalSymmetryAdvantage": MIN_VERTICAL_SYMMETRY_ADVANTAGE,
            "maximumMajorAxisMisalignmentDegrees": MAX_MAJOR_AXIS_MISALIGNMENT_DEGREES,
            "maximumBilateralColorMeanDelta": MAX_BILATERAL_COLOR_MEAN_DELTA,
        },
        "checks": checks,
        "failures": failures,
        "reasons": [item["message"] for item in failures],
        "passed": all(checks.values()),
    }


def require_authority_suitability(
    path: Path,
    *,
    source_kind: str,
    lineage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = analyze_authority_suitability(path, source_kind=source_kind, lineage=lineage)
    if not report["passed"]:
        raise AuthoritySuitabilityError(report)
    return report
