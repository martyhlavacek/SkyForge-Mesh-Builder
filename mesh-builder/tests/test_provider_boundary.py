from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.providers import LocalDeterministicProvider, ProviderContractError, ProviderRequest, resolve_provider


def test_provider_models_are_immutable(tmp_path: Path):
    request = ProviderRequest(
        request_id="request-1",
        operation="authority_to_mesh",
        asset_id="fixture",
        asset_role="air_moving",
        authority_path=tmp_path / "authority.png",
        output_dir=tmp_path / "output",
    )
    with pytest.raises(AttributeError):
        request.asset_role = "ground_static"  # type: ignore[misc]


def test_local_capabilities_are_zero_cost_and_role_specific():
    capabilities = LocalDeterministicProvider().capabilities
    assert capabilities.provider_id == "local_deterministic"
    assert capabilities.reproducibility_class == "deterministic_reproducibility"
    assert capabilities.paid_dispatch_enabled is False
    assert capabilities.asset_roles == ("air_moving",)
    assert capabilities.supports("authority_to_mesh", "air_moving")
    assert not capabilities.supports("authority_to_mesh", "ground_static")


def test_registry_fails_closed_for_unknown_provider():
    with pytest.raises(ProviderContractError, match="Unsupported mesh provider"):
        resolve_provider("meshy_production")


def test_local_provider_rejects_unsupported_operation_before_generation(tmp_path: Path):
    authority = tmp_path / "authority.png"
    authority.write_bytes(b"not-consumed")
    request = ProviderRequest(
        request_id="request-1",
        operation="text_to_mesh",
        asset_id="fixture",
        asset_role="air_moving",
        authority_path=authority,
        output_dir=tmp_path / "output",
    )
    with pytest.raises(ProviderContractError, match="does not support"):
        LocalDeterministicProvider().execute(request)
    assert not request.output_dir.exists()


def test_local_adapter_is_behaviorally_invisible_and_logs_zero_cost(monkeypatch, tmp_path: Path):
    authority = tmp_path / "authority.png"
    authority.write_bytes(b"authority")
    output = tmp_path / "generated"
    output.mkdir()
    mesh = output / "authority_generated_mesh.glb"
    report = output / "authority_mesh_generation_report.json"
    preview = output / "preview.png"
    mesh.write_bytes(b"mesh-bytes")
    preview.write_bytes(b"preview")
    report_payload = {
        "source": {"authoritySha256": "a" * 64},
        "mesh": {"sha256": "b" * 64},
        "gateResults": {"passed": True},
    }
    report.write_text(json.dumps(report_payload), encoding="utf-8")

    class Generated:
        pass

    generated = Generated()
    generated.mesh_path = mesh
    generated.report_path = report
    generated.preview_paths = (preview,)
    generated.report = report_payload

    monkeypatch.setattr("app.providers.local_deterministic.generate_authority_mesh", lambda a, o: generated)
    request = ProviderRequest(
        request_id="request-1",
        operation="authority_to_mesh",
        asset_id="fixture",
        asset_role="air_moving",
        authority_path=authority,
        output_dir=output,
    )
    capture = LocalDeterministicProvider().execute(request)
    assert capture.mesh_path.read_bytes() == b"mesh-bytes"
    assert capture.task.expected_cost == "0"
    assert capture.task.consumed_cost == "0"
    events = [json.loads(line) for line in (output / "provider_events.jsonl").read_text().splitlines()]
    assert [event["eventType"] for event in events] == ["request_validated", "capture_completed"]
    assert all(event["consumedCost"] == "0" for event in events)
