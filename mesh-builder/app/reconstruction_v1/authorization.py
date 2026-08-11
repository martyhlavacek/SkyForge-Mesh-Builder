from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from common.canonical_json import canonicalize

from .provider import ESTIMATED_CREDITS, ArtifactHostPolicy, AuthorizationError
from .reconstruction_input import (
    SINGLE_VIEW_KIND,
    human_approval,
    reconstruction_input_reference,
    validate_reconstruction_input,
)

AUTHORIZATION_SCHEMA_VERSION = "skyforge.meshy-pilot-authorization.v1"
CONTRACT_FRESHNESS_HOURS = 24
FIXED_REQUEST = {
    "ai_model": "meshy-6",
    "should_texture": False,
    "should_remesh": False,
    "image_enhancement": False,
    "auto_size": False,
    "target_formats": ["glb"],
}


@dataclass(frozen=True)
class ContractSnapshot:
    path: str
    verification_date: str
    sha256: str
    age_hours: float
    freshness_status: str

    @property
    def fresh(self) -> bool:
        return self.freshness_status == "FRESH"


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise AuthorizationError("Authorization projection prohibits floating-point values")
    if isinstance(value, dict):
        for item in value.values():
            _reject_floats(item)
    elif isinstance(value, list):
        for item in value:
            _reject_floats(item)


def load_contract_snapshot(repository_root: Path, relative_path: str, *, now: datetime | None = None) -> ContractSnapshot:
    path = (repository_root / relative_path).resolve()
    try:
        path.relative_to(repository_root.resolve())
    except ValueError as exc:
        raise AuthorizationError("Contract snapshot path escapes the repository") from exc
    payload = path.read_bytes()
    text = payload.decode("utf-8")
    match = re.search(r"Retrieved at `([^`]+)`", text)
    if not match:
        raise AuthorizationError("Contract snapshot does not contain its verification date")
    verified = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
    current = now or datetime.now(UTC)
    age_hours = (current - verified).total_seconds() / 3600
    status = "FRESH" if 0 <= age_hours <= CONTRACT_FRESHNESS_HOURS else "STALE"
    return ContractSnapshot(
        path=relative_path,
        verification_date=match.group(1),
        sha256=hashlib.sha256(payload).hexdigest(),
        age_hours=age_hours,
        freshness_status=status,
    )


def producer_binding_digest(package_root: Path) -> str:
    binding = json.loads((package_root / "PRODUCER_SOURCE_BINDING.json").read_text(encoding="utf-8"))
    digest = binding.get("treeManifestSha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise AuthorizationError("Producer source binding digest is unavailable")
    return digest


def build_authorization_projection(
    package_root: Path,
    bundle_root: Path,
    bundle: dict[str, Any],
    *,
    contract_snapshot: ContractSnapshot,
    artifact_host_policy: ArtifactHostPolicy,
    estimated_credits: int = ESTIMATED_CREDITS,
    maximum_credits: int = ESTIMATED_CREDITS,
    request_body: dict[str, Any] | None = None,
    track_s_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bundle_digest = validate_reconstruction_input(bundle_root, bundle, require_approved=True)
    input_reference = reconstruction_input_reference(bundle_root, bundle)
    resolved_request = dict(FIXED_REQUEST if request_body is None else request_body)
    if resolved_request != FIXED_REQUEST:
        raise AuthorizationError("Pilot request options differ from the fixed geometry-only contract")
    if type(estimated_credits) is not int or type(maximum_credits) is not int:
        raise AuthorizationError("Pilot credit values must be integers")
    if estimated_credits != ESTIMATED_CREDITS or maximum_credits != ESTIMATED_CREDITS:
        raise AuthorizationError("Pilot credit estimate and cap must both equal exactly 20")
    approval = human_approval(bundle)
    if not approval.get("approvedAt") or not approval.get("workflowId"):
        raise AuthorizationError("Human bundle approval record is unavailable")
    projection = {
        "schemaVersion": AUTHORIZATION_SCHEMA_VERSION,
        "inputKind": input_reference["inputKind"],
        "reconstructionInputDigest": input_reference["reconstructionInputDigest"],
        "reconstructionInputSourceSha256s": input_reference["sourceSha256s"],
        "bundleDigest": bundle_digest,
        "profileId": input_reference["profileId"],
        "requestBody": resolved_request,
        "estimatedCredits": estimated_credits,
        "maximumCredits": maximum_credits,
        "artifactHostPolicy": {"contractVersion": artifact_host_policy.contract_version},
        "contractSnapshot": {
            "sha256": contract_snapshot.sha256,
            "verificationDate": contract_snapshot.verification_date,
        },
        "producerSourceBindingDigest": producer_binding_digest(package_root),
        "humanApproval": {
            "approvedAt": approval["approvedAt"],
            "workflowId": approval["workflowId"],
        },
    }
    if input_reference["inputKind"] == SINGLE_VIEW_KIND:
        from .track_s import (
            APPROVED_TOP_SHA256,
            build_cost_governance,
            decision_rule_digest,
            fixed_request_digest,
            measurement_spec_digest,
            quarantine_digest,
            validate_cost_governance,
            validate_run_preregistration,
        )

        if not contract_snapshot.fresh:
            raise AuthorizationError("Track S contract snapshot is stale")
        if not isinstance(track_s_context, dict):
            raise AuthorizationError("Committed Track S run-specific preregistration is unavailable")
        cost = track_s_context.get("costGovernance")
        if not isinstance(cost, dict):
            cost = build_cost_governance(contract_snapshot)
        cost_digest = validate_cost_governance(cost, require_resolved=True)
        preregistration = track_s_context.get("runPreregistration")
        if not isinstance(preregistration, dict):
            raise AuthorizationError("Committed Track S run-specific preregistration is unavailable")
        executing_commit = track_s_context.get("executingCommit")
        is_ancestor = track_s_context.get("isAncestor")
        if not isinstance(executing_commit, str) or not callable(is_ancestor):
            raise AuthorizationError("Track S executing source commitment cannot be proven")
        prereg_digest = validate_run_preregistration(
            preregistration,
            executing_commit=executing_commit,
            is_ancestor=is_ancestor,
        )
        if preregistration.get("reconstructionInputDigest") != bundle_digest:
            raise AuthorizationError("Track S preregistration reconstruction input changed")
        if preregistration.get("beautyImageSha256") != input_reference["sourceSha256s"][0]:
            raise AuthorizationError("Track S preregistration beauty image changed")
        validation_target = preregistration.get("validationTarget") or {}
        if validation_target.get("sha256") != APPROVED_TOP_SHA256 or validation_target.get("isReconstructionInput") is not False:
            raise AuthorizationError("Track S TOP validation target identity or separation changed")
        if preregistration.get("contractSnapshotDigest") != contract_snapshot.sha256:
            raise AuthorizationError("Track S preregistration contract snapshot changed")
        if preregistration.get("costGovernanceDigest") != cost_digest:
            raise AuthorizationError("Track S preregistration cost governance changed")
        projection["trackS"] = {
            "validationTarget": validation_target,
            "candidateSourceCommit": preregistration.get("candidateSourceCommit"),
            "fixedRequestDigest": fixed_request_digest(),
            "expectedCreditCost": 20,
            "maximumCreditAuthorization": 20,
            "automaticRetry": False,
            "costGovernanceDigest": cost_digest,
            "failedTaskChargingDisposition": cost["failedTaskChargingDisposition"],
            "runPreregistrationDigest": prereg_digest,
            "measurementSpecDigest": measurement_spec_digest(),
            "decisionRuleDigest": decision_rule_digest(),
            "quarantineDigest": quarantine_digest(),
            "quarantineAttestation": preregistration.get("quarantineAttestation"),
            "networkKillSwitchState": track_s_context.get("networkKillSwitchState"),
            "hostPolicy": artifact_host_policy.contract_version,
            "maximumRedirects": track_s_context.get("maximumRedirects"),
        }
        if projection["trackS"]["networkKillSwitchState"] not in {"ENABLED", "DISABLED"}:
            raise AuthorizationError("Track S network kill-switch state is not bound")
        if projection["trackS"]["maximumRedirects"] != 4:
            raise AuthorizationError("Track S redirect ceiling changed")
    _reject_floats(projection)
    return projection


def authorization_digest(projection: dict[str, Any]) -> str:
    _reject_floats(projection)
    return hashlib.sha256(canonicalize(projection)).hexdigest()


def validate_authorization_projection(
    projection: dict[str, Any], *, bundle: dict[str, Any], artifact_host_policy: ArtifactHostPolicy
) -> str:
    if projection.get("schemaVersion") != AUTHORIZATION_SCHEMA_VERSION:
        raise AuthorizationError("Unsupported pilot authorization schema")
    expected_digest = bundle.get("bundleDigest", bundle.get("inputDigest"))
    if projection.get("bundleDigest") != expected_digest:
        raise AuthorizationError("Pilot authorization bundle digest changed")
    reference_kind = "single_view_v1" if bundle.get("inputKind") == "single_view_v1" else "multiview_bundle_v1"
    if projection.get("inputKind") != reference_kind:
        raise AuthorizationError("Pilot authorization inputKind changed")
    if projection.get("reconstructionInputDigest") != expected_digest:
        raise AuthorizationError("Pilot authorization reconstruction-input digest changed")
    expected_hashes = (
        [bundle["source"]["sha256"]]
        if reference_kind == "single_view_v1"
        else [item["sha256"] for item in bundle.get("views", [])]
    )
    if projection.get("reconstructionInputSourceSha256s") != expected_hashes:
        raise AuthorizationError("Pilot authorization reconstruction-input source hashes changed")
    if projection.get("profileId") != bundle.get("profileId"):
        raise AuthorizationError("Pilot authorization profile changed")
    if projection.get("requestBody") != FIXED_REQUEST:
        raise AuthorizationError("Pilot request options changed")
    if projection.get("estimatedCredits") != 20 or projection.get("maximumCredits") != 20:
        raise AuthorizationError("Pilot credit values changed")
    if projection.get("artifactHostPolicy") != {"contractVersion": artifact_host_policy.contract_version}:
        raise AuthorizationError("Pilot artifact-host policy changed")
    approval = bundle.get("approval") or {}
    if projection.get("humanApproval") != {
        "approvedAt": approval.get("approvedAt"),
        "workflowId": approval.get("workflowId"),
    }:
        raise AuthorizationError("Pilot human approval record changed")
    if reference_kind == "single_view_v1":
        from .track_s import (
            APPROVED_TOP_SHA256,
            FAILED_TASK_RESOLVED,
            decision_rule_digest,
            fixed_request_digest,
            measurement_spec_digest,
            quarantine_digest,
        )

        track = projection.get("trackS") or {}
        if track.get("validationTarget", {}).get("sha256") != APPROVED_TOP_SHA256:
            raise AuthorizationError("Track S validation target changed")
        if track.get("validationTarget", {}).get("isReconstructionInput") is not False:
            raise AuthorizationError("Track S validation target entered reconstruction input")
        if track.get("fixedRequestDigest") != fixed_request_digest():
            raise AuthorizationError("Track S fixed request digest changed")
        if track.get("measurementSpecDigest") != measurement_spec_digest():
            raise AuthorizationError("Track S measurement specification digest changed")
        if track.get("decisionRuleDigest") != decision_rule_digest():
            raise AuthorizationError("Track S decision-rule digest changed")
        if track.get("quarantineDigest") != quarantine_digest():
            raise AuthorizationError("Track S quarantine digest changed")
        if track.get("failedTaskChargingDisposition") not in FAILED_TASK_RESOLVED:
            raise AuthorizationError("Track S failed-task charging remains unresolved")
        if track.get("automaticRetry") is not False or track.get("maximumCreditAuthorization") != 20:
            raise AuthorizationError("Track S retry or credit policy changed")
        if track.get("maximumRedirects") != 4:
            raise AuthorizationError("Track S redirect ceiling changed")
    return authorization_digest(projection)
