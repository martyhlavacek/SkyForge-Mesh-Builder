from __future__ import annotations

import json
from pathlib import Path

from app.authority_mesh import GENERATOR_ID, GENERATOR_VERSION, generate_authority_mesh

from .base import MeshProvider
from .models import (
    ProviderCapabilities,
    ProviderCapture,
    ProviderContractError,
    ProviderEvent,
    ProviderRequest,
    ProviderTask,
)


class LocalDeterministicProvider(MeshProvider):
    PROVIDER_ID = "local_deterministic"
    PROVIDER_MODEL = GENERATOR_ID

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.PROVIDER_ID,
            operations=("authority_to_mesh",),
            reproducibility_class="deterministic_reproducibility",
            transport_mode="in_process",
            asset_roles=("air_moving",),
            cost_units="credits",
            paid_dispatch_enabled=False,
        )

    def execute(self, request: ProviderRequest) -> ProviderCapture:
        if not self.capabilities.supports(request.operation, request.asset_role):
            raise ProviderContractError(
                f"Provider {self.PROVIDER_ID!r} does not support operation={request.operation!r} "
                f"for assetRole={request.asset_role!r}"
            )
        generated = generate_authority_mesh(request.authority_path, request.output_dir)
        task = ProviderTask(
            provider_id=self.PROVIDER_ID,
            provider_model=f"{self.PROVIDER_MODEL}@{GENERATOR_VERSION}",
            request_id=request.request_id,
            request_digest=request.request_digest,
            task_id=request.request_digest,
            state="captured",
            expected_cost="0",
            consumed_cost="0",
            cost_units=self.capabilities.cost_units,
            reproducibility_class=self.capabilities.reproducibility_class,
        )
        capture = ProviderCapture(
            task=task,
            mesh_path=generated.mesh_path,
            report_path=generated.report_path,
            preview_paths=generated.preview_paths,
            evidence={
                "authoritySha256": generated.report["source"]["authoritySha256"],
                "meshSha256": generated.report["mesh"]["sha256"],
                "gateResults": generated.report["gateResults"],
                "providerVersion": GENERATOR_VERSION,
            },
        )
        self._write_events(request.output_dir, request, capture)
        return capture

    @staticmethod
    def _write_events(output_dir: Path, request: ProviderRequest, capture: ProviderCapture) -> Path:
        events = (
            ProviderEvent(
                sequence=1,
                event_type="request_validated",
                provider_id=capture.task.provider_id,
                request_id=request.request_id,
                request_digest=request.request_digest,
                state="accepted",
                expected_cost="0",
                consumed_cost="0",
                cost_units=capture.task.cost_units,
                details={"assetRole": request.asset_role, "operation": request.operation},
            ),
            ProviderEvent(
                sequence=2,
                event_type="capture_completed",
                provider_id=capture.task.provider_id,
                request_id=request.request_id,
                request_digest=request.request_digest,
                state="captured",
                expected_cost="0",
                consumed_cost="0",
                cost_units=capture.task.cost_units,
                details={
                    "meshSha256": capture.evidence["meshSha256"],
                    "reproducibilityClass": capture.task.reproducibility_class,
                },
            ),
        )
        path = output_dir / "provider_events.jsonl"
        path.write_text(
            "".join(json.dumps(event.as_json(), sort_keys=True, separators=(",", ":")) + "\n" for event in events),
            encoding="utf-8",
        )
        return path
