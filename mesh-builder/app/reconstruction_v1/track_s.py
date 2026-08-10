from __future__ import annotations

import hashlib
from collections import deque
from typing import Any, Callable

import numpy as np
from PIL import Image

from common.canonical_json import canonicalize

from .authorization import FIXED_REQUEST, ContractSnapshot
from .provider import AuthorizationError
from .quarantine import assert_reconstruction_hashes_eligible, quarantine_digest

TRACK_S_POLICY_SCHEMA = "skyforge.track-s-preregistration-policy.v1"
TRACK_S_RUN_SCHEMA = "skyforge.track-s-run-preregistration.v1"
TRACK_S_COST_SCHEMA = "skyforge.track-s-cost-governance.v1"
TRACK_S_MEASUREMENT_SCHEMA = "skyforge.track-s-measurement-spec.v1"
TRACK_S_DECISION_SCHEMA = "skyforge.track-s-experiment-decision.v1"
VALIDATION_TARGET_ROLE = "approved_top_authority_validation_target"
APPROVED_TOP_SHA256 = "7009a2b685fd170c8fac4fad683cfa68805b63629b1b49815e59770060c24c49"
FAILED_TASK_RESOLVED = frozenset({"CHARGED", "NOT_CHARGED", "CONDITIONAL"})
DECISIONS = frozenset({"CONTINUE_SINGLE_VIEW", "ESCALATE_TWO_VIEW_ELIGIBLE", "ABORT_MESHY"})

MEASUREMENT_SPEC: dict[str, Any] = {
    "schemaVersion": TRACK_S_MEASUREMENT_SCHEMA,
    "measurementSource": "independently_reloaded_glb_blender_5_2_lts",
    "requiredMeasurements": [
        "glbExists",
        "glbSha256",
        "glbHashMatches",
        "glbParserValid",
        "blenderReloadSucceeded",
        "vertexCount",
        "faceCount",
        "nonFiniteVertexCount",
        "degenerateFaceCount",
        "manifoldEdgeCount",
        "nonManifoldEdgeCount",
        "connectedComponentCount",
        "watertight",
        "largestComponentVolumeFractionPpm",
        "rawBoundingBoxDeclaredGlbUnits",
        "boundingBoxExtentsMicrounits",
        "perAxisExtentRatiosPpm",
        "topSilhouette",
        "topSilhouetteIou",
        "gameplayMetrics",
        "humanGameplayReadabilityArtifact",
    ],
    "topAlignment": {
        "resolution": [1024, 1024],
        "projection": "exact_orthographic_top_gltf_blender_coordinate_contract",
        "alphaThreshold": 128,
        "allowedRotationsDegrees": [0, 90, 180, 270],
        "rotationTieBreak": "smallest_angle",
        "scale": "isotropic_candidate_fore_aft_bbox_to_target_fore_aft_bbox",
        "translation": "candidate_centroid_to_target_centroid_only",
        "reflection": False,
        "anisotropicScale": False,
        "freeAngleRotation": False,
        "translationSearch": False,
    },
    "hardGates": {
        "blenderReloadRequired": True,
        "minimumVertexCount": 1,
        "minimumFaceCount": 1,
        "maximumNonFiniteVertexCount": 0,
        "maximumDegenerateFaceCount": 0,
        "minimumBoundingBoxExtentUnits": "0.000001",
        "watertightRequired": True,
        "connectedComponentCountInclusive": [1, 16],
        "minimumLargestComponentVolumeFractionPpm": 600000,
        "topSilhouetteNonEmpty": True,
        "gameplaySilhouetteNonEmpty": True,
        "gameplayRenderNotClipped": True,
    },
    "gameplayCamera": {
        "resolution": [64, 64],
        "angleDegrees": 75,
        "projection": "repository_gameplay_camera_orthographic",
        "coordinateConvention": "accepted_gltf_blender_contract",
        "cameraTransform": {
            "azimuthDegrees": 135,
            "elevationDegrees": 75,
            "rollDegrees": 0,
            "lookAt": "reloaded_glb_bounding_box_center",
            "objectOrigin": "reloaded_glb_declared_origin",
            "orthographicScale": "maximum_projected_extent_times_1100000ppm",
        },
        "framing": "full_craft_fixed_margin",
        "marginPpm": 100000,
        "alphaThreshold": 128,
        "minimumForegroundPixels": 128,
        "minimumLargest2dComponentPixelFractionPpm": 800000,
        "clippingAllowed": False,
    },
}

DECISION_RULES: dict[str, Any] = {
    "schemaVersion": "skyforge.track-s-decision-rules.v1",
    "strongSingleViewMinimumIouPpm": 800000,
    "twoViewEligibleMinimumIouPpm": 650000,
    "productionIouFloorPpmUnchanged": 940000,
    "readableValue": "READABLE",
    "unreadableValue": "UNREADABLE",
    "automaticRetryCount": 0,
    "automaticSecondTask": False,
}

PREREGISTRATION_POLICY: dict[str, Any] = {
    "schemaVersion": TRACK_S_POLICY_SCHEMA,
    "inputKind": "single_view_v1",
    "prediction": {
        "expectedOutcome": (
            "reloadable geometry-only gunship with recognizable major volume information; "
            "top-down silhouette expected below unchanged 0.94 production IoU floor"
        ),
        "expectedExploratoryIouRangePpm": [650000, 850000],
        "predictionIsPassBand": False,
    },
    "measurementSpec": MEASUREMENT_SPEC,
    "decisionRules": DECISION_RULES,
    "providerRequest": FIXED_REQUEST,
    "validationTargetRole": VALIDATION_TARGET_ROLE,
    "humanGameplayReadabilityRequired": True,
    "strategyRationale": "information_value_not_per_task_savings",
}


def canonical_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonicalize(value)).hexdigest()


def measurement_spec_digest() -> str:
    return canonical_digest(MEASUREMENT_SPEC)


def decision_rule_digest() -> str:
    return canonical_digest(DECISION_RULES)


def preregistration_policy_digest() -> str:
    return canonical_digest(PREREGISTRATION_POLICY)


def fixed_request_digest() -> str:
    return canonical_digest(FIXED_REQUEST)


def build_cost_governance(
    contract_snapshot: ContractSnapshot,
    *,
    failed_task_charging_disposition: str = "UNRESOLVED",
    failed_task_charging_evidence: str = "retained_contract_does_not_establish_disposition",
) -> dict[str, Any]:
    return {
        "schemaVersion": TRACK_S_COST_SCHEMA,
        "expectedCreditsPerTask": 20,
        "sequentialExperimentCredits": {"oneView": 20, "onePlusTwoView": 40, "onePlusTwoPlusThreeView": 60},
        "cumulativeAuthorizationCap": 20,
        "authorizedTaskCount": 1,
        "automaticRetryCount": 0,
        "automaticSecondTask": False,
        "strategyRationale": "information_value_not_per_task_savings",
        "contractSnapshot": {
            "path": contract_snapshot.path,
            "sha256": contract_snapshot.sha256,
            "verificationDate": contract_snapshot.verification_date,
            "ageHoursFloor": int(contract_snapshot.age_hours),
            "freshnessStatus": contract_snapshot.freshness_status,
        },
        "failedTaskChargingDisposition": failed_task_charging_disposition,
        "failedTaskChargingEvidence": failed_task_charging_evidence,
    }


def validate_cost_governance(record: dict[str, Any], *, require_resolved: bool = True) -> str:
    if record.get("schemaVersion") != TRACK_S_COST_SCHEMA:
        raise AuthorizationError("Track S cost-governance schema is unsupported")
    required = {
        "expectedCreditsPerTask": 20,
        "cumulativeAuthorizationCap": 20,
        "authorizedTaskCount": 1,
        "automaticRetryCount": 0,
        "automaticSecondTask": False,
        "strategyRationale": "information_value_not_per_task_savings",
    }
    if any(record.get(key) != value for key, value in required.items()):
        raise AuthorizationError("Track S cost governance differs from the fixed first-task policy")
    if record.get("sequentialExperimentCredits") != {
        "oneView": 20,
        "onePlusTwoView": 40,
        "onePlusTwoPlusThreeView": 60,
    }:
        raise AuthorizationError("Track S cumulative sequential costs changed")
    disposition = record.get("failedTaskChargingDisposition")
    if require_resolved and disposition not in FAILED_TASK_RESOLVED:
        raise AuthorizationError("Failed/rejected-task charging disposition remains unresolved")
    if disposition in FAILED_TASK_RESOLVED and not record.get("failedTaskChargingEvidence"):
        raise AuthorizationError("Resolved failed-task charging requires bound evidence")
    return canonical_digest(record)


def build_run_preregistration(
    *,
    reconstruction_input_digest: str,
    beauty_sha256: str,
    validation_target_sha256: str,
    validation_target_approval_identity: str,
    candidate_source_commit: str,
    contract_snapshot_digest: str,
    cost_governance_digest: str,
    committed_at_commit: str,
) -> dict[str, Any]:
    assert_reconstruction_hashes_eligible([beauty_sha256])
    record = {
        "schemaVersion": TRACK_S_RUN_SCHEMA,
        "reconstructionInputDigest": reconstruction_input_digest,
        "beautyImageSha256": beauty_sha256,
        "validationTarget": {
            "role": VALIDATION_TARGET_ROLE,
            "sha256": validation_target_sha256,
            "approvalIdentity": validation_target_approval_identity,
            "isReconstructionInput": False,
        },
        "candidateSourceCommit": candidate_source_commit,
        "measurementSpecDigest": measurement_spec_digest(),
        "decisionRuleDigest": decision_rule_digest(),
        "fixedRequestDigest": fixed_request_digest(),
        "contractSnapshotDigest": contract_snapshot_digest,
        "costGovernanceDigest": cost_governance_digest,
        "quarantineDigest": quarantine_digest(),
        "quarantineAttestation": "reconstruction_inputs_checked_and_validation_target_is_separate",
        "committedAtCommit": committed_at_commit,
    }
    record["preregistrationDigest"] = canonical_digest(record)
    return record


def validate_run_preregistration(
    record: dict[str, Any], *, executing_commit: str, is_ancestor: Callable[[str, str], bool]
) -> str:
    if record.get("schemaVersion") != TRACK_S_RUN_SCHEMA:
        raise AuthorizationError("Committed Track S run-specific preregistration is unavailable")
    declared = record.get("preregistrationDigest")
    projection = {key: value for key, value in record.items() if key != "preregistrationDigest"}
    if declared != canonical_digest(projection):
        raise AuthorizationError("Track S run-specific preregistration digest changed")
    if record.get("measurementSpecDigest") != measurement_spec_digest():
        raise AuthorizationError("Track S measurement specification changed after preregistration")
    if record.get("decisionRuleDigest") != decision_rule_digest():
        raise AuthorizationError("Track S decision rules changed after preregistration")
    if record.get("fixedRequestDigest") != fixed_request_digest():
        raise AuthorizationError("Track S fixed request changed after preregistration")
    if record.get("quarantineDigest") != quarantine_digest():
        raise AuthorizationError("Track S quarantine policy changed after preregistration")
    assert_reconstruction_hashes_eligible([record.get("beautyImageSha256", "")])
    commit = record.get("committedAtCommit")
    if not isinstance(commit, str) or not is_ancestor(commit, executing_commit):
        raise AuthorizationError("Track S preregistration is uncommitted or not bound to executing source")
    candidate = record.get("candidateSourceCommit")
    if not isinstance(candidate, str) or not is_ancestor(candidate, executing_commit):
        raise AuthorizationError("Track S candidate source commit is not bound to executing source")
    return declared


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise ValueError("Silhouette is empty")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _centroid(mask: np.ndarray) -> tuple[int, int, int]:
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise ValueError("Silhouette is empty")
    count = len(xs)
    return int(xs.sum()), int(ys.sum()), count


def align_top_silhouettes(candidate: np.ndarray, target: np.ndarray) -> dict[str, Any]:
    if candidate.shape != (1024, 1024) or target.shape != (1024, 1024):
        raise ValueError("Track S top silhouettes must be exactly 1024 x 1024")
    candidate_mask = np.asarray(candidate) >= 128
    target_mask = np.asarray(target) >= 128
    target_bbox = _bbox(target_mask)
    target_centroid = _centroid(target_mask)
    samples = []
    for rotation in (0, 90, 180, 270):
        turns = rotation // 90
        rotated = np.rot90(candidate_mask, k=-turns)
        before_bbox = _bbox(rotated)
        source_height = before_bbox[3] - before_bbox[1]
        target_height = target_bbox[3] - target_bbox[1]
        cropped = rotated[before_bbox[1] : before_bbox[3], before_bbox[0] : before_bbox[2]]
        scaled_width = max(1, (cropped.shape[1] * target_height + source_height // 2) // source_height)
        scaled = np.asarray(
            Image.fromarray((cropped * 255).astype(np.uint8)).resize(
                (scaled_width, target_height), Image.Resampling.NEAREST
            )
        ) >= 128
        canvas = np.zeros((1024, 1024), dtype=bool)
        scaled_centroid = _centroid(scaled)
        target_x_num, target_y_num, target_count = target_centroid
        scaled_x_num, scaled_y_num, scaled_count = scaled_centroid
        target_x = (target_x_num * 2 + target_count) // (2 * target_count)
        target_y = (target_y_num * 2 + target_count) // (2 * target_count)
        scaled_x = (scaled_x_num * 2 + scaled_count) // (2 * scaled_count)
        scaled_y = (scaled_y_num * 2 + scaled_count) // (2 * scaled_count)
        left, top = target_x - scaled_x, target_y - scaled_y
        src_left, src_top = max(0, -left), max(0, -top)
        dst_left, dst_top = max(0, left), max(0, top)
        width = min(scaled.shape[1] - src_left, 1024 - dst_left)
        height = min(scaled.shape[0] - src_top, 1024 - dst_top)
        if width > 0 and height > 0:
            canvas[dst_top : dst_top + height, dst_left : dst_left + width] = scaled[
                src_top : src_top + height, src_left : src_left + width
            ]
        intersection = int(np.logical_and(canvas, target_mask).sum())
        union = int(np.logical_or(canvas, target_mask).sum())
        iou_ppm = intersection * 1_000_000 // union if union else 0
        samples.append(
            {
                "rotationDegrees": rotation,
                "iouPpm": iou_ppm,
                "scaleFactor": {"numerator": target_height, "denominator": source_height},
                "candidateCentroidBefore": {"xNumerator": _centroid(rotated)[0], "yNumerator": _centroid(rotated)[1], "denominator": _centroid(rotated)[2]},
                "candidateCentroidAfter": {"xNumerator": _centroid(canvas)[0], "yNumerator": _centroid(canvas)[1], "denominator": _centroid(canvas)[2]},
                "targetCentroid": {"xNumerator": target_centroid[0], "yNumerator": target_centroid[1], "denominator": target_centroid[2]},
                "candidateBoundingBoxBefore": list(before_bbox),
                "candidateBoundingBoxAfter": list(_bbox(canvas)),
                "targetBoundingBox": list(target_bbox),
            }
        )
    selected = min(samples, key=lambda item: (-item["iouPpm"], item["rotationDegrees"]))
    return {
        "schemaVersion": "skyforge.track-s-top-alignment-result.v1",
        "resolution": [1024, 1024],
        "alphaThreshold": 128,
        "samples": samples,
        "selectedRotationDegrees": selected["rotationDegrees"],
        "selectedIouPpm": selected["iouPpm"],
        "reflectionUsed": False,
        "anisotropicScaleUsed": False,
        "translationSearchUsed": False,
    }


def gameplay_silhouette_metrics(mask: np.ndarray, *, clipped: bool) -> dict[str, Any]:
    if mask.shape != (64, 64):
        raise ValueError("Gameplay silhouette must be exactly 64 x 64")
    binary = np.asarray(mask) >= 128
    foreground = int(binary.sum())
    bbox = list(_bbox(binary)) if foreground else None
    visited = np.zeros_like(binary, dtype=bool)
    components = []
    for y, x in zip(*np.nonzero(binary), strict=False):
        if visited[y, x]:
            continue
        queue = deque([(int(y), int(x))])
        visited[y, x] = True
        count = 0
        while queue:
            cy, cx = queue.popleft()
            count += 1
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < 64 and 0 <= nx < 64 and binary[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((ny, nx))
        components.append(count)
    largest_ppm = max(components, default=0) * 1_000_000 // foreground if foreground else 0
    return {
        "resolution": [64, 64],
        "cameraAngleDegrees": 75,
        "projection": MEASUREMENT_SPEC["gameplayCamera"]["projection"],
        "framing": MEASUREMENT_SPEC["gameplayCamera"]["framing"],
        "marginPpm": 100000,
        "alphaThreshold": 128,
        "foregroundPixelCount": foreground,
        "foregroundOccupancyPpm": foreground * 1_000_000 // 4096,
        "silhouetteBoundingBox": bbox,
        "clipped": clipped,
        "connectedComponentCount2d": len(components),
        "largestComponentPixelFractionPpm": largest_ppm,
    }


def hard_validity_failures(record: dict[str, Any]) -> list[str]:
    sha256 = record.get("glbSha256")
    manifold = record.get("manifoldEdgeCount")
    non_manifold = record.get("nonManifoldEdgeCount")
    raw_bbox = record.get("rawBoundingBoxDeclaredGlbUnits") or {}
    minimum = raw_bbox.get("minimumMicrounits") if isinstance(raw_bbox, dict) else None
    maximum = raw_bbox.get("maximumMicrounits") if isinstance(raw_bbox, dict) else None
    ratios = record.get("perAxisExtentRatiosPpm")
    checks = [
        (record.get("glbExists") is True, "GLB_MISSING"),
        (isinstance(sha256, str) and len(sha256) == 64 and all(c in "0123456789abcdef" for c in sha256), "GLB_SHA256_INVALID"),
        (record.get("glbHashMatches") is True, "GLB_HASH_MISMATCH"),
        (record.get("glbParserValid") is True, "GLB_PARSER_INVALID"),
        (record.get("blenderReloadSucceeded") is True, "BLENDER_RELOAD_FAILED"),
        (record.get("vertexCount", 0) > 0, "EMPTY_VERTICES"),
        (record.get("faceCount", 0) > 0, "EMPTY_FACES"),
        (record.get("nonFiniteVertexCount") == 0, "NONFINITE_VERTICES"),
        (record.get("degenerateFaceCount") == 0, "DEGENERATE_FACES"),
        (type(manifold) is int and manifold >= 0, "MANIFOLD_EDGE_MEASUREMENT"),
        (type(non_manifold) is int and non_manifold >= 0, "NON_MANIFOLD_EDGE_MEASUREMENT"),
        (record.get("watertight") is True, "NON_WATERTIGHT"),
        (1 <= record.get("connectedComponentCount", 0) <= 16, "COMPONENT_COUNT"),
        (record.get("largestComponentVolumeFractionPpm", 0) >= 600000, "LARGEST_COMPONENT_FRACTION"),
        (record.get("topSilhouetteNonEmpty") is True, "EMPTY_TOP_SILHOUETTE"),
    ]
    extents = record.get("boundingBoxExtentsMicrounits") or []
    checks.append((len(extents) == 3 and all(type(item) is int and item > 1 for item in extents), "INVALID_BOUNDING_BOX"))
    checks.append(
        (
            isinstance(minimum, list)
            and isinstance(maximum, list)
            and len(minimum) == len(maximum) == 3
            and len(extents) == 3
            and all(type(item) is int for item in minimum + maximum)
            and all(maximum[index] - minimum[index] == extents[index] for index in range(3)),
            "RAW_BOUNDING_BOX_INVALID",
        )
    )
    checks.append(
        (
            isinstance(ratios, list)
            and len(ratios) == 3
            and all(type(item) is int and item > 0 for item in ratios),
            "EXTENT_RATIOS_INVALID",
        )
    )
    gameplay = record.get("gameplayMetrics") or {}
    checks.extend(
        [
            (gameplay.get("foregroundPixelCount", 0) >= 128, "GAMEPLAY_FOREGROUND"),
            (gameplay.get("clipped") is False, "GAMEPLAY_CLIPPED"),
            (gameplay.get("largestComponentPixelFractionPpm", 0) >= 800000, "GAMEPLAY_COMPONENT_FRACTION"),
        ]
    )
    return [reason for passed, reason in checks if not passed]


def build_human_readability_review(
    *, verdict: str, reviewer: str, reviewed_at: str, artifact_sha256: str
) -> dict[str, Any]:
    if verdict not in {"READABLE", "UNREADABLE"}:
        raise ValueError("Human gameplay readability verdict is invalid")
    if not reviewer or not reviewed_at or len(artifact_sha256) != 64:
        raise ValueError("Human gameplay readability review is not artifact-bound")
    record = {
        "schemaVersion": "skyforge.track-s-human-gameplay-readability.v1",
        "verdict": verdict,
        "reviewer": reviewer,
        "reviewedAt": reviewed_at,
        "artifactSha256": artifact_sha256,
    }
    record["reviewDigest"] = canonical_digest(record)
    return record


def decide_experiment(
    *, top_iou_ppm: int, measurement_record: dict[str, Any], human_readability: dict[str, Any]
) -> dict[str, Any]:
    review_projection = {key: value for key, value in human_readability.items() if key != "reviewDigest"}
    if human_readability.get("reviewDigest") != canonical_digest(review_projection):
        raise ValueError("Human gameplay readability review digest changed")
    verdict = human_readability.get("verdict")
    failures = hard_validity_failures(measurement_record)
    reasons = list(failures)
    if verdict == "UNREADABLE":
        reasons.append("HUMAN_GAMEPLAY_UNREADABLE")
    elif verdict != "READABLE":
        reasons.append("HUMAN_GAMEPLAY_REVIEW_MISSING")
    if failures or verdict != "READABLE" or top_iou_ppm < 650000:
        if top_iou_ppm < 650000:
            reasons.append("TOP_IOU_BELOW_0_65")
        decision = "ABORT_MESHY"
    elif top_iou_ppm >= 800000:
        decision = "CONTINUE_SINGLE_VIEW"
    else:
        decision = "ESCALATE_TWO_VIEW_ELIGIBLE"
    record = {
        "schemaVersion": TRACK_S_DECISION_SCHEMA,
        "decision": decision,
        "topIouPpm": top_iou_ppm,
        "humanGameplayReadability": human_readability,
        "reasonCodes": sorted(set(reasons)),
        "createsProviderTask": False,
        "authorizesAnotherTask": False,
        "automaticRetryCount": 0,
    }
    if decision not in DECISIONS:
        raise AssertionError("Unknown Track S decision")
    record["decisionDigest"] = canonical_digest(record)
    return record
