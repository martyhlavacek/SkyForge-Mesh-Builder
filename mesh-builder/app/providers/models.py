from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping


class ProviderContractError(RuntimeError):
    """Raised when a provider request cannot be handled without changing semantics."""


@dataclass(frozen=True)
class ProviderCapabilities:
    provider_id: str
    operations: tuple[str, ...]
    reproducibility_class: str
    transport_mode: str
    asset_roles: tuple[str, ...]
    cost_units: str
    paid_dispatch_enabled: bool

    def supports(self, operation: str, asset_role: str) -> bool:
        return operation in self.operations and asset_role in self.asset_roles


@dataclass(frozen=True)
class ProviderRequest:
    request_id: str
    operation: str
    asset_id: str
    asset_role: str
    authority_path: Path
    output_dir: Path
    provider_options: Mapping[str, Any] = field(default_factory=dict)

    @property
    def request_digest(self) -> str:
        payload = {
            "assetId": self.asset_id,
            "assetRole": self.asset_role,
            "authoritySha256": _sha256_file(self.authority_path),
            "operation": self.operation,
            "providerOptions": dict(self.provider_options),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ProviderTask:
    provider_id: str
    provider_model: str
    request_id: str
    request_digest: str
    task_id: str
    state: str
    expected_cost: str
    consumed_cost: str
    cost_units: str
    reproducibility_class: str


@dataclass(frozen=True)
class ProviderCapture:
    task: ProviderTask
    mesh_path: Path
    report_path: Path
    preview_paths: tuple[Path, ...]
    evidence: Mapping[str, Any]


@dataclass(frozen=True)
class ProviderEvent:
    sequence: int
    event_type: str
    provider_id: str
    request_id: str
    request_digest: str
    state: str
    expected_cost: str
    consumed_cost: str
    cost_units: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schemaVersion"] = "skyforge.provider-event.v1"
        return {
            "schemaVersion": payload.pop("schemaVersion"),
            "sequence": payload.pop("sequence"),
            "eventType": payload.pop("event_type"),
            "providerId": payload.pop("provider_id"),
            "requestId": payload.pop("request_id"),
            "requestDigest": payload.pop("request_digest"),
            "state": payload.pop("state"),
            "expectedCost": payload.pop("expected_cost"),
            "consumedCost": payload.pop("consumed_cost"),
            "costUnits": payload.pop("cost_units"),
            "details": payload.pop("details"),
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
