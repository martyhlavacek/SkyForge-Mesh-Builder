from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.providers.meshy_test_mode import (
    BASE_URL,
    CREATE_PATH,
    TEST_MODE_API_KEY,
    MeshyTestModeAdapter,
    MeshyTestModeError,
    sanitize_provider_object,
)
from app.providers.models import ProviderContractError
from app.providers.registry import resolve_provider


class FakeResponse:
    def __init__(
        self,
        *,
        json_value: Any | None = None,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
        lines: list[str] | None = None,
        status_code: int = 200,
    ) -> None:
        self._json = json_value
        self.content = content
        self.headers = headers or {}
        self._lines = lines or []
        self.status_code = status_code

    def json(self) -> Any:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_lines(self, decode_unicode: bool = False):
        return iter(self._lines)


class FakeSession:
    def __init__(self, *, stream_response: FakeResponse, poll_responses=None, asset_response=None) -> None:
        self.stream_response = stream_response
        self.poll_responses = list(poll_responses or [])
        self.asset_response = asset_response or FakeResponse(
            content=b"glTF-test-mode-fixed-sample", headers={"Content-Type": "model/gltf-binary"}
        )
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.gets: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, **kwargs: Any):
        self.posts.append((url, kwargs))
        return FakeResponse(json_value={"result": "test-task-123"})

    def get(self, url: str, **kwargs: Any):
        self.gets.append((url, kwargs))
        if url.endswith("/stream"):
            return self.stream_response
        if url.startswith("https://assets.meshy.ai/"):
            return self.asset_response
        if self.poll_responses:
            return self.poll_responses.pop(0)
        raise AssertionError(f"Unexpected GET {url}")


def authority(tmp_path: Path) -> Path:
    path = tmp_path / "authority.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\ntransport-test")
    return path


def terminal_task(*, consumed_credits: int = 0) -> dict[str, Any]:
    return {
        "id": "test-task-123",
        "type": "image-to-3d",
        "status": "SUCCEEDED",
        "progress": 100,
        "model_urls": {
            "glb": "https://assets.meshy.ai/fixed/tasks/test-task-123/model.glb?Expires=999&Signature=secret"
        },
        "thumbnail_url": "https://assets.meshy.ai/fixed/preview.png?Expires=999&Signature=secret",
        "expires_at": 1785600000000,
        "consumed_credits": consumed_credits,
    }


def sse_terminal_response(*, consumed_credits: int = 0) -> FakeResponse:
    return FakeResponse(
        lines=[
            "event: message",
            'data: {"id":"test-task-123","status":"IN_PROGRESS","progress":50}',
            "event: message",
            "data: " + json.dumps(terminal_task(consumed_credits=consumed_credits), separators=(",", ":")),
        ],
        headers={"Content-Type": "text/event-stream"},
    )


def adapter(session: FakeSession) -> MeshyTestModeAdapter:
    return MeshyTestModeAdapter(
        session,
        network_enabled=True,
        clock=lambda: "2026-08-01T12:00:00+00:00",
        sleeper=lambda _seconds: None,
        max_polls=3,
    )


def test_test_mode_payload_and_public_auth_shape_are_fixed(tmp_path: Path):
    session = FakeSession(stream_response=sse_terminal_response())
    result = adapter(session).run(authority_path=authority(tmp_path), output_dir=tmp_path / "evidence")
    assert len(session.posts) == 1
    url, call = session.posts[0]
    assert url == BASE_URL + CREATE_PATH
    assert call["headers"]["Authorization"] == f"Bearer {TEST_MODE_API_KEY}"
    assert call["json"] == {
        "image_url": call["json"]["image_url"],
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
    assert call["json"]["image_url"].startswith("data:image/png;base64,")
    assert result.provider_status == "SUCCEEDED"


def test_sse_progress_then_terminal_capture_creates_transport_only_pep(tmp_path: Path):
    session = FakeSession(stream_response=sse_terminal_response(consumed_credits=0))
    result = adapter(session).run(authority_path=authority(tmp_path), output_dir=tmp_path / "evidence")
    pep = json.loads(result.pep_path.read_text())
    diagnostic = json.loads(result.result_path.read_text())
    assert pep["evidenceClass"] == "transport_lifecycle_only"
    assert pep["promotionPermitted"] is False
    assert pep["expiresAt"].startswith("2026-")
    assert [item["phase"] for item in pep["taskSnapshots"]] == ["submit", "progress", "terminal"]
    assert diagnostic["vmpProduced"] is False
    assert diagnostic["approvedAssetProduced"] is False
    assert diagnostic["paidLedgerEntryCreated"] is False
    assert diagnostic["productionCredentialRead"] is False
    assert diagnostic["consumedCreditsArePaidReconciliationProof"] is False
    assert result.vmp_produced is False
    assert not list((tmp_path / "evidence").glob("*.sfmeshpack"))
    assert not (tmp_path / "evidence" / "asset.json").exists()


def test_sse_failure_falls_back_to_polling_without_resubmitting(tmp_path: Path):
    session = FakeSession(
        stream_response=FakeResponse(status_code=503),
        poll_responses=[
            FakeResponse(json_value={"id": "test-task-123", "status": "PENDING", "progress": 0}),
            FakeResponse(json_value=terminal_task()),
        ],
    )
    result = adapter(session).run(authority_path=authority(tmp_path), output_dir=tmp_path / "evidence")
    assert result.provider_status == "SUCCEEDED"
    assert len(session.posts) == 1
    task_gets = [url for url, _ in session.gets if url.endswith("test-task-123")]
    assert len(task_gets) == 2


def test_poll_timeout_never_retries_submit(tmp_path: Path):
    session = FakeSession(
        stream_response=FakeResponse(status_code=503),
        poll_responses=[FakeResponse(json_value={"status": "IN_PROGRESS"}) for _ in range(3)],
    )
    with pytest.raises(MeshyTestModeError, match="timed out"):
        adapter(session).run(authority_path=authority(tmp_path), output_dir=tmp_path / "evidence")
    assert len(session.posts) == 1


def test_sanitization_removes_signed_queries_secrets_and_local_paths(tmp_path: Path):
    sanitized = sanitize_provider_object(
        {
            "authorization": "Bearer production-secret",
            "model_url": "https://assets.meshy.ai/a/model.glb?Expires=1&Signature=x",
            "local_path": "/Users/marty/private.glb",
        }
    )
    encoded = json.dumps(sanitized, sort_keys=True)
    assert "production-secret" not in encoded
    assert "Signature=x" not in encoded
    assert "/Users/marty" not in encoded
    assert sanitized["model_url"]["signedQueryRemoved"] is True


def test_consumed_credits_parse_is_informational_not_reconciliation(tmp_path: Path):
    session = FakeSession(stream_response=sse_terminal_response(consumed_credits=17))
    result = adapter(session).run(authority_path=authority(tmp_path), output_dir=tmp_path / "evidence")
    diagnostic = json.loads(result.result_path.read_text())
    assert result.consumed_credits_informational == "17"
    assert diagnostic["consumedCreditsInformational"] == "17"
    assert diagnostic["consumedCreditsArePaidReconciliationProof"] is False


def test_network_requires_explicit_gate_and_exact_host_allowlist(tmp_path: Path):
    session = FakeSession(stream_response=sse_terminal_response())
    disabled = MeshyTestModeAdapter(session, network_enabled=False)
    with pytest.raises(MeshyTestModeError, match="Network is disabled"):
        disabled.run(authority_path=authority(tmp_path), output_dir=tmp_path / "evidence")
    for origin in (
        "http://api.meshy.ai",
        "https://evil.example",
        "https://api.meshy.ai.evil.example",
        "https://user:pass@api.meshy.ai",
        "https://api.meshy.ai/extra",
    ):
        with pytest.raises(MeshyTestModeError, match="allowlisted|exact"):
            MeshyTestModeAdapter(session, network_enabled=True, base_url=origin)


def test_fixed_sample_path_is_not_registered_as_normal_provider():
    with pytest.raises(ProviderContractError, match="Unsupported"):
        resolve_provider("meshy_test_mode")


def test_module_has_no_keychain_or_production_credential_access():
    source = (Path(__file__).resolve().parents[1] / "app" / "providers" / "meshy_test_mode.py").read_text()
    lowered = source.lower()
    assert "keychain" not in lowered
    assert "settings_store" not in lowered
    assert "get_secret" not in lowered
    assert "os.environ" not in source


def test_asset_download_host_is_restricted(tmp_path: Path):
    task = terminal_task()
    task["model_urls"]["glb"] = "https://untrusted.example/model.glb"
    session = FakeSession(
        stream_response=FakeResponse(lines=["event: message", "data: " + json.dumps(task)])
    )
    with pytest.raises(MeshyTestModeError, match="asset host"):
        adapter(session).run(authority_path=authority(tmp_path), output_dir=tmp_path / "evidence")


def test_complete_sanitized_lifecycle_history_is_captured(tmp_path: Path):
    session = FakeSession(stream_response=sse_terminal_response())
    result = adapter(session).run(authority_path=authority(tmp_path), output_dir=tmp_path / "evidence")
    history_path = result.evidence_directory / "sanitized_task_history.json"
    history = json.loads(history_path.read_text())
    assert [entry["phase"] for entry in history] == ["submit", "progress", "terminal"]
    encoded = history_path.read_text()
    assert "Signature=secret" not in encoded
    assert TEST_MODE_API_KEY not in encoded
    pep = json.loads(result.pep_path.read_text())
    assert any(item["path"] == history_path.name for item in pep["capturedArtifacts"])
