from __future__ import annotations

import ast
import hashlib
import io
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from app.pilot_server import create_pilot_app
from app.reconstruction_v1.authorization import (
    AUTHORIZATION_SCHEMA_VERSION,
    FIXED_REQUEST,
    authorization_digest,
    build_authorization_projection,
)
from app.reconstruction_v1.bundle import BundleError
from app.reconstruction_v1.pilot import PilotError, PilotRuntime, load_pilot_config
from app.reconstruction_v1.preflight import preflight_artifact_url
from app.reconstruction_v1.provider import (
    ArtifactHostPolicy,
    AuthorizationError,
    MeshyMultiImageProvider,
    ProviderError,
    SubmissionAuthorization,
)
from app.reconstruction_v1.state import TRANSITIONS, StateError, TaskLog

PACKAGE_ROOT = Path(__file__).parents[1]
REPOSITORY_ROOT = PACKAGE_ROOT.parent
BASELINE = "v0.7.1-accepted-baseline"
PRESERVED_HASHES = {
    "mesh-builder/app/server.py": "7363750693bde1828b72864e07d82675c19b934f52c6fcc75ab3de024c2fa7c5",
    "mesh-builder/app/templates/index.html": "9f721c813b4d345241903d3eaf36f00dcd159e756da22e8f86ad3ba98c2f0e7a",
    "mesh-builder/app/static/style.css": "b2c579b9e28ddfeb3f08d41daa546c1e5bb7e1a5accdaded7571880ae72c1baf",
    "mesh-builder/app/pipeline.py": "aa567b7aff0d6888a1f30d4ce530219bd15dedbb267b552d85dd9f5c843a050f",
    "mesh-builder/app/bootstrap.py": "b5c53edb1c81e2582d135902ce2a6bf5a476d2d1ee2b6732939fd0c1124446d0",
}


class NoTransport:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        raise AssertionError("transport must not be reached")


class Response:
    def __init__(self, status_code=200, *, value=None, content=b"", headers=None, url=None):
        self.status_code = status_code
        self._value = value or {}
        self.content = content
        self.headers = headers or {}
        self.url = url

    def json(self):
        return self._value


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def image_bytes(color, *, mode="RGB"):
    stream = io.BytesIO()
    Image.new(mode, (32, 24), color).save(stream, format="PNG")
    return stream.getvalue()


def make_contract(root: Path, verified: datetime) -> str:
    relative = "docs/contracts/MESHY_CONTRACT_REVERIFICATION_2026-08-04.md"
    path = root / relative
    path.parent.mkdir(parents=True)
    stamp = verified.astimezone(UTC).isoformat().replace("+00:00", "Z")
    path.write_text(f"# Fixture contract\n\nRetrieved at `{stamp}`.\n", encoding="utf-8")
    return relative


def runtime_fixture(tmp_path: Path, *, fresh=True, provider=None):
    repository = tmp_path / "repository"
    package = repository / "mesh-builder"
    package.mkdir(parents=True)
    now = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
    verified = now - timedelta(hours=1 if fresh else 48)
    make_contract(repository, verified)
    (package / "PRODUCER_SOURCE_BINDING.json").write_text(
        json.dumps({"treeManifestSha256": "a" * 64}), encoding="utf-8"
    )
    active = provider or MeshyMultiImageProvider(
        NoTransport(),
        environ={"SKYFORGE_PROVIDER_NETWORK_DISABLED": "1"},
        artifact_host_policy=ArtifactHostPolicy(
            "fixture.host-policy.v1", frozenset({"assets.meshy.ai"}), lambda _host: ("8.8.8.8",)
        ),
        require_authorization_digest=True,
    )
    runtime = PilotRuntime(package, package / "workspace" / "pilot_ui", active, now=lambda: now, sleeper=lambda _v: None)
    runtime.config = {**runtime.config, "contractSnapshotPath": "docs/contracts/MESHY_CONTRACT_REVERIFICATION_2026-08-04.md"}
    return runtime


def import_valid(runtime: PilotRuntime, *, provenance="human_authority_candidate"):
    return runtime.import_bundle(
        profile_id="enemy_gunship",
        asset_id="pilot.ship",
        uploads=[
            ("top", "top.png", image_bytes((255, 0, 0)), provenance),
            ("front", "front.png", image_bytes((0, 255, 0)), provenance),
            ("right", "right.png", image_bytes((0, 0, 255)), provenance),
        ],
    )


def approve_and_reverify(runtime: PilotRuntime):
    import_valid(runtime)
    runtime.approve(workflow_id="human-fixture")
    runtime.request_contract_reverified()


def test_preserved_v071_files_match_accepted_hashes_and_tag_bytes():
    tracked_static = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", BASELINE, "--", "mesh-builder/app/static"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert tracked_static == ["mesh-builder/app/static/style.css"]
    for relative, expected in PRESERVED_HASHES.items():
        payload = (REPOSITORY_ROOT / relative).read_bytes()
        accepted = subprocess.run(
            ["git", "show", f"{BASELINE}:{relative}"], cwd=REPOSITORY_ROOT, check=True, capture_output=True
        ).stdout
        assert payload == accepted
        assert hashlib.sha256(payload).hexdigest() == expected


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_static_import_graph_is_strictly_isolated():
    server_imports = imported_modules(PACKAGE_ROOT / "app/server.py")
    pilot_imports = imported_modules(PACKAGE_ROOT / "app/pilot_server.py")
    assert not any("pilot_server" in name for name in server_imports)
    forbidden = ("pipeline", "vmp", "geometry_v2", "import-probe", "probe")
    assert not any(token in name for name in pilot_imports for token in forbidden)
    assert any("reconstruction_v1" in name for name in pilot_imports)


def test_servers_construct_independently_and_bind_concurrently(tmp_path: Path):
    from app.server import create_app

    production = create_app(PACKAGE_ROOT, tmp_path / "production")
    pilot = create_pilot_app(workspace=tmp_path / "pilot")
    assert any(rule.rule == "/" for rule in production.url_map.iter_rules())
    assert pilot.test_client().get("/").status_code == 200
    assert load_pilot_config()["pilotPort"] == 5180
    production_source = (PACKAGE_ROOT / "app/server.py").read_text(encoding="utf-8")
    assert "'5179'" in production_source and "5180" not in production_source


def test_canonical_transition_graph_every_legal_and_illegal_edge(tmp_path: Path):
    states = set(TRANSITIONS) | {target for targets in TRANSITIONS.values() for target in targets}

    def path_to(target):
        queue = [(None, [])]
        visited = set()
        while queue:
            current, path = queue.pop(0)
            if current == target:
                return path
            if current in visited:
                continue
            visited.add(current)
            for next_state in TRANSITIONS.get(current, set()):
                queue.append((next_state, [*path, next_state]))
        raise AssertionError(f"No canonical path to {target}")

    for source in states | {None}:
        for target in states:
            path = tmp_path / f"{source}-{target}.jsonl"
            log = TaskLog(path)
            if source is not None:
                for index, state in enumerate(path_to(source)):
                    log.append(state, timestamp=str(index))
            if target in TRANSITIONS.get(source, set()):
                log.append(target, timestamp="legal")
            else:
                with pytest.raises(StateError):
                    log.append(target, timestamp="illegal")


@pytest.mark.parametrize("terminal", ["FAILED", "CANCELED", "USER_ACCEPTED", "USER_REJECTED"])
def test_terminal_states_have_no_transitions(terminal):
    assert TRANSITIONS[terminal] == set()


def test_restart_and_tampered_hash_chain(tmp_path: Path):
    path = tmp_path / "TaskLog.jsonl"
    TaskLog(path).append("PREPARED", timestamp="1")
    restarted = TaskLog(path)
    restarted.append("BUNDLE_APPROVED", timestamp="2")
    assert restarted.events()[-1]["state"] == "BUNDLE_APPROVED"
    path.write_text(path.read_text().replace('"PREPARED"', '"SUBMITTED"'), encoding="utf-8")
    with pytest.raises(StateError, match="integrity"):
        restarted.events()


def test_ui_projects_exact_backend_state_set_and_has_no_cancel_action(tmp_path: Path):
    app = create_pilot_app(workspace=tmp_path / "pilot")
    page = app.test_client().get("/").get_data(as_text=True)
    projected = page.split('id="backend-states">', 1)[1].split("</code>", 1)[0].split(",")
    assert set(projected) == {state for state in TRANSITIONS if state is not None}
    assert "/provider/cancel" not in page.lower()
    assert ">cancel<" not in page.lower()
    assert "API key" in page and 'name="api' not in page


@pytest.mark.parametrize(
    "uploads,profile,message",
    [
        ([('top', 'top.png', image_bytes((1, 2, 3)), 'human_authority_candidate')], "enemy_gunship", "order"),
        ([('front', 'a.png', image_bytes((1, 2, 3)), 'human_authority_candidate'), ('top', 'b.png', image_bytes((2, 3, 4)), 'human_authority_candidate'), ('right', 'c.png', image_bytes((3, 4, 5)), 'human_authority_candidate')], "enemy_gunship", "order"),
        ([('top', 'a.png', image_bytes((1, 2, 3)), 'human_authority_candidate'), ('front', 'b.png', image_bytes((2, 3, 4)), 'human_authority_candidate'), ('right', 'c.png', image_bytes((3, 4, 5)), 'human_authority_candidate')], "unsupported", "Unsupported"),
    ],
)
def test_bundle_missing_wrong_order_and_profile_refused(tmp_path: Path, uploads, profile, message):
    with pytest.raises((PilotError, BundleError), match=message):
        runtime_fixture(tmp_path).import_bundle(profile_id=profile, asset_id="x", uploads=uploads)


def test_duplicate_bytes_fixture_and_single_view_authority_refused(tmp_path: Path):
    runtime = runtime_fixture(tmp_path)
    same = image_bytes((10, 20, 30))
    with pytest.raises(BundleError, match="independently"):
        runtime.import_bundle(
            profile_id="enemy_gunship",
            asset_id="x",
            uploads=[
                ("top", "top.png", same, "human_authority_candidate"),
                ("front", "front.png", same, "human_authority_candidate"),
                ("right", "right.png", image_bytes((30, 20, 10)), "human_authority_candidate"),
            ],
        )
    for classification in ("deterministic_fixture", "single_view_source"):
        other = runtime_fixture(tmp_path / classification)
        import_valid(other, provenance=classification)
        with pytest.raises(PilotError, match="cannot become"):
            other.approve(workflow_id="human")


def test_post_approval_swap_refuses_and_only_discard_recovers(tmp_path: Path):
    runtime = runtime_fixture(tmp_path)
    bundle = import_valid(runtime)
    runtime.approve(workflow_id="human")
    (runtime.workspace / bundle["views"][0]["path"]).write_bytes(image_bytes((9, 9, 9)))
    with pytest.raises(BundleError, match="mutated"):
        runtime.load_bundle(require_approved=True)
    with pytest.raises(PilotError, match="discard"):
        import_valid(runtime)
    runtime.discard()
    assert runtime.current_state() is None


def test_contract_snapshot_hash_age_and_stale_refusal(tmp_path: Path):
    stale = runtime_fixture(tmp_path, fresh=False)
    import_valid(stale)
    stale.approve(workflow_id="human")
    snapshot = stale.contract_snapshot()
    assert snapshot.sha256 == hashlib.sha256((stale.repository_root / snapshot.path).read_bytes()).hexdigest()
    assert snapshot.freshness_status == "STALE" and snapshot.age_hours == 48
    with pytest.raises(PilotError, match="STALE"):
        stale.request_contract_reverified()
    with pytest.raises(PilotError, match="STALE"):
        stale.preview_authorization()
    with pytest.raises(PilotError, match="STALE"):
        stale.approve_cost("a" * 64)
    with pytest.raises(PilotError, match="STALE"):
        stale.submit(api_key=None)


def test_fresh_snapshot_permits_only_expected_transition(tmp_path: Path):
    runtime = runtime_fixture(tmp_path, fresh=True)
    approve_and_reverify(runtime)
    assert runtime.current_state() == "CONTRACT_REVERIFIED"
    with pytest.raises(StateError):
        runtime.task_log.append("COST_APPROVED", timestamp="illegal")


def approved_projection(tmp_path: Path):
    runtime = runtime_fixture(tmp_path)
    approve_and_reverify(runtime)
    record = runtime.preview_authorization()
    return runtime, record


def test_authorization_schema_fixed_values_and_determinism(tmp_path: Path):
    runtime, record = approved_projection(tmp_path)
    projection = record["projection"]
    assert projection["schemaVersion"] == AUTHORIZATION_SCHEMA_VERSION
    assert projection["requestBody"] == FIXED_REQUEST
    assert projection["estimatedCredits"] == projection["maximumCredits"] == 20
    assert None not in projection.values()
    assert authorization_digest(projection) == record["authorizationDigest"]
    payload = tmp_path / "projection.json"
    payload.write_text(json.dumps(projection), encoding="utf-8")
    code = "import json,sys; from app.reconstruction_v1.authorization import authorization_digest; print(authorization_digest(json.load(open(sys.argv[1]))))"
    completed = subprocess.run([sys.executable, "-c", code, str(payload)], cwd=PACKAGE_ROOT, text=True, capture_output=True, check=True)
    assert completed.stdout.strip() == record["authorizationDigest"]
    assert runtime.current_state() == "AUTHORIZATION_PREVIEWED"


@pytest.mark.parametrize(
    "path,value",
    [
        (("bundleDigest",), "b" * 64),
        (("profileId",), "enemy_interceptor"),
        (("requestBody", "ai_model"), "other"),
        (("requestBody", "should_texture"), True),
        (("estimatedCredits",), 19),
        (("maximumCredits",), 21),
        (("artifactHostPolicy", "contractVersion"), "other"),
        (("contractSnapshot", "sha256"), "c" * 64),
        (("contractSnapshot", "verificationDate"), "other"),
        (("producerSourceBindingDigest",), "d" * 64),
        (("humanApproval", "approvedAt"), "other"),
        (("humanApproval", "workflowId"), "other"),
    ],
)
def test_every_authorization_field_affects_digest(tmp_path: Path, path, value):
    _, record = approved_projection(tmp_path)
    changed = json.loads(json.dumps(record["projection"]))
    target = changed
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    assert authorization_digest(changed) != record["authorizationDigest"]


def test_authorization_rejects_options_credit_float_and_confirmation_changes(tmp_path: Path):
    runtime = runtime_fixture(tmp_path)
    import_valid(runtime)
    bundle = runtime.approve(workflow_id="human")
    snapshot = runtime.contract_snapshot()
    for request_body in ({**FIXED_REQUEST, "should_texture": True}, {**FIXED_REQUEST, "target_formats": ["obj"]}):
        with pytest.raises(AuthorizationError, match="options"):
            build_authorization_projection(runtime.package_root, runtime.workspace, bundle, contract_snapshot=snapshot, artifact_host_policy=runtime.provider.artifact_host_policy, request_body=request_body)
    for cap in (19, 21, 20.0):
        with pytest.raises(AuthorizationError, match="credit"):
            build_authorization_projection(runtime.package_root, runtime.workspace, bundle, contract_snapshot=snapshot, artifact_host_policy=runtime.provider.artifact_host_policy, maximum_credits=cap)
    runtime.request_contract_reverified()
    record = runtime.preview_authorization()
    with pytest.raises(PilotError, match="does not match"):
        runtime.approve_cost("0" * 64)
    runtime.approve_cost(record["authorizationDigest"])
    bundle["approval"]["workflowId"] = "changed"
    runtime.bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises((PilotError, BundleError, AuthorizationError)):
        runtime.submit(api_key="fixture-key")


def test_provider_submit_recomputes_extended_digest_before_transport(tmp_path: Path):
    runtime, record = approved_projection(tmp_path)
    bundle = runtime.load_bundle(require_approved=True)
    transport = NoTransport()
    provider = MeshyMultiImageProvider(
        transport,
        environ={},
        submission_registry=tmp_path / "registry",
        artifact_host_policy=runtime.provider.artifact_host_policy,
        require_authorization_digest=True,
    )
    authorization = SubmissionAuthorization(
        True,
        bundle["bundleDigest"],
        bundle["bundleDigest"],
        20,
        "fixture-secret",
        authorization_projection=record["projection"],
        confirmed_authorization_digest="0" * 64,
    )
    with pytest.raises((AuthorizationError, ProviderError)):
        provider.submit_task(runtime.workspace, bundle, authorization)
    assert transport.calls == []


@pytest.mark.parametrize("guard", ["CI", "GITHUB_ACTIONS", "SKYFORGE_PROVIDER_NETWORK_DISABLED"])
@pytest.mark.parametrize("operation", ["submit_task", "get_task", "poll_until_terminal", "download_artifact", "download_artifacts"])
def test_all_provider_operations_blocked_before_transport(tmp_path: Path, guard, operation):
    transport = NoTransport()
    provider = MeshyMultiImageProvider(transport, environ={guard: "1"})
    with pytest.raises(AuthorizationError):
        if operation == "submit_task":
            provider.submit_task(tmp_path, {}, SubmissionAuthorization(False, "", "", 20, None))
        elif operation == "get_task":
            provider.get_task("task")
        elif operation == "poll_until_terminal":
            provider.poll_until_terminal("task", maximum_polls=1)
        elif operation == "download_artifact":
            provider.download_artifact("https://assets.meshy.ai/a.glb")
        else:
            provider.download_artifacts({"modelUrls": {"glb": "https://assets.meshy.ai/a.glb"}})
    assert transport.calls == []


def test_render_has_no_transport_secret_data_uri_or_signed_query(tmp_path: Path):
    transport = NoTransport()
    provider = MeshyMultiImageProvider(transport, environ={}, require_authorization_digest=True)
    app = create_pilot_app(workspace=tmp_path / "pilot", provider=provider, api_key_loader=lambda: "MUST_NOT_LOAD")
    page = app.test_client().get("/").get_data(as_text=True)
    assert transport.calls == []
    assert "MUST_NOT_LOAD" not in page
    assert "Authorization:" not in page and "data:image" not in page and "signature=" not in page


def test_head_only_preflight_unknown_redirect_and_stub_labels(tmp_path: Path):
    policy = ArtifactHostPolicy("fixture.v1", frozenset({"assets.meshy.ai"}), lambda _host: ("8.8.8.8",))
    transport = Transport([Response(302, headers={"Location": "https://unknown.example/a?signature=secret"})])
    report = preflight_artifact_url("https://assets.meshy.ai/a?token=secret", policy=policy, transport=transport)
    assert report["finalDecision"] == "REFUSE"
    assert [call[0] for call in transport.calls] == ["HEAD"]
    assert "secret" not in json.dumps(report)
    runtime = runtime_fixture(tmp_path)
    labeled = runtime.preflight("https://assets.meshy.ai/a", transport=Transport([Response(200)]))
    assert "dnsResults" not in labeled
    assert labeled["stubDnsResults"] == ["8.8.8.8"]
    assert labeled["resolutionSource"] == "offline_stub_not_observed"


def test_poll_requires_task_id_handles_canceled_and_immediate_capture(tmp_path: Path):
    canceled = runtime_fixture(tmp_path / "cancel")
    canceled.task_log.append("PREPARED", timestamp="1")
    with pytest.raises(PilotError, match="providerTaskId"):
        canceled.poll_and_capture()

    class FakeProvider:
        artifact_host_policy = ArtifactHostPolicy("fixture.v1", frozenset(), lambda _host: ())

        def get_task(self, _task):
            return {"status": "SUCCEEDED", "expires_at": "2026-08-12T00:00:00Z", "model_urls": {"glb": "fixture"}}

        def normalize_response(self, response):
            return {"status": "SUCCEEDED", "expiresAt": response["expires_at"], "modelUrls": response["model_urls"]}

        def download_artifacts(self, _normalized):
            return {"glb": b"glTF" + b"\0" * 20}

    runtime = runtime_fixture(tmp_path / "success", provider=FakeProvider())
    for state in ("PREPARED", "BUNDLE_APPROVED", "CONTRACT_REVERIFIED", "AUTHORIZATION_PREVIEWED", "COST_APPROVED", "SUBMITTING"):
        runtime.task_log.append(state, timestamp=state)
    runtime.task_log.append("SUBMITTED", timestamp="submitted", details={"providerTaskId": "task-1"})
    result = runtime.poll_and_capture()
    assert runtime.current_state() == "DOWNLOADED"
    assert result["expiresAt"] == "2026-08-12T00:00:00Z"
    assert result["rawGlbSha256"]


def test_polling_bounds_and_launcher_contract(tmp_path: Path):
    config = load_pilot_config()
    assert config["pilotPort"] == 5180
    assert config["pollingIntervalSeconds"] == 10 and config["maximumPollCount"] == 30
    launcher = (PACKAGE_ROOT / "scripts/run_pilot_ui.command").read_text(encoding="utf-8")
    assert "PORT=5180" in launcher and "SKYFORGE_PROVIDER_NETWORK_DISABLED=1" in launcher
    assert "app.pilot_server" in launcher and "app.server" not in launcher
    assert "API" in launcher and "key" in launcher
    zsh = shutil.which("zsh")
    if zsh is not None:
        subprocess.run([zsh, "-n", str(PACKAGE_ROOT / "scripts/run_pilot_ui.command")], check=True)


def test_polling_exhaustion_records_failed_terminal_state(tmp_path: Path):
    class PendingProvider:
        artifact_host_policy = ArtifactHostPolicy("fixture.v1", frozenset(), lambda _host: ())

        def get_task(self, _task):
            return {"status": "IN_PROGRESS"}

        def normalize_response(self, _response):
            return {"status": "IN_PROGRESS"}

    runtime = runtime_fixture(tmp_path, provider=PendingProvider())
    runtime.config = {**runtime.config, "maximumPollCount": 2, "pollingIntervalSeconds": 1}
    for state in (
        "PREPARED",
        "BUNDLE_APPROVED",
        "CONTRACT_REVERIFIED",
        "AUTHORIZATION_PREVIEWED",
        "COST_APPROVED",
        "SUBMITTING",
    ):
        runtime.task_log.append(state, timestamp=state)
    runtime.task_log.append("SUBMITTED", timestamp="submitted", details={"providerTaskId": "task-1"})
    with pytest.raises(PilotError, match="exhausted"):
        runtime.poll_and_capture()
    assert runtime.current_state() == "FAILED"
