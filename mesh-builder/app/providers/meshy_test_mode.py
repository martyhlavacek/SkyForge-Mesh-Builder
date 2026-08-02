from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol
from urllib.parse import urlparse

from common.schema_validation import validate_document


class MeshyTestModeError(RuntimeError):
    """The zero-credit Meshy lifecycle diagnostic failed closed."""


class MeshyTestModePromotionError(MeshyTestModeError):
    """Transport-only evidence was presented to an approval/export path."""


TEST_MODE_API_KEY = "msy_dummy_api_key_for_test_mode_12345678"
API_HOST = "api.meshy.ai"
ASSET_HOST = "assets.meshy.ai"
BASE_URL = f"https://{API_HOST}"
CREATE_PATH = "/openapi/v1/image-to-3d"
TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "EXPIRED", "CANCELED"})


class HttpResponse(Protocol):
    status_code: int
    content: bytes
    headers: Mapping[str, str]

    def json(self) -> Any: ...

    def raise_for_status(self) -> None: ...

    def iter_lines(self, decode_unicode: bool = False) -> Iterable[bytes | str]: ...


class HttpSession(Protocol):
    def post(self, url: str, **kwargs: Any) -> HttpResponse: ...

    def get(self, url: str, **kwargs: Any) -> HttpResponse: ...


@dataclass(frozen=True)
class TestModeDiagnosticResult:
    task_id: str
    provider_status: str
    consumed_credits_informational: str
    evidence_directory: Path
    pep_path: Path
    result_path: Path
    vmp_produced: bool = False
    approved_asset_produced: bool = False
    promotion_permitted: bool = False

    def assert_not_promotable(self) -> None:
        if self.promotion_permitted or self.vmp_produced or self.approved_asset_produced:
            raise MeshyTestModePromotionError("Meshy test-mode evidence cannot be promoted")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=False, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def _millis_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _data_uri(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise MeshyTestModeError("Test-mode authority input must be PNG or JPEG")
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _sanitize_url(value: str) -> dict[str, Any]:
    parsed = urlparse(value)
    return {
        "host": parsed.hostname or "",
        "path": parsed.path,
        "signedQueryRemoved": bool(parsed.query),
    }


def sanitize_provider_object(value: Any) -> Any:
    """Remove credentials, signed URLs, and local paths before evidence hashing."""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if any(token in lowered for token in ("authorization", "api_key", "apikey", "secret", "token")):
                sanitized[key] = "<redacted>"
            elif isinstance(item, str) and item.startswith(("http://", "https://")):
                sanitized[key] = _sanitize_url(item)
            else:
                sanitized[key] = sanitize_provider_object(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_provider_object(item) for item in value]
    if isinstance(value, str) and value.startswith(("/", "file://")):
        return "<local-path-removed>"
    return value


class MeshyTestModeAdapter:
    """Zero-credit transport/lifecycle diagnostic isolated from production providers.

    It deliberately does not implement ``MeshProvider`` and is not registered in the
    normal provider registry, so its fixed sample cannot become a ProviderCapture,
    approved asset, or Validated Mesh Package.
    """

    PROVIDER_ID = "meshy_test_mode"
    MODEL_ID = "test-mode-fixed-sample"

    def __init__(
        self,
        session: HttpSession,
        *,
        network_enabled: bool = False,
        base_url: str = BASE_URL,
        clock: Callable[[], str] = _utc_now,
        sleeper: Callable[[float], None] = time.sleep,
        max_polls: int = 20,
        poll_interval_seconds: float = 1.0,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.session = session
        self.network_enabled = network_enabled
        self.base_url = base_url.rstrip("/")
        self.clock = clock
        self.sleeper = sleeper
        self.max_polls = max_polls
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds
        self._validate_api_origin(self.base_url)

    @staticmethod
    def _validate_api_origin(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != API_HOST or parsed.port not in {None, 443}:
            raise MeshyTestModeError("Meshy diagnostic API origin is not allowlisted")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise MeshyTestModeError("Meshy diagnostic API origin must be the exact allowlisted origin")

    @staticmethod
    def _validate_asset_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != ASSET_HOST or parsed.port not in {None, 443}:
            raise MeshyTestModeError("Meshy diagnostic asset host is not allowlisted")
        if parsed.username or parsed.password:
            raise MeshyTestModeError("Meshy diagnostic asset URL contains user information")

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {TEST_MODE_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @staticmethod
    def build_payload(authority_path: Path) -> dict[str, Any]:
        return {
            "image_url": _data_uri(authority_path),
            "model_type": "standard",
            "ai_model": "meshy-6",
            "should_texture": False,
            "should_remesh": False,
            "image_enhancement": False,
            "remove_lighting": False,
            "auto_size": False,
            "moderation": False,
            "target_formats": ["glb"],
        }

    def run(self, *, authority_path: Path, output_dir: Path) -> TestModeDiagnosticResult:
        if not self.network_enabled:
            raise MeshyTestModeError("Network is disabled; pass the explicit diagnostic network gate")
        output_dir.mkdir(parents=True, exist_ok=True)
        payload = self.build_payload(authority_path)
        request_digest = _sha256_bytes(_canonical_bytes(payload))
        snapshots: list[dict[str, Any]] = []
        sanitized_history: list[dict[str, Any]] = []

        submit = self.session.post(
            self.base_url + CREATE_PATH,
            headers=self.headers,
            json=payload,
            timeout=self.timeout_seconds,
        )
        submit.raise_for_status()
        submit_object = submit.json()
        if not isinstance(submit_object, dict) or not isinstance(submit_object.get("result"), str):
            raise MeshyTestModeError("Meshy test-mode submit response is invalid")
        task_id = submit_object["result"]
        snapshots.append(self._snapshot("submit", "SUBMITTED", submit_object, sanitized_history))

        terminal = self._stream_terminal(task_id, snapshots, sanitized_history)
        if terminal is None:
            terminal = self._poll_terminal(task_id, snapshots, sanitized_history)
        status = str(terminal.get("status", "UNKNOWN")).upper()
        if status not in TERMINAL_STATUSES:
            raise MeshyTestModeError(f"Meshy test-mode task did not reach a terminal state: {status}")

        sanitized_terminal = sanitize_provider_object(terminal)
        _atomic_json(output_dir / "sanitized_terminal_task.json", sanitized_terminal)
        history_path = output_dir / "sanitized_task_history.json"
        _atomic_json(history_path, sanitized_history)
        artifacts: list[dict[str, Any]] = [
            {
                "path": history_path.name,
                "sha256": _sha256_file(history_path),
                "contentType": "application/json",
                "capturedAt": self.clock(),
            }
        ]
        if status == "SUCCEEDED":
            model_url = terminal.get("model_urls", {}).get("glb") if isinstance(terminal.get("model_urls"), dict) else None
            if not isinstance(model_url, str):
                raise MeshyTestModeError("Succeeded test-mode task omitted the GLB URL")
            self._validate_asset_url(model_url)
            response = self.session.get(
                model_url,
                headers={"Accept": "model/gltf-binary"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            fixed_sample = output_dir / "fixed_sample_transport_only.glb"
            fixed_sample.write_bytes(response.content)
            artifacts.append(
                {
                    "path": fixed_sample.name,
                    "sha256": _sha256_file(fixed_sample),
                    "contentType": response.headers.get("Content-Type", "model/gltf-binary"),
                    "capturedAt": self.clock(),
                }
            )

        zero_credit_record = {
            "schemaVersion": "skyforge.meshy-test-mode-zero-credit-declaration.v1",
            "providerId": self.PROVIDER_ID,
            "publicTestKey": True,
            "paidReservationCreated": False,
            "productionCredentialRead": False,
            "requestDigest": request_digest,
            "consumedCreditsInformational": str(terminal.get("consumed_credits", "unknown")),
            "paidReconciliationProof": False,
        }
        declaration_path = output_dir / "zero_credit_transport_declaration.json"
        _atomic_json(declaration_path, zero_credit_record)
        artifacts.append(
            {
                "path": declaration_path.name,
                "sha256": _sha256_file(declaration_path),
                "contentType": "application/json",
                "capturedAt": self.clock(),
            }
        )

        captured_at = self.clock()
        pep = {
            "schemaVersion": "skyforge.provider-evidence-package.v1",
            "providerId": self.PROVIDER_ID,
            "modelId": self.MODEL_ID,
            "evidenceClass": "transport_lifecycle_only",
            "promotionPermitted": False,
            "resolvedRequestDigest": request_digest,
            "taskSnapshots": snapshots,
            "capturedArtifacts": artifacts,
            "reservationRecordSha256": _sha256_file(declaration_path),
            "sanitization": {
                "secretsRemoved": True,
                "signedUrlsRemoved": True,
                "localPathsRemoved": True,
            },
            "capturedAt": captured_at,
        }
        expires_at = _millis_to_iso(terminal.get("expires_at"))
        if expires_at is not None:
            pep["expiresAt"] = expires_at
        validate_document("provider_evidence_package.schema.json", pep)
        pep_path = output_dir / "provider_evidence_package.json"
        _atomic_json(pep_path, pep)

        result = {
            "schemaVersion": "skyforge.meshy-test-mode-diagnostic-result.v1",
            "providerId": self.PROVIDER_ID,
            "taskId": task_id,
            "providerStatus": status,
            "consumedCreditsInformational": str(terminal.get("consumed_credits", "unknown")),
            "consumedCreditsArePaidReconciliationProof": False,
            "productionCredentialRead": False,
            "paidLedgerEntryCreated": False,
            "evidenceClass": "transport_lifecycle_only",
            "promotionPermitted": False,
            "approvedAssetProduced": False,
            "vmpProduced": False,
            "geometryQualityClaimPermitted": False,
            "authorityPreservationClaimPermitted": False,
            "pepSha256": _sha256_file(pep_path),
        }
        result_path = output_dir / "diagnostic_result.json"
        _atomic_json(result_path, result)
        diagnostic = TestModeDiagnosticResult(
            task_id=task_id,
            provider_status=status,
            consumed_credits_informational=result["consumedCreditsInformational"],
            evidence_directory=output_dir,
            pep_path=pep_path,
            result_path=result_path,
        )
        diagnostic.assert_not_promotable()
        return diagnostic

    def _snapshot(
        self,
        phase: str,
        state: str,
        provider_object: Any,
        sanitized_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        sanitized = sanitize_provider_object(provider_object)
        captured_at = self.clock()
        sanitized_history.append(
            {"phase": phase, "state": state, "capturedAt": captured_at, "providerObject": sanitized}
        )
        return {
            "phase": phase,
            "state": state,
            "capturedAt": captured_at,
            "sanitizedObjectSha256": _sha256_bytes(_canonical_bytes(sanitized)),
        }

    def _stream_terminal(
        self,
        task_id: str,
        snapshots: list[dict[str, Any]],
        sanitized_history: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        try:
            response = self.session.get(
                f"{self.base_url}{CREATE_PATH}/{task_id}/stream",
                headers={"Authorization": f"Bearer {TEST_MODE_API_KEY}", "Accept": "text/event-stream"},
                timeout=self.timeout_seconds,
                stream=True,
            )
            response.raise_for_status()
            event_type = "message"
            for raw_line in response.iter_lines(decode_unicode=True):
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if not line:
                    continue
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                data = json.loads(line.split(":", 1)[1].strip())
                if event_type == "error":
                    return None
                status = str(data.get("status", "UNKNOWN")).upper()
                snapshots.append(
                    self._snapshot(
                        "terminal" if status in TERMINAL_STATUSES else "progress",
                        status,
                        data,
                        sanitized_history,
                    )
                )
                if status in TERMINAL_STATUSES:
                    return data
        except Exception:
            # One SSE attempt only. Polling is the documented fallback; submit is never retried.
            return None
        return None

    def _poll_terminal(
        self,
        task_id: str,
        snapshots: list[dict[str, Any]],
        sanitized_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        for ordinal in range(self.max_polls):
            response = self.session.get(
                f"{self.base_url}{CREATE_PATH}/{task_id}",
                headers={"Authorization": f"Bearer {TEST_MODE_API_KEY}", "Accept": "application/json"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            task = response.json()
            if not isinstance(task, dict):
                raise MeshyTestModeError("Meshy test-mode task response is invalid")
            status = str(task.get("status", "UNKNOWN")).upper()
            snapshots.append(
                self._snapshot(
                    "terminal" if status in TERMINAL_STATUSES else "progress",
                    status,
                    task,
                    sanitized_history,
                )
            )
            if status in TERMINAL_STATUSES:
                return task
            if ordinal + 1 < self.max_polls:
                self.sleeper(self.poll_interval_seconds)
        raise MeshyTestModeError("Meshy test-mode polling timed out without retrying submit")
