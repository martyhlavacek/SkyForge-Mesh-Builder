from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from common.canonical_json import canonicalize

from .bundle import validate_bundle
from .provider import ESTIMATED_CREDITS, ArtifactHostPolicy, AuthorizationError

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
) -> dict[str, Any]:
    bundle_digest = validate_bundle(bundle_root, bundle, require_approved=True)
    resolved_request = dict(FIXED_REQUEST if request_body is None else request_body)
    if resolved_request != FIXED_REQUEST:
        raise AuthorizationError("Pilot request options differ from the fixed geometry-only contract")
    if type(estimated_credits) is not int or type(maximum_credits) is not int:
        raise AuthorizationError("Pilot credit values must be integers")
    if estimated_credits != ESTIMATED_CREDITS or maximum_credits != ESTIMATED_CREDITS:
        raise AuthorizationError("Pilot credit estimate and cap must both equal exactly 20")
    approval = bundle.get("approval")
    if not isinstance(approval, dict):
        raise AuthorizationError("Human bundle approval record is unavailable")
    projection = {
        "schemaVersion": AUTHORIZATION_SCHEMA_VERSION,
        "bundleDigest": bundle_digest,
        "profileId": bundle["profileId"],
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
    if projection.get("bundleDigest") != bundle.get("bundleDigest"):
        raise AuthorizationError("Pilot authorization bundle digest changed")
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
    return authorization_digest(projection)
