from __future__ import annotations

import copy
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator
from PIL import Image

from app.pilot_server import create_pilot_app
from app.reconstruction_v1.authorization import ContractSnapshot, build_authorization_projection
from app.reconstruction_v1.bundle import BundleError, approve_bundle, build_bundle, validate_bundle
from app.reconstruction_v1.cross_view import measure_cross_view
from app.reconstruction_v1.provider import ArtifactHostPolicy, AuthorizationError, MeshyMultiImageProvider
from app.reconstruction_v1.quarantine import QUARANTINED_HASHES, quarantine_digest, quarantine_record
from app.reconstruction_v1.reconstruction_input import (
    MULTIVIEW_KIND,
    SINGLE_VIEW_KIND,
    ReconstructionInputError,
    approve_single_view_input,
    build_single_view_input,
    input_kind,
    reconstruction_input_reference,
    single_view_content_digest,
    validate_reconstruction_input,
    validate_single_view_input,
)
from app.reconstruction_v1.state import TRANSITIONS, TaskLog
from app.reconstruction_v1.track_s import (
    APPROVED_TOP_SHA256,
    DECISION_RULES,
    MEASUREMENT_SPEC,
    PREREGISTRATION_POLICY,
    align_top_silhouettes,
    build_cost_governance,
    build_human_readability_review,
    build_run_preregistration,
    canonical_digest,
    decide_experiment,
    decision_rule_digest,
    fixed_request_digest,
    gameplay_silhouette_metrics,
    hard_validity_failures,
    measurement_spec_digest,
    preregistration_policy_digest,
    validate_cost_governance,
    validate_run_preregistration,
)

PACKAGE_ROOT = Path(__file__).parents[1]
REPOSITORY_ROOT = PACKAGE_ROOT.parent


class NoTransport:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        raise AssertionError("provider transport must not be reached")


def image(path: Path, *, color=(20, 40, 60), size=(80, 60)) -> Path:
    Image.new("RGB", size, color).save(path)
    return path


def single(root: Path, *, approve=True):
    root.mkdir(parents=True, exist_ok=True)
    source = image(root / "beauty.png")
    document = build_single_view_input(
        root,
        source_path=source,
        asset_id="track-s.gunship",
        profile_id="enemy_gunship",
        original_filename="approved_beauty.png",
        provenance="human_approved_beauty_reference",
        provenance_source_type="human_uploaded_approved_beauty",
        imported_at="2026-08-10T00:00:00Z",
        source_commit="a" * 40,
    )
    return approve_single_view_input(
        root, document, approved_at="2026-08-10T00:01:00Z", workflow_id="human"
    ) if approve else document


def snapshot(*, fresh=True) -> ContractSnapshot:
    return ContractSnapshot(
        path="docs/contracts/fixture.md",
        verification_date="2026-08-10T00:00:00Z",
        sha256="b" * 64,
        age_hours=1 if fresh else 48,
        freshness_status="FRESH" if fresh else "STALE",
    )


def valid_measurement() -> dict:
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask[16:48, 16:48] = 255
    return {
        "glbExists": True,
        "glbSha256": "a" * 64,
        "glbHashMatches": True,
        "glbParserValid": True,
        "blenderReloadSucceeded": True,
        "vertexCount": 100,
        "faceCount": 200,
        "nonFiniteVertexCount": 0,
        "degenerateFaceCount": 0,
        "manifoldEdgeCount": 300,
        "nonManifoldEdgeCount": 0,
        "watertight": True,
        "connectedComponentCount": 1,
        "largestComponentVolumeFractionPpm": 1000000,
        "rawBoundingBoxDeclaredGlbUnits": {
            "minimumMicrounits": [0, 0, 0],
            "maximumMicrounits": [1000000, 2000000, 500000],
        },
        "boundingBoxExtentsMicrounits": [1000000, 2000000, 500000],
        "perAxisExtentRatiosPpm": [500000, 1000000, 250000],
        "topSilhouetteNonEmpty": True,
        "gameplayMetrics": gameplay_silhouette_metrics(mask, clipped=False),
    }


def run_prereg(document, cost, *, committed="c" * 40):
    return build_run_preregistration(
        reconstruction_input_digest=document["inputDigest"],
        beauty_sha256=document["source"]["sha256"],
        validation_target_sha256=APPROVED_TOP_SHA256,
        validation_target_approval_identity="approved-top-workflow",
        candidate_source_commit="d" * 40,
        contract_snapshot_digest="b" * 64,
        cost_governance_digest=validate_cost_governance(cost),
        committed_at_commit=committed,
    )


def test_single_view_valid_construction_schema_digest_and_approval(tmp_path: Path):
    document = single(tmp_path, approve=False)
    schema = json.loads((PACKAGE_ROOT / "profiles/single_view_reconstruction_input_v1.schema.json").read_text())
    Draft202012Validator(schema).validate(document)
    assert document["inputKind"] == SINGLE_VIEW_KIND
    assert document["declaredRole"] == "beauty_three_quarter_reconstruction_reference"
    assert document["source"]["dimensions"] == [80, 60]
    assert document["source"]["mode"] == "RGB"
    assert single_view_content_digest(document) == document["inputDigest"]
    approved = approve_single_view_input(tmp_path, document, approved_at="at", workflow_id="human")
    assert validate_single_view_input(tmp_path, approved) == document["inputDigest"]
    reference = reconstruction_input_reference(tmp_path, approved)
    reference_schema = json.loads(
        (PACKAGE_ROOT / "profiles/reconstruction_input_reference_v1.schema.json").read_text()
    )
    Draft202012Validator(reference_schema).validate(reference)
    assert approved["approval"] == {
        "status": "APPROVED", "approvedAt": "at", "workflowId": "human", "inputDigest": document["inputDigest"]
    }


def test_single_view_absolute_traversal_symlink_and_regular_file_refusal(tmp_path: Path):
    document = single(tmp_path)
    for unsafe in ("/tmp/a.png", "../a.png"):
        changed = copy.deepcopy(document)
        changed["source"]["path"] = unsafe
        changed["inputDigest"] = single_view_content_digest(changed)
        with pytest.raises(ReconstructionInputError, match="Unsafe"):
            validate_single_view_input(tmp_path, changed, require_approved=False)
    link = tmp_path / "link.png"
    link.symlink_to(tmp_path / "beauty.png")
    changed = copy.deepcopy(document)
    changed["source"]["path"] = link.name
    changed["inputDigest"] = single_view_content_digest(changed)
    with pytest.raises(ReconstructionInputError, match="non-symlink"):
        validate_single_view_input(tmp_path, changed, require_approved=False)
    with pytest.raises(ReconstructionInputError, match="non-symlink"):
        build_single_view_input(
            tmp_path, source_path=tmp_path, asset_id="x", profile_id="enemy_gunship",
            original_filename="x", provenance="human_approved_beauty_reference",
            provenance_source_type="human", imported_at="x", source_commit="x"
        )


@pytest.mark.parametrize("field,value", [
    ("mode", "RGBA"),
    ("dimensions", [1, 1]),
    ("provenance", "fixture"),
    ("path", "other.png"),
    ("sha256", "0" * 64),
])
def test_single_view_covered_mutation_invalidates_approval(tmp_path: Path, field, value):
    document = single(tmp_path)
    changed = copy.deepcopy(document)
    changed["source"][field] = value
    with pytest.raises(ReconstructionInputError):
        validate_single_view_input(tmp_path, changed)


def test_single_view_byte_mutation_and_digest_determinism(tmp_path: Path):
    document = single(tmp_path)
    assert single_view_content_digest(document) == single_view_content_digest(copy.deepcopy(document))
    image(tmp_path / "beauty.png", color=(99, 20, 10))
    with pytest.raises(ReconstructionInputError, match="mutated"):
        validate_single_view_input(tmp_path, document)


def test_input_kind_common_routing_and_state_machine_unchanged(tmp_path: Path):
    document = single(tmp_path)
    assert input_kind(document) == SINGLE_VIEW_KIND
    assert reconstruction_input_reference(tmp_path, document)["inputKind"] == SINGLE_VIEW_KIND
    multiview_root = tmp_path / "multiview"
    multiview_root.mkdir()
    dimensions = {"top": (30, 40), "front": (30, 20), "right": (40, 20)}
    views = []
    for index, (role, size) in enumerate(dimensions.items()):
        canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        left, top = (64 - size[0]) // 2, (64 - size[1]) // 2
        for x in range(left, left + size[0]):
            for y in range(top, top + size[1]):
                canvas.putpixel((x, y), (20 + index, 40, 60, 255))
        path = multiview_root / f"{role}.png"
        canvas.save(path)
        views.append((role, path))
    bundle = build_bundle(
        multiview_root,
        asset_id="multi",
        profile_id="enemy_gunship",
        source_commit="a" * 40,
        created_at="at",
        views=views,
    )
    bundle = approve_bundle(multiview_root, bundle, approved_at="at", workflow_id="human")
    assert input_kind(bundle) == MULTIVIEW_KIND
    assert reconstruction_input_reference(multiview_root, bundle)["inputKind"] == MULTIVIEW_KIND
    assert set(TRANSITIONS) == {
        None, "PREPARED", "BUNDLE_APPROVED", "CONTRACT_REVERIFIED", "AUTHORIZATION_PREVIEWED",
        "COST_APPROVED", "SUBMITTING", "SUBMITTED", "POLLING", "SUCCEEDED", "DOWNLOADED",
        "VALIDATED", "FAILED", "CANCELED", "USER_ACCEPTED", "USER_REJECTED"
    }
    assert not any("SINGLE_VIEW" in str(state) or state == "ABORT" for state in TRANSITIONS)
    with pytest.raises(ReconstructionInputError, match="Unknown"):
        input_kind({"inputKind": "unknown"})


def test_provider_uses_same_endpoint_path_with_exactly_one_image_and_no_contact(tmp_path: Path):
    document = single(tmp_path)
    transport = NoTransport()
    provider = MeshyMultiImageProvider(transport, environ={"SKYFORGE_PROVIDER_NETWORK_DISABLED": "1"})
    request = provider.prepare_request(tmp_path, document)
    assert len(request["image_urls"]) == 1
    assert request["ai_model"] == "meshy-6" and request["should_texture"] is False
    assert transport.calls == []


def test_pilot_ui_imports_approves_single_view_and_remains_visibly_unsendable(tmp_path: Path):
    transport = NoTransport()
    provider = MeshyMultiImageProvider(
        transport,
        environ={"SKYFORGE_PROVIDER_NETWORK_DISABLED": "1"},
        submission_registry=tmp_path / "registry",
        require_authorization_digest=True,
    )
    key_calls = []
    app = create_pilot_app(
        workspace=tmp_path / "workspace",
        provider=provider,
        now=lambda: datetime(2026, 8, 10, tzinfo=UTC),
        api_key_loader=lambda: key_calls.append(True),
    )
    client = app.test_client()
    payload = io.BytesIO()
    Image.new("RGB", (80, 60), (20, 40, 60)).save(payload, format="PNG")
    response = client.post(
        "/single-view/import",
        data={
            "assetId": "track-s.gunship",
            "profileId": "enemy_gunship",
            "provenance": "human_approved_beauty_reference",
            "provenanceSourceType": "human_uploaded_approved_beauty",
            "beauty": (io.BytesIO(payload.getvalue()), "gunship_beauty.png"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    response = client.post("/bundle/approve", data={"workflowId": "human"})
    assert response.status_code == 200
    page = client.get("/").get_data(as_text=True)
    assert "single_view_v1" in page
    assert "UNRESOLVED" in page and "STALE" in page
    assert APPROVED_TOP_SHA256 in page and "reconstruction input: NO" in page
    assert client.post("/provider/submit").status_code == 409
    assert key_calls == [] and transport.calls == []


def test_mbs213_historical_multiview_and_new_track_s_session_are_isolated(tmp_path: Path):
    historical = tmp_path / "pilot_ui"
    historical.mkdir()
    dimensions = {"top": (30, 40), "front": (30, 20), "right": (40, 20)}
    views = []
    for index, (role, size) in enumerate(dimensions.items()):
        canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        left, top = (64 - size[0]) // 2, (64 - size[1]) // 2
        for x in range(left, left + size[0]):
            for y in range(top, top + size[1]):
                canvas.putpixel((x, y), (20 + index, 40, 60, 255))
        path = historical / f"authority_{role}.png"
        canvas.save(path)
        views.append((role, path))
    bundle = build_bundle(
        historical,
        asset_id="historical.mbs195",
        profile_id="enemy_gunship",
        source_commit="historical",
        created_at="historical",
        views=views,
    )
    bundle = approve_bundle(historical, bundle, approved_at="historical", workflow_id="historical-human")
    (historical / "MultiviewAuthorityBundleV1.json").write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    log = TaskLog(historical / "TaskLog.jsonl")
    log.append(
        "PREPARED",
        timestamp="2026-08-01T00:00:00Z",
        details={"inputKind": MULTIVIEW_KIND, "reconstructionInputDigest": bundle["bundleDigest"]},
    )
    log.append(
        "BUNDLE_APPROVED",
        timestamp="2026-08-01T00:01:00Z",
        details={"inputKind": MULTIVIEW_KIND, "reconstructionInputDigest": bundle["bundleDigest"]},
    )
    (historical / "authorization_preview.json").write_text('{"historical":true}\n', encoding="utf-8")
    corrupted = copy.deepcopy(bundle)
    corrupted["cameraDeclaration"] = "rejected_historical_measurement"
    (historical / "MultiviewAuthorityBundleV1.json").write_text(
        json.dumps(corrupted, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    before = {path.relative_to(historical): path.read_bytes() for path in historical.rglob("*") if path.is_file()}

    transport = NoTransport()
    provider = MeshyMultiImageProvider(
        transport,
        environ={"SKYFORGE_PROVIDER_NETWORK_DISABLED": "1"},
        submission_registry=tmp_path / "registry",
        require_authorization_digest=True,
    )
    key_calls = []
    app = create_pilot_app(
        workspace=historical,
        provider=provider,
        now=lambda: datetime(2026, 8, 10, tzinfo=UTC),
        api_key_loader=lambda: key_calls.append(True),
        enable_session_isolation=True,
    )
    client = app.test_client()

    historical_page = client.get("/").get_data(as_text=True)
    assert "HISTORICAL READ-ONLY RUN" in historical_page
    assert "Input kind</dt><dd>NOT SELECTED" in historical_page
    assert "Logged state</dt><dd>BUNDLE_APPROVED" in historical_page
    assert "Start new Track S single-view session" in historical_page
    assert client.get("/bundle/view/top?view=historical").status_code == 200

    response = client.post("/sessions/track-s/start")
    assert response.status_code == 200
    active_page = response.get_data(as_text=True)
    assert "Input kind</dt><dd>NOT SELECTED" in active_page
    assert "Logged state</dt><dd>NO TASK LOG" in active_page
    assert "Import and bind one beauty reference" in active_page
    assert "Profile and top/front/right import" not in active_page
    assert "No authorization preview exists" in active_page
    assert "UNRESOLVED" in active_page and "STALE" in active_page
    assert APPROVED_TOP_SHA256 in active_page and "reconstruction input: NO" in active_page
    assert before == {path.relative_to(historical): path.read_bytes() for path in historical.rglob("*") if path.is_file()}

    payload = io.BytesIO()
    Image.new("RGB", (80, 60), (20, 40, 60)).save(payload, format="PNG")
    response = client.post(
        "/single-view/import",
        data={
            "assetId": "track-s.gunship",
            "profileId": "enemy_gunship",
            "provenance": "human_approved_beauty_reference",
            "provenanceSourceType": "human_uploaded_approved_beauty",
            "beauty": (io.BytesIO(payload.getvalue()), "gunship_beauty.png"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    manager = app.extensions["skyforge_pilot_session_manager"]
    active = manager.active_runtime()
    assert active is not None and active.status()["inputKind"] == SINGLE_VIEW_KIND
    session_schema = json.loads(
        (PACKAGE_ROOT / "profiles/track_s_experiment_session_v1.schema.json").read_text()
    )
    Draft202012Validator(session_schema).validate(manager.active_session_identity())
    pointer = json.loads(manager.active_pointer_path.read_text())
    Draft202012Validator(session_schema["$defs"]["activePointer"]).validate(pointer)
    assert active.current_state() == "PREPARED"
    assert active.authorization_path.exists() is False
    single_digest = active.load_reconstruction_input(require_approved=False)["inputDigest"]
    assert single_digest != bundle["bundleDigest"]
    response = client.post("/bundle/approve", data={"workflowId": "track-s-human"})
    assert response.status_code == 200
    assert active.task_log.events()[-1]["details"] == {
        "inputKind": SINGLE_VIEW_KIND,
        "reconstructionInputDigest": single_digest,
    }
    assert client.get("/?view=historical").status_code == 200
    assert client.get("/?view=active").status_code == 200
    assert before == {path.relative_to(historical): path.read_bytes() for path in historical.rglob("*") if path.is_file()}
    assert client.post("/provider/submit").status_code == 409
    assert key_calls == [] and transport.calls == []


@pytest.mark.parametrize("denied", sorted(QUARANTINED_HASHES))
def test_quarantine_refuses_single_at_construction_approval_authorization_and_provider(tmp_path: Path, monkeypatch, denied):
    import app.reconstruction_v1.reconstruction_input as inputs

    approved_root = tmp_path / "approved"
    document = single(approved_root)
    source = image(tmp_path / "beauty.png")
    monkeypatch.setattr(inputs, "_sha256", lambda _path: denied)
    with pytest.raises(ValueError, match="quarantined"):
        build_single_view_input(
            tmp_path, source_path=source, asset_id="x", profile_id="enemy_gunship",
            original_filename="beauty.png", provenance="human_approved_beauty_reference",
            provenance_source_type="human", imported_at="x", source_commit="x"
        )
    document["source"]["sha256"] = denied
    document["inputDigest"] = single_view_content_digest(document)
    document["approval"]["inputDigest"] = document["inputDigest"]
    with pytest.raises(ValueError, match="quarantined"):
        validate_reconstruction_input(approved_root, document)
    provider = MeshyMultiImageProvider(NoTransport(), environ={})
    with pytest.raises(ValueError, match="quarantined"):
        provider.prepare_request(approved_root, document)


def test_quarantine_policy_file_top_allowed_and_historical_evidence_inspectable():
    committed = json.loads((PACKAGE_ROOT / "profiles/reconstruction_input_quarantine_v1.json").read_text())
    assert committed == quarantine_record()
    assert APPROVED_TOP_SHA256 not in QUARANTINED_HASHES
    assert len(quarantine_digest()) == 64
    workspace = PACKAGE_ROOT / "workspace/pilot_ui"
    if all((workspace / f"authority_{role}.png").exists() for role in ("top", "front", "right")):
        record = measure_cross_view({role: workspace / f"authority_{role}.png" for role in ("top", "front", "right")})
        assert record["result"] == "FAIL"


def test_new_multiview_build_refuses_quarantine_but_historical_validation_has_no_quarantine_branch(tmp_path: Path, monkeypatch):
    import app.reconstruction_v1.bundle as bundle_module

    dimensions = {"top": (30, 40), "front": (30, 20), "right": (40, 20)}
    paths = []
    for role, size in dimensions.items():
        canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        left, top = (64 - size[0]) // 2, (64 - size[1]) // 2
        for x in range(left, left + size[0]):
            for y in range(top, top + size[1]):
                canvas.putpixel((x, y), (20, 40, 60, 255))
        path = tmp_path / f"{role}.png"
        canvas.save(path)
        paths.append((role, path))
    actual = bundle_module.sha256_file
    denied = next(iter(QUARANTINED_HASHES))
    monkeypatch.setattr(bundle_module, "sha256_file", lambda path: denied if path.name == "front.png" else actual(path))
    with pytest.raises(BundleError, match="quarantined"):
        build_bundle(tmp_path, asset_id="x", profile_id="enemy_gunship", source_commit="x", created_at="x", views=paths)
    monkeypatch.setattr(bundle_module, "sha256_file", actual)
    eligible = build_bundle(
        tmp_path, asset_id="x", profile_id="enemy_gunship", source_commit="x", created_at="x", views=paths
    )
    monkeypatch.setattr(
        bundle_module,
        "assert_reconstruction_hashes_eligible",
        lambda _hashes: (_ for _ in ()).throw(bundle_module.QuarantineError("quarantined approval")),
    )
    with pytest.raises(BundleError, match="quarantined approval"):
        approve_bundle(tmp_path, eligible, approved_at="at", workflow_id="human")
    assert "quarantine" not in validate_bundle.__code__.co_names


def test_cost_model_unresolved_missing_and_stale_fail_closed():
    unresolved = build_cost_governance(snapshot(fresh=False))
    assert unresolved["sequentialExperimentCredits"] == {"oneView": 20, "onePlusTwoView": 40, "onePlusTwoPlusThreeView": 60}
    assert unresolved["automaticRetryCount"] == 0 and unresolved["automaticSecondTask"] is False
    with pytest.raises(AuthorizationError, match="unresolved"):
        validate_cost_governance(unresolved)
    missing = copy.deepcopy(unresolved)
    missing.pop("failedTaskChargingDisposition")
    with pytest.raises(AuthorizationError, match="unresolved"):
        validate_cost_governance(missing)
    resolved = build_cost_governance(snapshot(), failed_task_charging_disposition="NOT_CHARGED", failed_task_charging_evidence="synthetic_fixture")
    assert len(validate_cost_governance(resolved)) == 64


def test_policy_file_and_digests_are_committed_and_deterministic():
    committed = json.loads((PACKAGE_ROOT / "profiles/track_s_experiment_preregistration_v1.json").read_text())
    assert committed == PREREGISTRATION_POLICY
    assert preregistration_policy_digest() == canonical_digest(committed)
    assert measurement_spec_digest() == canonical_digest(MEASUREMENT_SPEC)
    assert decision_rule_digest() == canonical_digest(DECISION_RULES)
    assert fixed_request_digest() == canonical_digest(PREREGISTRATION_POLICY["providerRequest"])
    camera = committed["measurementSpec"]["gameplayCamera"]["cameraTransform"]
    assert camera == {
        "azimuthDegrees": 135,
        "elevationDegrees": 75,
        "rollDegrees": 0,
        "lookAt": "reloaded_glb_bounding_box_center",
        "objectOrigin": "reloaded_glb_declared_origin",
        "orthographicScale": "maximum_projected_extent_times_1100000ppm",
    }


def test_run_preregistration_required_committed_and_mutation_resistant(tmp_path: Path):
    document = single(tmp_path)
    cost = build_cost_governance(snapshot(), failed_task_charging_disposition="NOT_CHARGED", failed_task_charging_evidence="synthetic")
    prereg = run_prereg(document, cost)
    assert validate_run_preregistration(
        prereg,
        executing_commit="d" * 40,
        is_ancestor=lambda old, _new: old in {"c" * 40, "d" * 40},
    ) == prereg["preregistrationDigest"]
    for field in ("measurementSpecDigest", "decisionRuleDigest", "fixedRequestDigest", "quarantineDigest"):
        changed = copy.deepcopy(prereg)
        changed[field] = "0" * 64
        changed["preregistrationDigest"] = canonical_digest({k: v for k, v in changed.items() if k != "preregistrationDigest"})
        with pytest.raises(AuthorizationError):
            validate_run_preregistration(changed, executing_commit="d" * 40, is_ancestor=lambda _a, _b: True)
    with pytest.raises(AuthorizationError, match="uncommitted"):
        validate_run_preregistration(prereg, executing_commit="d" * 40, is_ancestor=lambda _a, _b: False)


def test_track_s_authorization_binds_every_gate_and_stale_or_unresolved_refuses(tmp_path: Path):
    document = single(tmp_path)
    policy = ArtifactHostPolicy("fixture-hosts.v1", frozenset({"assets.meshy.ai"}), lambda _h: ("8.8.8.8",))
    cost = build_cost_governance(snapshot(), failed_task_charging_disposition="NOT_CHARGED", failed_task_charging_evidence="synthetic")
    prereg = run_prereg(document, cost)
    package = tmp_path / "package"
    package.mkdir()
    (package / "PRODUCER_SOURCE_BINDING.json").write_text(json.dumps({"treeManifestSha256": "a" * 64}))
    context = {"costGovernance": cost, "runPreregistration": prereg, "executingCommit": "d" * 40, "isAncestor": lambda _a, _b: True, "networkKillSwitchState": "ENABLED", "maximumRedirects": 4}
    projection = build_authorization_projection(package, tmp_path, document, contract_snapshot=snapshot(), artifact_host_policy=policy, track_s_context=context)
    assert projection["inputKind"] == SINGLE_VIEW_KIND
    assert projection["trackS"]["automaticRetry"] is False
    assert projection["trackS"]["validationTarget"]["isReconstructionInput"] is False
    with pytest.raises(AuthorizationError, match="stale"):
        build_authorization_projection(package, tmp_path, document, contract_snapshot=snapshot(fresh=False), artifact_host_policy=policy, track_s_context=context)
    unresolved = {**context, "costGovernance": build_cost_governance(snapshot())}
    with pytest.raises(AuthorizationError, match="unresolved"):
        build_authorization_projection(package, tmp_path, document, contract_snapshot=snapshot(), artifact_host_policy=policy, track_s_context=unresolved)
    with pytest.raises(AuthorizationError, match="preregistration"):
        build_authorization_projection(package, tmp_path, document, contract_snapshot=snapshot(), artifact_host_policy=policy)


def top_shape() -> np.ndarray:
    mask = np.zeros((1024, 1024), dtype=np.uint8)
    mask[300:740, 430:590] = 255
    mask[300:420, 590:700] = 255
    return mask


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_iou_alignment_selects_exact_quarter_turns(rotation):
    target = top_shape()
    candidate = np.rot90(target, k=rotation // 90)
    result = align_top_silhouettes(candidate, target)
    expected = rotation
    assert result["selectedRotationDegrees"] == expected
    assert result["selectedIouPpm"] == 1000000
    assert result["reflectionUsed"] is result["anisotropicScaleUsed"] is result["translationSearchUsed"] is False
    assert result["resolution"] == [1024, 1024] and result["alphaThreshold"] == 128


def test_iou_tie_break_centroid_only_and_no_mirror():
    target = np.zeros((1024, 1024), dtype=np.uint8)
    target[400:624, 400:624] = 255
    candidate = np.zeros_like(target)
    candidate[100:324, 700:924] = 255
    result = align_top_silhouettes(candidate, target)
    assert result["selectedRotationDegrees"] == 0
    assert all(item["iouPpm"] == 1000000 for item in result["samples"])


def test_gameplay_metrics_and_hard_gate_matrix():
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask[16:48, 16:48] = 255
    metrics = gameplay_silhouette_metrics(mask, clipped=False)
    assert metrics["foregroundPixelCount"] == 1024 and metrics["largestComponentPixelFractionPpm"] == 1000000
    valid = valid_measurement()
    records_schema = json.loads((PACKAGE_ROOT / "profiles/track_s_records_v1.schema.json").read_text())
    Draft202012Validator(records_schema["$defs"]["measurementResult"]).validate(valid)
    assert hard_validity_failures(valid) == []
    mutations = {
        "glbExists": False,
        "glbHashMatches": False,
        "glbParserValid": False,
        "blenderReloadSucceeded": False,
        "vertexCount": 0,
        "faceCount": 0,
        "nonFiniteVertexCount": 1,
        "degenerateFaceCount": 1,
        "manifoldEdgeCount": -1,
        "nonManifoldEdgeCount": -1,
        "watertight": False,
        "connectedComponentCount": 17,
        "largestComponentVolumeFractionPpm": 599999,
        "boundingBoxExtentsMicrounits": [1, 2, 3],
        "rawBoundingBoxDeclaredGlbUnits": {"minimumMicrounits": [0, 0], "maximumMicrounits": [1, 2]},
        "perAxisExtentRatiosPpm": [1, 0, 1],
        "topSilhouetteNonEmpty": False,
    }
    for key, value in mutations.items():
        changed = valid_measurement()
        changed[key] = value
        assert hard_validity_failures(changed)
    for field, value in (("foregroundPixelCount", 127), ("clipped", True), ("largestComponentPixelFractionPpm", 799999)):
        changed = valid_measurement()
        changed["gameplayMetrics"][field] = value
        assert hard_validity_failures(changed)


@pytest.mark.parametrize("iou,readability,expected", [
    (800000, "READABLE", "CONTINUE_SINGLE_VIEW"),
    (799999, "READABLE", "ESCALATE_TWO_VIEW_ELIGIBLE"),
    (650000, "READABLE", "ESCALATE_TWO_VIEW_ELIGIBLE"),
    (649999, "READABLE", "ABORT_MESHY"),
    (900000, "UNREADABLE", "ABORT_MESHY"),
])
def test_experiment_decision_bands_create_no_task(iou, readability, expected):
    review = build_human_readability_review(
        verdict=readability,
        reviewer="Marty",
        reviewed_at="2026-08-10T00:00:00Z",
        artifact_sha256="a" * 64,
    )
    decision = decide_experiment(top_iou_ppm=iou, measurement_record=valid_measurement(), human_readability=review)
    assert decision["decision"] == expected
    assert decision["createsProviderTask"] is decision["authorizesAnotherTask"] is False
    assert decision["automaticRetryCount"] == 0


def test_hard_failure_forces_abort_without_lifecycle_or_provider_action():
    record = valid_measurement()
    record["watertight"] = False
    review = build_human_readability_review(
        verdict="READABLE", reviewer="Marty", reviewed_at="at", artifact_sha256="a" * 64
    )
    decision = decide_experiment(top_iou_ppm=900000, measurement_record=record, human_readability=review)
    assert decision["decision"] == "ABORT_MESHY" and "NON_WATERTIGHT" in decision["reasonCodes"]
    assert "ABORT_MESHY" not in TRANSITIONS
