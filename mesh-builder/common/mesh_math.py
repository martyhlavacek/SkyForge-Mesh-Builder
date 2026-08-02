from __future__ import annotations

import math
import re
from typing import Iterable

JOB_ID_RE = re.compile(r"^[A-Za-z0-9._-]+-[0-9a-f]{8}$")
VALID_AXES = {"+X", "-X", "+Y", "-Y", "+Z", "-Z"}
BASE_WORLD_SPAN = 5.5

# Calibrated from the CR-0003 fallback-fixture sweep:
# 5 profiles × pitches {0, 20, 36} × banks {-18, 0, 18}.
# The retained CR-0003 sweep included temporary review effects, so the resulting
# frame is conservative. Runtime effects are disabled in v0.3.1.
CANONICAL_ORTHO_SWEEP_MAX_REQUIRED = 8.36418
CANONICAL_ORTHO_SWEEP_PROFILE_SCALE = 1.15
CANONICAL_ORTHO_SWEEP_PROFILE_COUNT = 5
CANONICAL_ORTHO_SWEEP_PROFILE_DIGEST = "ae41ec0079105c99d559077e2679aca98134fe864093248e84400bb781e5e3bb"
CANONICAL_HEIGHT_TO_PLANFORM_MAX = 0.575
CANONICAL_HEIGHT_BINDING_PITCH_DEGREES = 36
CANONICAL_ORTHO_REQUIRED_MARGIN = round(
    CANONICAL_ORTHO_SWEEP_MAX_REQUIRED / (BASE_WORLD_SPAN * CANONICAL_ORTHO_SWEEP_PROFILE_SCALE), 6
)
CANONICAL_ORTHO_MARGIN = 1.40


def clamp_float(value: object, minimum: float, maximum: float, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return min(max(number, minimum), maximum)


def clamp_int(value: object, minimum: int, maximum: int, field: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    return min(max(number, minimum), maximum)


def validate_orientation(forward_axis: str, up_axis: str) -> tuple[str, str]:
    if forward_axis not in VALID_AXES:
        raise ValueError("forwardAxis is invalid")
    if up_axis not in VALID_AXES:
        raise ValueError("upAxis is invalid")
    if forward_axis[-1] == up_axis[-1]:
        raise ValueError("forwardAxis and upAxis must use different dimensions")
    return forward_axis, up_axis


def target_span(profile_scale: float, base_span: float = BASE_WORLD_SPAN) -> float:
    scale = float(profile_scale)
    if scale <= 0:
        raise ValueError("profile scale must be positive")
    return base_span * scale


def canonical_ortho_scale(
    maximum_profile_scale: float,
    *,
    base_span: float = BASE_WORLD_SPAN,
    margin: float = CANONICAL_ORTHO_MARGIN,
) -> float:
    """Return one pinned orthographic frame shared by every craft profile.

    The frame is derived from the largest governed profile rather than refitted to
    each craft. The margin is calibrated from a measured fixture sweep instead of
    being inferred from one unbanked planform.
    """
    if maximum_profile_scale <= 0:
        raise ValueError("maximum profile scale must be positive")
    if margin <= 1:
        raise ValueError("canonical ortho margin must be greater than one")
    return round(base_span * float(maximum_profile_scale) * float(margin), 6)


def canonical_frame_calibration(
    maximum_profile_scale: float,
    profile_count: int = CANONICAL_ORTHO_SWEEP_PROFILE_COUNT,
    profile_digest: str = CANONICAL_ORTHO_SWEEP_PROFILE_DIGEST,
) -> dict[str, object]:
    if abs(float(maximum_profile_scale) - CANONICAL_ORTHO_SWEEP_PROFILE_SCALE) > 1e-9:
        raise RuntimeError(
            "Canonical frame evidence is invalid for the current maximum profile scale; "
            "re-run the calibration sweep"
        )
    if int(profile_count) != CANONICAL_ORTHO_SWEEP_PROFILE_COUNT:
        raise RuntimeError(
            "Canonical frame evidence is invalid for the current profile count; re-run the calibration sweep"
        )
    if profile_digest != CANONICAL_ORTHO_SWEEP_PROFILE_DIGEST:
        raise RuntimeError(
            "Canonical frame evidence is not bound to the current craft profile file; re-run the calibration sweep"
        )
    chosen_scale = canonical_ortho_scale(maximum_profile_scale)
    headroom = chosen_scale - CANONICAL_ORTHO_SWEEP_MAX_REQUIRED
    return {
        "method": "conservative_CR0003_profile_frame_sweep",
        "evidence": "docs/MBS-CR-0003_evidence/probe_canonical_frame_sweep.py",
        "profiles": CANONICAL_ORTHO_SWEEP_PROFILE_COUNT,
        "profileDigest": CANONICAL_ORTHO_SWEEP_PROFILE_DIGEST,
        "pitchesDegrees": [0, 20, 36],
        "banksDegrees": [-18, 0, 18],
        "runtimeEffectsEnabled": False,
        "measuredMaximumRequiredOrthoScale": CANONICAL_ORTHO_SWEEP_MAX_REQUIRED,
        "measuredRequiredMargin": CANONICAL_ORTHO_REQUIRED_MARGIN,
        "chosenMargin": CANONICAL_ORTHO_MARGIN,
        "canonicalOrthoScale": chosen_scale,
        "fixtureHeadroomWorldUnits": round(headroom, 6),
        "fixtureHeadroomFraction": round(headroom / chosen_scale, 6),
        "maximumHeightToPlanformRatio": CANONICAL_HEIGHT_TO_PLANFORM_MAX,
        "heightEnvelopeBindingPitchDegrees": CANONICAL_HEIGHT_BINDING_PITCH_DEGREES,
    }


def projected_pixel_span(world_span: float, ortho_scale: float, resolution: int) -> float:
    if world_span < 0:
        raise ValueError("world span must not be negative")
    if ortho_scale <= 0 or resolution <= 0:
        raise ValueError("ortho scale and resolution must be positive")
    return float(world_span) / float(ortho_scale) * int(resolution)


def is_valid_job_id(job_id: str) -> bool:
    return bool(JOB_ID_RE.fullmatch(job_id))


def all_within(values: Iterable[float], minimum: float, maximum: float) -> bool:
    return all(minimum <= value <= maximum for value in values)
