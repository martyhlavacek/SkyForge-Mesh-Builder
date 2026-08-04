from __future__ import annotations

import base64
import ipaddress
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urljoin, urlsplit

from .bundle import SUPPORTED_PROFILES, validate_bundle

ENDPOINT = "https://api.meshy.ai/openapi/v1/multi-image-to-3d"
ESTIMATED_CREDITS = 20
ARTIFACT_HOST_CONTRACT_VERSION = "skyforge.meshy-artifact-hosts.unverified.v1"
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class AuthorizationError(RuntimeError):
    """Raised before transport when a paid-call control is absent."""


class ProviderError(RuntimeError):
    """Raised for a deterministic provider or artifact failure."""


@dataclass(frozen=True)
class ArtifactHostPolicy:
    contract_version: str
    approved_hosts: frozenset[str]
    address_resolver: Callable[[str], tuple[str, ...]] | None = None

    def validate(self, url: str) -> str:
        if not isinstance(url, str) or not url:
            raise ProviderError("Malformed provider artifact URL")
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError as exc:
            raise ProviderError("Malformed provider artifact URL") from exc
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise ProviderError("Provider artifact URL must use HTTPS with a hostname")
        if parsed.username is not None or parsed.password is not None:
            raise ProviderError("Provider artifact URL must not contain credentials")
        if port not in {None, 443}:
            raise ProviderError("Provider artifact URL uses an unexpected port")
        hostname = parsed.hostname.lower()
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            raise ProviderError("Provider artifact URL must not target an IP literal")
        if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
            raise ProviderError("Provider artifact URL must not target localhost")
        approved = {host.lower() for host in self.approved_hosts}
        if hostname not in approved:
            raise ProviderError(
                f"Provider artifact host is not approved by {self.contract_version}"
            )
        if self.address_resolver is None:
            raise ProviderError("Provider artifact address resolution policy is unavailable")
        try:
            addresses = self.address_resolver(hostname)
        except Exception as exc:
            raise ProviderError("Provider artifact hostname resolution failed") from exc
        if not addresses:
            raise ProviderError("Provider artifact hostname resolved to no addresses")
        for address in addresses:
            try:
                resolved = ipaddress.ip_address(address)
            except ValueError as exc:
                raise ProviderError("Provider artifact hostname resolution was malformed") from exc
            if not resolved.is_global:
                raise ProviderError("Provider artifact hostname resolved to a non-public address")
        return url


DEFAULT_ARTIFACT_HOST_POLICY = ArtifactHostPolicy(
    contract_version=ARTIFACT_HOST_CONTRACT_VERSION,
    approved_hosts=frozenset(),
)


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
        artifact_host_policy: ArtifactHostPolicy = DEFAULT_ARTIFACT_HOST_POLICY,
    ):
        self.transport = transport
        self.environ = dict(os.environ if environ is None else environ)
        self.submission_registry = submission_registry
        self.artifact_host_policy = artifact_host_policy
        self._post_attempted = False
        self.last_create_response: dict[str, Any] | None = None

    def _assert_network_permitted(self, operation: str) -> None:
        active = [name for name in ("CI", "GITHUB_ACTIONS") if self.environ.get(name)]
        if self.environ.get("SKYFORGE_PROVIDER_NETWORK_DISABLED") == "1":
            active.append("SKYFORGE_PROVIDER_NETWORK_DISABLED")
        if active:
            raise AuthorizationError(
                f"Provider network operation {operation} is disabled by {','.join(active)}"
            )

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
        self._assert_network_permitted("submit_task")
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
        self._assert_network_permitted("get_task")
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
        self._assert_network_permitted("poll_until_terminal")
        if maximum_polls < 1:
            raise ProviderError("Polling limit must be positive")
        for _ in range(maximum_polls):
            normalized = self.normalize_response(self.get_task(task_id))
            if normalized["status"] in {"SUCCEEDED", "FAILED", "CANCELED"}:
                return normalized
        raise ProviderError("Meshy polling timeout reached without creating another task")

    def download_artifact(self, url: str) -> bytes:
        self._assert_network_permitted("download_artifact")
        current_url = self.artifact_host_policy.validate(url)
        for _ in range(4):
            response = self.transport.request("GET", current_url, allow_redirects=False)
            response_url = getattr(response, "url", None)
            if response_url:
                self.artifact_host_policy.validate(response_url)
            if response.status_code not in REDIRECT_STATUSES:
                break
            location = (getattr(response, "headers", None) or {}).get("Location")
            if not location:
                raise ProviderError("Provider artifact redirect omitted Location")
            current_url = self.artifact_host_policy.validate(urljoin(current_url, location))
        else:
            raise ProviderError("Provider artifact redirect limit exceeded")
        payload = bytes(response.content)
        if response.status_code != 200 or len(payload) < 20 or payload[:4] != b"glTF":
            raise ProviderError("Missing, expired, empty, or corrupt provider GLB")
        return payload

    def download_artifacts(self, normalized_response: dict[str, Any]) -> dict[str, bytes]:
        self._assert_network_permitted("download_artifacts")
        urls = normalized_response.get("modelUrls")
        if not isinstance(urls, dict) or not isinstance(urls.get("glb"), str):
            raise ProviderError("Successful task response did not contain a GLB artifact URL")
        return {"glb": self.download_artifact(urls["glb"])}
