from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from PIL import Image

from .authorization import (
    FIXED_REQUEST,
    authorization_digest,
    build_authorization_projection,
    load_contract_snapshot,
)
from .bundle import (
    VIEW_ORDER,
    approve_bundle,
    build_bundle,
    content_digest,
    render_contact_sheet,
    validate_bundle,
)
from .preflight import preflight_artifact_url
from .provider import (
    ESTIMATED_CREDITS,
    MeshyMultiImageProvider,
    SubmissionAuthorization,
)
from .quarantine import quarantine_digest, quarantine_record
from .reconstruction_input import (
    MULTIVIEW_KIND,
    SINGLE_VIEW_KIND,
    approve_single_view_input,
    build_single_view_input,
    input_kind,
    validate_single_view_input,
)
from .state import TRANSITIONS, StateError, TaskLog
from .track_s import (
    APPROVED_TOP_SHA256,
    DECISION_RULES,
    MEASUREMENT_SPEC,
    PREREGISTRATION_POLICY,
    build_cost_governance,
    decision_rule_digest,
    measurement_spec_digest,
    preregistration_policy_digest,
)

PILOT_CONFIG_PATH = Path(__file__).with_name("pilot_config_v1.json")
BUNDLE_FILENAME = "MultiviewAuthorityBundleV1.json"
SINGLE_VIEW_FILENAME = "SingleViewReconstructionInputV1.json"
AUTHORIZATION_FILENAME = "authorization_preview.json"
SESSION_IDENTITY_FILENAME = "TrackSExperimentSessionV1.json"
ACTIVE_SESSION_FILENAME = "ACTIVE_TRACK_S_SESSION.json"
ALLOWED_PROVENANCE = frozenset(
    {"human_authority_candidate", "deterministic_fixture", "single_view_source"}
)
APPROVABLE_PROVENANCE = "human_authority_candidate"
ALLOWED_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})
ROLE_TOKENS = frozenset(VIEW_ORDER)


class PilotError(RuntimeError):
    """A fail-closed pilot workflow refusal safe for display."""


class PilotSessionManager:
    """Selects an isolated Track S run without mutating the historical pilot workspace."""

    def __init__(
        self,
        package_root: Path,
        historical_workspace: Path,
        sessions_root: Path,
        provider: MeshyMultiImageProvider,
        *,
        now: Callable[[], datetime] | None = None,
    ):
        self.package_root = package_root.resolve()
        self.historical_workspace = historical_workspace.resolve()
        self.sessions_root = sessions_root.resolve()
        self.provider = provider
        self.now = now or (lambda: datetime.now(UTC))
        self.historical_runtime = PilotRuntime(
            self.package_root, self.historical_workspace, provider, now=self.now
        )

    @property
    def active_pointer_path(self) -> Path:
        return self.sessions_root / ACTIVE_SESSION_FILENAME

    def _timestamp(self) -> str:
        return self.now().astimezone(UTC).isoformat().replace("+00:00", "Z")

    def active_session_identity(self) -> dict[str, Any] | None:
        if not self.active_pointer_path.is_file():
            return None
        pointer = json.loads(self.active_pointer_path.read_text(encoding="utf-8"))
        if pointer.get("schemaVersion") != "skyforge.active-track-s-session.v1":
            raise PilotError("Active Track S session pointer is invalid")
        session_id = pointer.get("sessionId")
        if not isinstance(session_id, str) or not re.fullmatch(r"track-s-[0-9TZ.-]+", session_id):
            raise PilotError("Active Track S session identity is unsafe")
        workspace = self.sessions_root / session_id
        if workspace.is_symlink() or not workspace.is_dir():
            raise PilotError("Active Track S session workspace is unavailable")
        identity_path = workspace / SESSION_IDENTITY_FILENAME
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        if identity != {
            "schemaVersion": "skyforge.track-s-experiment-session.v1",
            "sessionId": session_id,
            "inputKind": None,
            "createdAt": identity.get("createdAt"),
            "historicalWorkspaceInherited": False,
        } or not isinstance(identity.get("createdAt"), str):
            raise PilotError("Track S session identity record is invalid")
        return identity

    def active_runtime(self) -> PilotRuntime | None:
        identity = self.active_session_identity()
        if identity is None:
            return None
        return PilotRuntime(
            self.package_root,
            self.sessions_root / identity["sessionId"],
            self.provider,
            now=self.now,
        )

    def start_track_s_session(self) -> PilotRuntime:
        timestamp = self._timestamp()
        session_id = "track-s-" + re.sub(r"[^0-9TZ.-]", "-", timestamp)
        workspace = self.sessions_root / session_id
        if workspace.exists():
            raise PilotError("A Track S session already exists for this exact timestamp")
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        workspace.mkdir()
        identity = {
            "schemaVersion": "skyforge.track-s-experiment-session.v1",
            "sessionId": session_id,
            "inputKind": None,
            "createdAt": timestamp,
            "historicalWorkspaceInherited": False,
        }
        (workspace / SESSION_IDENTITY_FILENAME).write_text(
            json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        pointer = {
            "schemaVersion": "skyforge.active-track-s-session.v1",
            "sessionId": session_id,
        }
        temporary = self.sessions_root / f".{ACTIVE_SESSION_FILENAME}.tmp"
        temporary.write_text(json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.active_pointer_path)
        runtime = self.active_runtime()
        if runtime is None or runtime.current_state() is not None:
            raise PilotError("New Track S session did not start with an empty lifecycle")
        return runtime

    def historical_view_path(self, role: str) -> Path:
        if role not in VIEW_ORDER:
            raise PilotError("Unknown historical authority role")
        bundle_path = self.historical_workspace / BUNDLE_FILENAME
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        item = next((entry for entry in bundle.get("views", []) if entry.get("role") == role), None)
        if not isinstance(item, dict):
            raise PilotError("Historical authority role is unavailable")
        relative = PurePosixPath(str(item.get("path", "")))
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise PilotError("Historical authority path is unsafe")
        path = self.historical_workspace / relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(self.historical_workspace):
            raise PilotError("Historical authority file is unavailable")
        return path

    def discard_active_session(self) -> None:
        runtime = self.active_runtime()
        if runtime is None:
            raise PilotError("No active Track S session exists")
        runtime.discard()
        self.active_pointer_path.unlink()


def _filename_tokens(filename: str) -> set[str]:
    stem = Path(filename).name
    with_acronym_boundaries = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", stem)
    with_camel_boundaries = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", with_acronym_boundaries)
    with_digit_boundaries = re.sub(
        r"(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])",
        " ",
        with_camel_boundaries,
    )
    return {
        token.casefold()
        for token in re.split(r"[^A-Za-z0-9]+", with_digit_boundaries)
        if token
    }


def load_pilot_config() -> dict[str, Any]:
    config = json.loads(PILOT_CONFIG_PATH.read_text(encoding="utf-8"))
    if config.get("schemaVersion") != "skyforge.meshy-pilot-config.v1":
        raise PilotError("Unsupported pilot configuration")
    if config.get("pilotPort") != 5180:
        raise PilotError("Pilot port differs from the reviewed deterministic port")
    if config.get("pollingIntervalSeconds") != 10 or config.get("maximumPollCount") != 30:
        raise PilotError("Pilot polling configuration differs from the reviewed bounds")
    if config.get("maximumRedirects") != 4:
        raise PilotError("Pilot redirect limit differs from the reviewed bound")
    return config


class PilotRuntime:
    def __init__(
        self,
        package_root: Path,
        workspace: Path,
        provider: MeshyMultiImageProvider,
        *,
        now: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.package_root = package_root.resolve()
        self.repository_root = self.package_root.parent.resolve()
        self.workspace = workspace.resolve()
        self.provider = provider
        self.now = now or (lambda: datetime.now(UTC))
        self.sleeper = sleeper
        self.config = load_pilot_config()

    @property
    def bundle_path(self) -> Path:
        return self.workspace / BUNDLE_FILENAME

    @property
    def authorization_path(self) -> Path:
        return self.workspace / AUTHORIZATION_FILENAME

    @property
    def single_view_path(self) -> Path:
        return self.workspace / SINGLE_VIEW_FILENAME

    @property
    def task_log(self) -> TaskLog:
        return TaskLog(self.workspace / "TaskLog.jsonl")

    def current_state(self) -> str | None:
        events = self.task_log.events()
        return events[-1]["state"] if events else None

    def _timestamp(self) -> str:
        return self.now().astimezone(UTC).isoformat().replace("+00:00", "Z")

    def contract_snapshot(self):
        return load_contract_snapshot(
            self.repository_root,
            self.config["contractSnapshotPath"],
            now=self.now(),
        )

    def load_bundle(self, *, require_approved: bool = False) -> dict[str, Any]:
        if not self.bundle_path.is_file():
            raise PilotError("No multiview authority bundle has been imported")
        bundle = json.loads(self.bundle_path.read_text(encoding="utf-8"))
        validate_bundle(self.workspace, bundle, require_approved=require_approved)
        self._validate_provenance(bundle, require_approvable=require_approved)
        return bundle

    def load_reconstruction_input(self, *, require_approved: bool = False) -> dict[str, Any]:
        if self.bundle_path.is_file() and self.single_view_path.is_file():
            raise PilotError("Multiple reconstruction inputs exist; discard and restart")
        if self.single_view_path.is_file():
            document = json.loads(self.single_view_path.read_text(encoding="utf-8"))
            validate_single_view_input(self.workspace, document, require_approved=require_approved)
            return document
        return self.load_bundle(require_approved=require_approved)

    @staticmethod
    def _validate_provenance(bundle: dict[str, Any], *, require_approvable: bool) -> None:
        classifications = [item.get("provenanceClassification") for item in bundle.get("views", [])]
        if any(value not in ALLOWED_PROVENANCE for value in classifications):
            raise PilotError("Every authority view requires a supported provenance classification")
        if require_approvable and any(value != APPROVABLE_PROVENANCE for value in classifications):
            raise PilotError("Fixture or single-view material cannot become human-approved authority")

    def import_bundle(
        self,
        *,
        profile_id: str,
        uploads: list[tuple[str, str, bytes, str]],
        asset_id: str,
    ) -> dict[str, Any]:
        if self.task_log.events():
            raise PilotError("Approved workflow is immutable; discard and restart")
        if [item[0] for item in uploads] != list(VIEW_ORDER):
            raise PilotError("Views must be supplied in top, front, right order")
        for role, original_name, _payload, _provenance in uploads:
            tokens = _filename_tokens(original_name)
            conflicts = sorted((tokens & ROLE_TOKENS) - {role})
            if conflicts:
                raise PilotError(
                    f"Source filename conflicts with its {role} authority role; "
                    "rename the file before import"
                )
        self.workspace.mkdir(parents=True, exist_ok=True)
        paths: list[tuple[str, Path]] = []
        metadata: dict[str, tuple[str, str]] = {}
        try:
            for role, original_name, payload, provenance in uploads:
                if provenance not in ALLOWED_PROVENANCE:
                    raise PilotError("Unsupported authority provenance classification")
                suffix = Path(original_name).suffix.lower()
                if suffix not in ALLOWED_IMAGE_SUFFIXES:
                    raise PilotError("Authority view must be PNG, JPG, or JPEG")
                destination = self.workspace / f"authority_{role}{suffix}"
                destination.write_bytes(payload)
                with Image.open(destination) as image:
                    image.verify()
                paths.append((role, destination))
                metadata[role] = (Path(original_name).name, provenance)
            bundle = build_bundle(
                self.workspace,
                asset_id=asset_id,
                profile_id=profile_id,
                source_commit="IMPORTED_AUTHORITY_INPUT_NOT_GENERATED_BY_PILOT",
                created_at=self._timestamp(),
                views=paths,
            )
            for item in bundle["views"]:
                original, provenance = metadata[item["role"]]
                item["originalFilename"] = original
                item["provenanceClassification"] = provenance
            contact = self.workspace / "authority_contact_sheet.png"
            render_contact_sheet(self.workspace, bundle, contact)
            bundle["contactSheet"] = {
                "path": contact.name,
                "sha256": hashlib.sha256(contact.read_bytes()).hexdigest(),
            }
            bundle["bundleDigest"] = content_digest(bundle)
            validate_bundle(self.workspace, bundle, require_approved=False)
            self._validate_provenance(bundle, require_approvable=False)
            self.bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self.task_log.append(
                "PREPARED",
                timestamp=self._timestamp(),
                details={"inputKind": MULTIVIEW_KIND, "reconstructionInputDigest": bundle["bundleDigest"]},
            )
            return bundle
        except Exception:
            if not self.task_log.path.exists():
                for path in self.workspace.glob("authority_*"):
                    if path.is_file():
                        path.unlink()
            raise

    def import_single_view(
        self,
        *,
        profile_id: str,
        upload_name: str,
        payload: bytes,
        provenance: str,
        provenance_source_type: str,
        asset_id: str,
    ) -> dict[str, Any]:
        if self.task_log.events() or self.bundle_path.exists() or self.single_view_path.exists():
            raise PilotError("Approved workflow is immutable; discard and restart")
        suffix = Path(upload_name).suffix.lower()
        if suffix not in ALLOWED_IMAGE_SUFFIXES:
            raise PilotError("Track S beauty reference must be PNG, JPG, or JPEG")
        self.workspace.mkdir(parents=True, exist_ok=True)
        destination = self.workspace / f"track_s_beauty_reference{suffix}"
        try:
            destination.write_bytes(payload)
            document = build_single_view_input(
                self.workspace,
                source_path=destination,
                asset_id=asset_id,
                profile_id=profile_id,
                original_filename=upload_name,
                provenance=provenance,
                provenance_source_type=provenance_source_type,
                imported_at=self._timestamp(),
                source_commit="IMPORTED_BEAUTY_REFERENCE_NOT_GENERATED_BY_PILOT",
            )
            self.single_view_path.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            self.task_log.append(
                "PREPARED",
                timestamp=self._timestamp(),
                details={"inputKind": SINGLE_VIEW_KIND, "reconstructionInputDigest": document["inputDigest"]},
            )
            return document
        except Exception:
            if not self.task_log.path.exists() and destination.exists():
                destination.unlink()
            raise

    def approve(self, *, workflow_id: str) -> dict[str, Any]:
        if self.current_state() != "PREPARED":
            raise StateError(f"Illegal reconstruction transition: {self.current_state()} -> BUNDLE_APPROVED")
        bundle = self.load_reconstruction_input(require_approved=False)
        kind = input_kind(bundle)
        if kind == MULTIVIEW_KIND:
            self._validate_provenance(bundle, require_approvable=True)
            approved = approve_bundle(
                self.workspace,
                bundle,
                approved_at=self._timestamp(),
                workflow_id=workflow_id,
            )
            digest = approved["bundleDigest"]
            target = self.bundle_path
        else:
            approved = approve_single_view_input(
                self.workspace,
                bundle,
                approved_at=self._timestamp(),
                workflow_id=workflow_id,
            )
            digest = approved["inputDigest"]
            target = self.single_view_path
        target.write_text(json.dumps(approved, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.task_log.append(
            "BUNDLE_APPROVED",
            timestamp=self._timestamp(),
            details={"inputKind": kind, "reconstructionInputDigest": digest},
        )
        return approved

    def discard(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

    def request_contract_reverified(self) -> None:
        snapshot = self.contract_snapshot()
        if not snapshot.fresh:
            raise PilotError("Contract snapshot is STALE; live re-verification must be committed externally")
        self.load_reconstruction_input(require_approved=True)
        self.task_log.append(
            "CONTRACT_REVERIFIED",
            timestamp=self._timestamp(),
            details={"snapshotSha256": snapshot.sha256, "verificationDate": snapshot.verification_date},
        )

    def preview_authorization(self) -> dict[str, Any]:
        snapshot = self.contract_snapshot()
        if not snapshot.fresh:
            raise PilotError("Contract snapshot is STALE; authorization preview is refused")
        bundle = self.load_reconstruction_input(require_approved=True)
        projection = build_authorization_projection(
            self.package_root,
            self.workspace,
            bundle,
            contract_snapshot=snapshot,
            artifact_host_policy=self.provider.artifact_host_policy,
        )
        digest = authorization_digest(projection)
        record = {"projection": projection, "authorizationDigest": digest}
        self.authorization_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.task_log.append(
            "AUTHORIZATION_PREVIEWED",
            timestamp=self._timestamp(),
            details={"authorizationDigest": digest},
        )
        return record

    def approve_cost(self, confirmed_digest: str) -> None:
        snapshot = self.contract_snapshot()
        if not snapshot.fresh:
            raise PilotError("Contract snapshot is STALE; cost approval is refused")
        record = self.recompute_authorization()
        if confirmed_digest != record["authorizationDigest"]:
            raise PilotError("Exact authorizationDigest confirmation does not match")
        self.task_log.append(
            "COST_APPROVED",
            timestamp=self._timestamp(),
            details={"authorizationDigest": confirmed_digest, "maximumCredits": ESTIMATED_CREDITS},
        )

    def recompute_authorization(self) -> dict[str, Any]:
        snapshot = self.contract_snapshot()
        bundle = self.load_reconstruction_input(require_approved=True)
        projection = build_authorization_projection(
            self.package_root,
            self.workspace,
            bundle,
            contract_snapshot=snapshot,
            artifact_host_policy=self.provider.artifact_host_policy,
        )
        return {"projection": projection, "authorizationDigest": authorization_digest(projection)}

    def submit(self, *, api_key: str | None) -> str:
        snapshot = self.contract_snapshot()
        if not snapshot.fresh:
            raise PilotError("Contract snapshot is STALE; provider submission is refused")
        if self.current_state() != "COST_APPROVED":
            raise PilotError("Exact authorizationDigest has not been approved")
        record = self.recompute_authorization()
        confirmed = self.task_log.events()[-1]["details"].get("authorizationDigest")
        if record["authorizationDigest"] != confirmed:
            raise PilotError("Authorization inputs changed after explicit approval")
        bundle = self.load_reconstruction_input(require_approved=True)
        self.task_log.append("SUBMITTING", timestamp=self._timestamp())
        try:
            task_id = self.provider.submit_task(
                self.workspace,
                bundle,
                SubmissionAuthorization(
                    paid_enabled=True,
                    approved_bundle_digest=bundle.get("bundleDigest", bundle.get("inputDigest")),
                    confirmed_bundle_digest=bundle.get("bundleDigest", bundle.get("inputDigest")),
                    maximum_credits=20,
                    api_key=api_key,
                    authorization_projection=record["projection"],
                    confirmed_authorization_digest=confirmed,
                ),
            )
        except Exception:
            self.task_log.append("FAILED", timestamp=self._timestamp(), details={"reason": "submission_refused"})
            raise
        self.task_log.append("SUBMITTED", timestamp=self._timestamp(), details={"providerTaskId": task_id})
        return task_id

    def poll_and_capture(self) -> dict[str, Any]:
        events = self.task_log.events()
        if not events or events[-1]["state"] != "SUBMITTED":
            raise PilotError("Polling requires a valid submitted providerTaskId")
        task_id = events[-1]["details"].get("providerTaskId")
        if not isinstance(task_id, str) or not task_id:
            raise PilotError("Polling requires a valid submitted providerTaskId")
        self.task_log.append("POLLING", timestamp=self._timestamp(), details={"attempt": 0})
        for attempt in range(1, self.config["maximumPollCount"] + 1):
            normalized = self.provider.normalize_response(self.provider.get_task(task_id))
            status = normalized["status"]
            if status in {"PENDING", "IN_PROGRESS"}:
                self.task_log.append("POLLING", timestamp=self._timestamp(), details={"attempt": attempt})
                if attempt < self.config["maximumPollCount"]:
                    self.sleeper(self.config["pollingIntervalSeconds"])
                continue
            if status in {"FAILED", "CANCELED"}:
                self.task_log.append(status, timestamp=self._timestamp(), details={"providerTaskId": task_id})
                return normalized
            if status == "SUCCEEDED":
                self.task_log.append(
                    "SUCCEEDED",
                    timestamp=self._timestamp(),
                    details={"providerTaskId": task_id, "expiresAt": normalized.get("expiresAt")},
                )
                artifacts = self.provider.download_artifacts(normalized)
                artifact_path = self.workspace / "captured_provider_artifact.glb"
                artifact_path.write_bytes(artifacts["glb"])
                digest = hashlib.sha256(artifacts["glb"]).hexdigest()
                self.task_log.append(
                    "DOWNLOADED",
                    timestamp=self._timestamp(),
                    details={
                        "rawGlbSha256": digest,
                        "artifactLocation": artifact_path.name,
                        "expiresAt": normalized.get("expiresAt"),
                    },
                )
                return {**normalized, "rawGlbSha256": digest, "artifactLocation": artifact_path.name}
        self.task_log.append(
            "FAILED",
            timestamp=self._timestamp(),
            details={"reason": "maximum_poll_count_exhausted"},
        )
        raise PilotError("Bounded provider polling exhausted without a terminal result")

    def preflight(self, url: str, *, transport: Any | None = None) -> dict[str, Any]:
        result = preflight_artifact_url(
            url,
            policy=self.provider.artifact_host_policy,
            transport=transport,
            maximum_redirects=self.config["maximumRedirects"],
        )
        if "dnsResults" in result:
            result["stubDnsResults"] = result.pop("dnsResults")
            result["resolutionSource"] = "offline_stub_not_observed" if transport is not None else "operating_system_resolver"
        return result

    def status(self) -> dict[str, Any]:
        events = self.task_log.events()
        state = events[-1]["state"] if events else None
        snapshot = self.contract_snapshot()
        bundle = None
        bundle_error = None
        single_view = None
        reconstruction_kind = None
        if self.bundle_path.exists() or self.single_view_path.exists():
            try:
                loaded = self.load_reconstruction_input(require_approved=state not in {None, "PREPARED"})
                reconstruction_kind = input_kind(loaded)
                if reconstruction_kind == MULTIVIEW_KIND:
                    bundle = loaded
                else:
                    single_view = loaded
            except Exception as exc:
                bundle_error = str(exc)
        authorization = None
        if self.authorization_path.exists():
            authorization = json.loads(self.authorization_path.read_text(encoding="utf-8"))
        cost = build_cost_governance(snapshot)
        blocked_reasons = []
        if not snapshot.fresh:
            blocked_reasons.append("Committed Meshy contract snapshot is STALE")
        if reconstruction_kind == SINGLE_VIEW_KIND:
            if cost["failedTaskChargingDisposition"] == "UNRESOLVED":
                blocked_reasons.append("Failed/rejected-task charging remains UNRESOLVED")
            blocked_reasons.append("Committed run-specific preregistration is not yet available")
        return {
            "state": state,
            "events": events,
            "bundle": bundle,
            "singleView": single_view,
            "inputKind": reconstruction_kind,
            "bundleError": bundle_error,
            "contract": snapshot,
            "authorization": authorization,
            "config": self.config,
            "fixedRequest": FIXED_REQUEST,
            "trackS": {
                "validationTarget": {"role": "approved_top_authority_validation_target", "sha256": APPROVED_TOP_SHA256, "isReconstructionInput": False},
                "quarantine": quarantine_record(),
                "quarantineDigest": quarantine_digest(),
                "preregistrationPolicy": PREREGISTRATION_POLICY,
                "preregistrationPolicyDigest": preregistration_policy_digest(),
                "measurementSpec": MEASUREMENT_SPEC,
                "measurementSpecDigest": measurement_spec_digest(),
                "decisionRules": DECISION_RULES,
                "decisionRuleDigest": decision_rule_digest(),
                "costGovernance": cost,
                "blockedReasons": blocked_reasons,
            },
            "backendStates": sorted(value for value in TRANSITIONS if value is not None),
            "allowedNextStates": sorted(TRANSITIONS.get(state, set())),
            "sendable": state == "COST_APPROVED" and snapshot.fresh and bundle_error is None and not blocked_reasons,
        }
