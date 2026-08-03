from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import trimesh
from jsonschema import Draft202012Validator
from PIL import Image

from app.reconstruction_v1.bundle import BundleError, approve_bundle, build_bundle, content_digest, validate_bundle
from app.reconstruction_v1.evidence import validate_glb, verify_manifest, write_manifest
from app.reconstruction_v1.orientation import OrientationError, proper_axis_rotations, rasterize, resolve_orientation
from app.reconstruction_v1.provider import (
    AuthorizationError,
    MeshyMultiImageProvider,
    ProviderError,
    SubmissionAuthorization,
)
from app.reconstruction_v1.state import StateError, TaskLog


class Response:
    def __init__(self, status_code=200, value=None, content=b""):
        self.status_code = status_code
        self._value = value if value is not None else {}
        self.content = content

    def json(self):
        return self._value


class Transport:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.error:
            raise self.error
        return self.responses.pop(0)


@pytest.fixture
def bundle_fixture(tmp_path: Path):
    paths = []
    for index, role in enumerate(("top", "front", "right")):
        path = tmp_path / f"{role}.png"
        Image.new("RGBA", (64 + index, 64), (20 + index, 30, 40, 255)).save(path)
        paths.append(path)
    bundle = build_bundle(tmp_path, asset_id="ship-1", profile_id="enemy_gunship", source_commit="a" * 40, created_at="2026-08-03T00:00:00Z", views=list(zip(("top", "front", "right"), paths, strict=True)))
    return tmp_path, approve_bundle(tmp_path, bundle, approved_at="2026-08-03T00:01:00Z", workflow_id="fixture")


def authorization(bundle, **updates):
    values = dict(paid_enabled=True, approved_bundle_digest=bundle["bundleDigest"], confirmed_bundle_digest=bundle["bundleDigest"], maximum_credits=20, api_key="canary-super-secret")
    values.update(updates)
    return SubmissionAuthorization(**values)


def test_bundle_exact_roles_supported_profile_and_approval(bundle_fixture):
    root, bundle = bundle_fixture
    assert validate_bundle(root, bundle) == bundle["bundleDigest"]
    schema = json.loads((Path(__file__).parents[1] / "profiles" / "multiview_authority_bundle_v1.schema.json").read_text())
    Draft202012Validator(schema).validate(bundle)
    with pytest.raises(BundleError, match="Unsupported"):
        build_bundle(root, asset_id="x", profile_id="bomber", source_commit="a", created_at="x", views=[])


@pytest.mark.parametrize("roles", [("top", "right", "front"), ("top", "front"), ("top", "front", "front")])
def test_missing_wrong_order_and_duplicate_views_fail(tmp_path: Path, roles):
    paths = []
    for index, role in enumerate(roles):
        path = tmp_path / f"{index}.png"
        Image.new("RGB", (8, 8)).save(path)
        paths.append((role, path))
    with pytest.raises(BundleError, match="exactly|Duplicate"):
        build_bundle(tmp_path, asset_id="x", profile_id="enemy_gunship", source_commit="a", created_at="x", views=paths)


def test_mutation_and_wrong_digest_invalidate_approval(bundle_fixture):
    root, bundle = bundle_fixture
    (root / "top.png").write_bytes(b"mutated")
    with pytest.raises(BundleError, match="mutated"):
        validate_bundle(root, bundle)


def test_contact_sheet_is_bound(bundle_fixture):
    root, bundle = bundle_fixture
    contact = root / "contact.png"
    Image.new("RGB", (16, 16)).save(contact)
    bundle["contactSheet"] = {"path": contact.name, "sha256": hashlib.sha256(contact.read_bytes()).hexdigest()}
    bundle["bundleDigest"] = content_digest(bundle)
    bundle = approve_bundle(root, bundle, approved_at="2026-08-03T00:02:00Z", workflow_id="fixture")
    validate_bundle(root, bundle)
    contact.write_bytes(b"mutated")
    with pytest.raises(BundleError, match="Contact sheet mutated"):
        validate_bundle(root, bundle)
    bundle["views"][0]["sha256"] = "0" * 64
    with pytest.raises(BundleError):
        validate_bundle(root, bundle)


def test_traversal_absolute_and_symlink_fail(bundle_fixture, tmp_path: Path):
    root, bundle = bundle_fixture
    for unsafe in ("../escape.png", "/tmp/escape.png"):
        changed = json.loads(json.dumps(bundle))
        changed["views"][0]["path"] = unsafe
        with pytest.raises(BundleError, match="Unsafe"):
            validate_bundle(root, changed, require_approved=False)
    link = root / "link.png"
    link.symlink_to(root / "top.png")
    changed = json.loads(json.dumps(bundle))
    changed["views"][0]["path"] = link.name
    with pytest.raises(BundleError):
        validate_bundle(root, changed, require_approved=False)


@pytest.mark.parametrize("updates, message", [
    ({"paid_enabled": False}, "disabled"),
    ({"confirmed_bundle_digest": "0" * 64}, "exact approved"),
    ({"maximum_credits": 19}, "exceeds"),
    ({"maximum_credits": "20"}, "exceeds"),
    ({"api_key": None}, "unavailable"),
    ({"api_key": "   "}, "unavailable"),
    ({"prior_task_id": "existing"}, "already exists"),
])
def test_paid_authorization_controls_fail_before_transport(bundle_fixture, updates, message):
    root, bundle = bundle_fixture
    transport = Transport()
    provider = MeshyMultiImageProvider(transport, environ={}, submission_registry=root / "registry")
    with pytest.raises(AuthorizationError, match=message):
        provider.submit_task(root, bundle, authorization(bundle, **updates))
    assert transport.calls == []


@pytest.mark.parametrize("environment", [{"CI": "true"}, {"GITHUB_ACTIONS": "true"}, {"SKYFORGE_PROVIDER_NETWORK_DISABLED": "1"}])
def test_process_level_ci_network_kill_switch(bundle_fixture, environment):
    root, bundle = bundle_fixture
    transport = Transport()
    with pytest.raises(AuthorizationError, match="disabled"):
        MeshyMultiImageProvider(
            transport, environ=environment, submission_registry=root / "registry"
        ).submit_task(root, bundle, authorization(bundle))
    assert not transport.calls


def test_request_profile_redaction_and_single_post(bundle_fixture):
    root, bundle = bundle_fixture
    transport = Transport([Response(value={"result": "task-1"})])
    provider = MeshyMultiImageProvider(transport, environ={}, submission_registry=root / "registry")
    request = provider.prepare_request(root, bundle)
    assert request["ai_model"] == "meshy-6" and len(request["image_urls"]) == 3
    assert request["should_texture"] is request["should_remesh"] is request["image_enhancement"] is False
    assert "data:" not in json.dumps(provider.redact_for_evidence(request))
    assert provider.submit_task(root, bundle, authorization(bundle)) == "task-1"
    assert provider.last_create_response == {"result": "task-1"}
    evidence_text = json.dumps(
        {"request": provider.redact_for_evidence(request), "response": provider.last_create_response}
    )
    assert "canary-super-secret" not in evidence_text and "data:" not in evidence_text
    assert len([call for call in transport.calls if call[0] == "POST"]) == 1
    with pytest.raises(AuthorizationError):
        provider.submit_task(root, bundle, authorization(bundle))


def test_ambiguous_post_never_retries_and_key_not_in_error(bundle_fixture):
    root, bundle = bundle_fixture
    transport = Transport(error=TimeoutError("timeout"))
    provider = MeshyMultiImageProvider(transport, environ={}, submission_registry=root / "registry")
    with pytest.raises(ProviderError) as caught:
        provider.submit_task(root, bundle, authorization(bundle))
    assert "canary-super-secret" not in str(caught.value)
    with pytest.raises(AuthorizationError):
        provider.submit_task(root, bundle, authorization(bundle))
    assert len(transport.calls) == 1


def test_persistent_registry_blocks_restart_and_copied_bundle(bundle_fixture, tmp_path: Path):
    root, bundle = bundle_fixture
    registry = tmp_path.parent / f"{tmp_path.name}-application-registry"
    first = MeshyMultiImageProvider(
        Transport([Response(value={"result": "task-1"})]), environ={}, submission_registry=registry
    )
    assert first.submit_task(root, bundle, authorization(bundle)) == "task-1"
    copied = tmp_path.parent / f"{tmp_path.name}-copied-bundle"
    shutil.copytree(root, copied)
    restarted = MeshyMultiImageProvider(Transport(), environ={}, submission_registry=registry)
    with pytest.raises(AuthorizationError, match="already exists"):
        restarted.submit_task(copied, bundle, authorization(bundle))
    unavailable = MeshyMultiImageProvider(Transport(), environ={})
    different_root = tmp_path.parent / f"{tmp_path.name}-different-copy"
    shutil.copytree(root, different_root)
    with pytest.raises(AuthorizationError, match="registry is unavailable"):
        unavailable.submit_task(different_root, bundle, authorization(bundle))


@pytest.mark.parametrize("status", [400, 401, 402, 429])
def test_submission_failure_classes(status, bundle_fixture):
    root, bundle = bundle_fixture
    provider = MeshyMultiImageProvider(
        Transport([Response(status_code=status)]),
        environ={},
        submission_registry=root / "registry",
    )
    with pytest.raises(ProviderError, match=str(status)):
        provider.submit_task(root, bundle, authorization(bundle))


def test_polling_and_download_fail_closed_without_post_retry():
    transport = Transport([Response(value={"status": "FAILED"}), Response(status_code=404, content=b"expired")])
    provider = MeshyMultiImageProvider(transport, environ={})
    assert provider.get_task("task")["status"] == "FAILED"
    with pytest.raises(ProviderError, match="expired"):
        provider.download_artifact("https://fixture.invalid/model.glb")
    assert all(call[0] == "GET" for call in transport.calls)


def test_download_all_artifacts_requires_and_validates_glb():
    payload = b"glTF" + b"\0" * 20
    provider = MeshyMultiImageProvider(Transport([Response(content=payload)]), environ={})
    assert provider.download_artifacts({"modelUrls": {"glb": "https://fixture.invalid/model.glb"}}) == {
        "glb": payload
    }
    with pytest.raises(ProviderError, match="GLB artifact URL"):
        provider.download_artifacts({"modelUrls": {}})


def test_polling_timeout_uses_get_only():
    transport = Transport([Response(value={"status": "IN_PROGRESS"}) for _ in range(3)])
    provider = MeshyMultiImageProvider(transport, environ={})
    with pytest.raises(ProviderError, match="timeout"):
        provider.poll_until_terminal("task", maximum_polls=3)
    assert len(transport.calls) == 3 and all(call[0] == "GET" for call in transport.calls)


def test_malformed_normalized_response_fails():
    provider = MeshyMultiImageProvider(Transport(), environ={})
    with pytest.raises(ProviderError, match="Malformed"):
        provider.normalize_response({"status": "UNKNOWN"})


def test_malformed_poll_and_corrupt_glb_fail(tmp_path: Path):
    provider = MeshyMultiImageProvider(Transport([Response(value=[])]), environ={})
    with pytest.raises(ProviderError, match="Malformed"):
        provider.get_task("task")
    path = tmp_path / "bad.glb"
    path.write_bytes(b"not a glb")
    with pytest.raises(ValueError, match="Corrupt"):
        validate_glb(path)


def test_append_only_lifecycle_and_illegal_transition(tmp_path: Path):
    log = TaskLog(tmp_path / "task.jsonl")
    log.append("PREPARED", timestamp="1")
    log.append("BUNDLE_APPROVED", timestamp="2")
    with pytest.raises(StateError, match="Illegal"):
        log.append("SUCCEEDED", timestamp="3")
    assert [event["state"] for event in log.events()] == ["PREPARED", "BUNDLE_APPROVED"]


def test_task_log_tampering_fails_closed(tmp_path: Path):
    log = TaskLog(tmp_path / "task.jsonl")
    log.append("PREPARED", timestamp="1")
    log.path.write_text(log.path.read_text().replace('"PREPARED"', '"SUBMITTED"'))
    with pytest.raises(StateError, match="integrity"):
        log.events()


def asymmetric_mesh():
    first = trimesh.creation.box((2.0, 1.0, 0.5))
    second = trimesh.creation.icosphere(subdivisions=1, radius=0.22)
    second.apply_translation((0.61, 0.21, 0.39))
    return trimesh.util.concatenate([first, second])


def test_proper_rotation_search_and_raw_bytes_preserved(tmp_path: Path):
    authority = asymmetric_mesh()
    masks = {role: rasterize(authority, role) for role in ("top", "front", "right")}
    rotated = authority.copy()
    transform = np.eye(4)
    transform[:3, :3] = proper_axis_rotations()[7]
    rotated.apply_transform(transform)
    raw = tmp_path / "raw.glb"
    raw.write_bytes(trimesh.exchange.gltf.export_glb(trimesh.Scene(rotated)))
    before = raw.read_bytes()
    canonical, report = resolve_orientation(rotated, masks, ambiguity_margin=0.0)
    assert len(report["scores"]) == 24 and report["winner"]["combined"] >= report["runnerUp"]["combined"]
    assert np.isclose(max(canonical.extents), 1.0)
    assert raw.read_bytes() == before


def test_symmetric_orientation_is_ambiguous():
    mesh = trimesh.creation.box()
    masks = {role: rasterize(mesh, role) for role in ("top", "front", "right")}
    with pytest.raises(OrientationError, match="Ambiguous"):
        resolve_orientation(mesh, masks)


def test_near_symmetric_orientation_can_fail_at_declared_margin():
    mesh = asymmetric_mesh()
    masks = {role: rasterize(mesh, role) for role in ("top", "front", "right")}
    _, report = resolve_orientation(mesh, masks, ambiguity_margin=0.0)
    with pytest.raises(OrientationError, match="Ambiguous"):
        resolve_orientation(mesh, masks, ambiguity_margin=report["margin"] + 1e-8)


def test_manifest_mutation_and_valid_glb(tmp_path: Path):
    path = tmp_path / "fixture.glb"
    path.write_bytes(trimesh.exchange.gltf.export_glb(trimesh.Scene(asymmetric_mesh())))
    assert validate_glb(path)["geometryCount"] >= 1
    manifest = tmp_path / "SHA256_MANIFEST.json"
    write_manifest(tmp_path, manifest)
    assert verify_manifest(tmp_path, manifest)
    path.write_bytes(path.read_bytes() + b"mutation")
    assert not verify_manifest(tmp_path, manifest)


def test_unknown_provider_and_default_routes_remain_isolated():
    from app.providers import ProviderContractError, resolve_provider

    with pytest.raises(ProviderContractError):
        resolve_provider("meshy_multi_image")
    source = (Path(__file__).parents[1] / "app" / "server.py").read_text(encoding="utf-8")
    assert "reconstruction_v1" not in source
