from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

CROSS_VIEW_SCHEMA_VERSION = "skyforge.cross-view-consistency.v1"
CROSS_VIEW_METHOD = "deterministic_alpha_or_border_luminance_threshold_ensemble"
CROSS_VIEW_ASPECT_TOLERANCE_PPM = 150_000
CENTER_OFFSET_TOLERANCE_PPM = 50_000
ASPECT_STABILITY_TOLERANCE_PPM = 150_000
BBOX_DIMENSION_STABILITY_TOLERANCE_PPM = 100_000
THRESHOLDS = (8, 16, 24, 40, 60, 80)
VIEW_ORDER = ("top", "front", "right")
CAMERA_DECLARATION_PASS = "measured_orthographic_cross_view_consistency_pass"


class CrossViewError(ValueError):
    """Raised when deterministic cross-view geometry cannot be trusted."""


def _median(values: list[int]) -> int:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2


def _border_median(image: Image.Image) -> int:
    width, height = image.size
    border = (
        list(image.crop((0, 0, width, 1)).getdata())
        + list(image.crop((0, height - 1, width, height)).getdata())
        + list(image.crop((0, 0, 1, height)).getdata())
        + list(image.crop((width - 1, 0, width, height)).getdata())
    )
    return _median([int(value) for value in border])


def _mask_for_threshold(image: Image.Image, threshold: int) -> Image.Image:
    if "A" in image.getbands():
        alpha = image.getchannel("A")
        if alpha.getextrema()[0] < 255:
            return alpha.point(lambda value: 255 if value >= threshold else 0)
    luminance = image.convert("L")
    low, high = luminance.getextrema()
    if low == high:
        raise CrossViewError("Uniform authority image cannot produce a valid silhouette")
    background = _border_median(luminance)
    return luminance.point(lambda value: 255 if abs(value - background) >= threshold else 0)


def _bbox_record(image: Image.Image, threshold: int) -> dict[str, Any]:
    mask = _mask_for_threshold(image, threshold)
    bbox = mask.getbbox()
    if bbox is None:
        raise CrossViewError(f"Threshold {threshold} produced empty foreground")
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    foreground_pixels = mask.histogram()[255]
    minimum_pixels = max(16, image.width * image.height // 10_000)
    if width < 4 or height < 4 or foreground_pixels < minimum_pixels:
        raise CrossViewError(f"Threshold {threshold} produced foreground too small for reliable measurement")
    if left == 0 and top == 0 and right == image.width and bottom == image.height:
        raise CrossViewError(f"Threshold {threshold} produced a degenerate full-canvas foreground")
    horizontal = abs((left + right) - image.width) * 1_000_000 // image.width
    vertical = abs((top + bottom) - image.height) * 1_000_000 // image.height
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": width,
        "height": height,
        "foregroundPixels": foreground_pixels,
        "canvasWidth": image.width,
        "canvasHeight": image.height,
        "centerOffsetPpm": {"horizontal": horizontal, "vertical": vertical},
    }


def aspect_mismatch_ppm(boxes: dict[str, dict[str, Any]]) -> int:
    top = boxes["top"]
    front = boxes["front"]
    right = boxes["right"]
    lhs = top["width"] * right["width"] * front["height"]
    rhs = top["height"] * right["height"] * front["width"]
    if rhs <= 0:
        raise CrossViewError("Cross-view aspect denominator is not positive")
    return abs(lhs - rhs) * 1_000_000 // rhs


def classify_measurement(
    *, mismatch_ppm: int, min_mismatch_ppm: int, max_mismatch_ppm: int,
    maximum_dimension_spread_ppm: int, maximum_center_offset_ppm: int,
) -> str:
    stable = (
        max_mismatch_ppm - min_mismatch_ppm <= ASPECT_STABILITY_TOLERANCE_PPM
        and maximum_dimension_spread_ppm <= BBOX_DIMENSION_STABILITY_TOLERANCE_PPM
    )
    return "PASS" if (
        mismatch_ppm <= CROSS_VIEW_ASPECT_TOLERANCE_PPM
        and maximum_center_offset_ppm <= CENTER_OFFSET_TOLERANCE_PPM
        and stable
    ) else "FAIL"


def measure_cross_view(paths: dict[str, Path]) -> dict[str, Any]:
    if tuple(paths) != VIEW_ORDER:
        raise CrossViewError("Cross-view inputs must be exactly top, front, right in order")
    images: dict[str, Image.Image] = {}
    try:
        for role, path in paths.items():
            try:
                image = Image.open(path)
                image.load()
            except Exception as exc:
                raise CrossViewError(f"Malformed {role} authority image") from exc
            images[role] = image

        samples = []
        dimension_values: dict[str, dict[str, list[int]]] = {
            role: {"width": [], "height": []} for role in VIEW_ORDER
        }
        maximum_center_offset = 0
        for threshold in THRESHOLDS:
            boxes = {role: _bbox_record(images[role], threshold) for role in VIEW_ORDER}
            mismatch = aspect_mismatch_ppm(boxes)
            for role, box in boxes.items():
                dimension_values[role]["width"].append(box["width"])
                dimension_values[role]["height"].append(box["height"])
                maximum_center_offset = max(
                    maximum_center_offset,
                    box["centerOffsetPpm"]["horizontal"],
                    box["centerOffsetPpm"]["vertical"],
                )
            samples.append({"threshold": threshold, "aspectMismatchPpm": mismatch, "boundingBoxes": boxes})

        mismatches = [sample["aspectMismatchPpm"] for sample in samples]
        dimension_spreads: dict[str, dict[str, int]] = {}
        maximum_dimension_spread = 0
        for role in VIEW_ORDER:
            dimension_spreads[role] = {}
            for dimension in ("width", "height"):
                values = dimension_values[role][dimension]
                spread = (max(values) - min(values)) * 1_000_000 // max(values)
                dimension_spreads[role][dimension] = spread
                maximum_dimension_spread = max(maximum_dimension_spread, spread)

        median_mismatch = _median(mismatches)
        representative = samples[len(samples) // 2 - 1]
        result = classify_measurement(
            mismatch_ppm=median_mismatch,
            min_mismatch_ppm=min(mismatches),
            max_mismatch_ppm=max(mismatches),
            maximum_dimension_spread_ppm=maximum_dimension_spread,
            maximum_center_offset_ppm=maximum_center_offset,
        )
        return {
            "schemaVersion": CROSS_VIEW_SCHEMA_VERSION,
            "method": CROSS_VIEW_METHOD,
            "aspectTolerancePpm": CROSS_VIEW_ASPECT_TOLERANCE_PPM,
            "centerTolerancePpm": CENTER_OFFSET_TOLERANCE_PPM,
            "stabilityRule": {
                "allThresholdsRequired": True,
                "aspectMismatchRangeTolerancePpm": ASPECT_STABILITY_TOLERANCE_PPM,
                "bboxDimensionRangeTolerancePpm": BBOX_DIMENSION_STABILITY_TOLERANCE_PPM,
            },
            "measuredAspectMismatchPpm": median_mismatch,
            "minAspectMismatchPpm": min(mismatches),
            "maxAspectMismatchPpm": max(mismatches),
            "maximumDimensionSpreadPpm": maximum_dimension_spread,
            "dimensionSpreadsPpm": dimension_spreads,
            "maximumCenterOffsetPpm": maximum_center_offset,
            "headlineMetricSource": "integer_median_of_thresholdSamples.aspectMismatchPpm",
            "fixedThresholdExemplarThreshold": representative["threshold"],
            "fixedThresholdExemplarBoundingBoxes": representative["boundingBoxes"],
            "fixedThresholdExemplarCenterOffsetsPpm": {
                role: representative["boundingBoxes"][role]["centerOffsetPpm"] for role in VIEW_ORDER
            },
            "thresholdsUsed": list(THRESHOLDS),
            "thresholdSamples": samples,
            "result": result,
        }
    finally:
        for image in images.values():
            image.close()


def require_cross_view_consistency(paths: dict[str, Path]) -> dict[str, Any]:
    record = measure_cross_view(paths)
    if record["result"] != "PASS":
        raise CrossViewError(
            "Cross-view geometric consistency failed: "
            f"median mismatch {record['measuredAspectMismatchPpm']} ppm; "
            f"maximum center offset {record['maximumCenterOffsetPpm']} ppm; "
            f"maximum dimension spread {record['maximumDimensionSpreadPpm']} ppm"
        )
    return record
