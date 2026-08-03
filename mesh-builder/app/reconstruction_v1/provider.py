from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .bundle import SUPPORTED_PROFILES, validate_bundle

ENDPOINT = "https://api.meshy.ai/openapi/v1/multi-image-to-3d"
ESTIMATED_CREDITS = 20


class AuthorizationError(RuntimeError):
    """Raised before transport when a paid-call control is absent."""


class ProviderError(RuntimeError):
    """Raised for a deterministic provider or artifact failure."""


class HttpTransport(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> Any: ...


class ReconstructionProvider(Protocol):
    provider_id: str

    def estimate_cost(self) -> dict[str, Any]: ...

    def prepare_request(self, root: Path, bundle: dict[str, Any]) -> dict[str, Any]: ...

    def redact_for_evidence(self, request: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class SubmissionAuthorization:
    paid_enabled: bool
    approved_bundle_digest: str
    confirmed_bundle_digest: str
    maximum_credits: int
    api_key: str | None
    prior_task_id: str | None = None


class MeshyMultiImageProvider:
    provider_id = "meshy_multi_image"
    model = "meshy-6"

    def __init__(
        self,
        transport: HttpTransport,
        *,
        environ: dict[str, str] | None = None,
        submission_registry: Path | None = None,
    ):
        self.transport = transport
        self.environ = dict(os.environ if environ is None else environ)
        self.submission_registry = submission_registry
        self._post_attempted = False
        self.last_create_response: dict[str, Any] | None = None

    def estimate_cost(self) -> dict[str, Any]:
        return {"currency": "credits", "estimatedCredits": ESTIMATED_CREDITS, "assumptionDate": "2026-08-03"}

    @staticmethod
    def _data_uri(path: Path) -> str:
        suffix = path.suffix.lower()
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")

    def prepare_request(self, root: Path, bundle: dict[str, Any]) -> dict[str, Any]:
        validate_bundle(root, bundle, require_approved=True)
        return {
            "image_urls": [self._data_uri(root / item["path"]) for item in bundle["views"]],
            "ai_model": self.model,
            "should_texture": False,
            "should_remesh": False,
            "image_enhancement": False,
            "auto_size": False,
            "target_formats": ["glb"],
        }

    def redact_for_evidence(self, request: dict[str, Any]) -> dict[str, Any]:
        redacted = json.loads(json.dumps(request))
        redacted["image_urls"] = [f"<redacted-data-uri-{index + 1}>" for index, _ in enumerate(request["image_urls"])]
        return redacted

    def _authorize(self, root: Path, bundle: dict[str, Any], authorization: SubmissionAuthorization) -> str:
        digest = validate_bundle(root, bundle, require_approved=True)
        if authorization.paid_enabled is not True:
            raise AuthorizationError("Paid provider route is locally disabled")
        if self.environ.get("CI") or self.environ.get("GITHUB_ACTIONS") or self.environ.get("SKYFORGE_PROVIDER_NETWORK_DISABLED") == "1":
            raise AuthorizationError("Provider submission is disabled in CI/no-network execution")
        if bundle["profileId"] not in SUPPORTED_PROFILES:
            raise AuthorizationError("Unsupported paid reconstruction profile")
        if authorization.approved_bundle_digest != digest or authorization.confirmed_bundle_digest != digest:
            raise AuthorizationError("Paid confirmation is not bound to the exact approved bundle")
        if type(authorization.maximum_credits) is not int or authorization.maximum_credits < ESTIMATED_CREDITS:
            raise AuthorizationError("Estimated provider cost exceeds the authorized credit cap")
        if not isinstance(authorization.api_key, str) or not authorization.api_key.strip():
            raise AuthorizationError("Secure Meshy API key is unavailable")
        if authorization.prior_task_id or self._post_attempted:
            raise AuthorizationError("A provider task already exists or submission was already attempted")
        if self.submission_registry is None:
            raise AuthorizationError("Persistent provider submission registry is unavailable")
        self.submission_registry.mkdir(parents=True, exist_ok=True)
        guard = self.submission_registry / f"meshy_submission_{digest}.guard"
        try:
            with guard.open("x", encoding="utf-8") as stream:
                stream.write("SUBMISSION_ATTEMPT_RESERVED_NO_AUTOMATIC_RETRY\n")
        except FileExistsError as exc:
            raise AuthorizationError("A provider task already exists or submission was already attempted") from exc
        return digest

    def submit_task(self, root: Path, bundle: dict[str, Any], authorization: SubmissionAuthorization) -> str:
        self._authorize(root, bundle, authorization)
        request = self.prepare_request(root, bundle)
        self._post_attempted = True
        try:
            response = self.transport.request(
                "POST",
                ENDPOINT,
                json=request,
                headers={"Authorization": "Bearer " + str(authorization.api_key)},
            )
        except Exception as exc:
            raise ProviderError("Ambiguous POST result; automatic resubmission is forbidden") from exc
        if response.status_code in {400, 401, 402, 429}:
            raise ProviderError(f"Meshy submission rejected with HTTP {response.status_code}")
        if response.status_code != 200:
            raise ProviderError(f"Unexpected Meshy submission HTTP {response.status_code}")
        raw_response = response.json()
        if not isinstance(raw_response, dict):
            raise ProviderError("Meshy create response was not a JSON object")
        self.last_create_response = json.loads(json.dumps(raw_response))
        task_id = raw_response.get("result")
        if not isinstance(task_id, str) or not task_id:
            raise ProviderError("Meshy create response did not contain a task ID")
        return task_id

    def get_task(self, task_id: str) -> dict[str, Any]:
        response = self.transport.request("GET", f"{ENDPOINT}/{task_id}")
        if response.status_code in {401, 402, 429}:
            raise ProviderError(f"Meshy polling rejected with HTTP {response.status_code}")
        if response.status_code != 200 or not isinstance(response.json(), dict):
            raise ProviderError("Malformed Meshy polling response")
        return response.json()

    def normalize_response(self, response: dict[str, Any]) -> dict[str, Any]:
        status = response.get("status")
        if status not in {"PENDING", "IN_PROGRESS", "SUCCEEDED", "FAILED", "CANCELED"}:
            raise ProviderError("Malformed Meshy task status")
        return {
            "provider": self.provider_id,
            "status": status,
            "progress": response.get("progress"),
            "modelUrls": dict(response.get("model_urls") or {}),
            "consumedCredits": response.get("task_error", {}).get("consumed_credits")
            if isinstance(response.get("task_error"), dict)
            else response.get("consumed_credits"),
            "taskError": response.get("task_error"),
        }

    def poll_until_terminal(self, task_id: str, *, maximum_polls: int) -> dict[str, Any]:
        if maximum_polls < 1:
            raise ProviderError("Polling limit must be positive")
        for _ in range(maximum_polls):
            normalized = self.normalize_response(self.get_task(task_id))
            if normalized["status"] in {"SUCCEEDED", "FAILED", "CANCELED"}:
                return normalized
        raise ProviderError("Meshy polling timeout reached without creating another task")

    def download_artifact(self, url: str) -> bytes:
        response = self.transport.request("GET", url)
        payload = bytes(response.content)
        if response.status_code != 200 or len(payload) < 20 or payload[:4] != b"glTF":
            raise ProviderError("Missing, expired, empty, or corrupt provider GLB")
        return payload

    def download_artifacts(self, normalized_response: dict[str, Any]) -> dict[str, bytes]:
        urls = normalized_response.get("modelUrls")
        if not isinstance(urls, dict) or not isinstance(urls.get("glb"), str):
            raise ProviderError("Successful task response did not contain a GLB artifact URL")
        return {"glb": self.download_artifact(urls["glb"])}
