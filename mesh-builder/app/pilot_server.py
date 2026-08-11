from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import requests
from flask import Flask, render_template, request, send_file

from .reconstruction_v1.pilot import PilotError, PilotRuntime, PilotSessionManager
from .reconstruction_v1.provider import MeshyMultiImageProvider
from .reconstruction_v1.state import StateError

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = PACKAGE_ROOT / "workspace" / "pilot_ui"


def create_pilot_app(
    *,
    workspace: Path = DEFAULT_WORKSPACE,
    provider: MeshyMultiImageProvider | None = None,
    now: Callable[[], datetime] | None = None,
    api_key_loader: Callable[[], str | None] | None = None,
    enable_session_isolation: bool | None = None,
) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).with_name("templates")),
        static_folder=str(Path(__file__).with_name("static") / "pilot"),
        static_url_path="/pilot-static",
    )
    app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024
    active_provider = provider or MeshyMultiImageProvider(
        requests.Session(),
        submission_registry=workspace / "submission_registry",
        require_authorization_digest=True,
    )
    session_isolation = workspace.resolve() == DEFAULT_WORKSPACE.resolve() if enable_session_isolation is None else enable_session_isolation
    session_manager = (
        PilotSessionManager(
            PACKAGE_ROOT,
            workspace,
            workspace.parent / "pilot_ui_sessions",
            active_provider,
            now=now,
        )
        if session_isolation
        else None
    )
    runtime = session_manager.historical_runtime if session_manager else PilotRuntime(
        PACKAGE_ROOT, workspace, active_provider, now=now
    )
    key_loader = api_key_loader or (lambda: None)
    app.extensions["skyforge_pilot_runtime"] = runtime
    app.extensions["skyforge_pilot_session_manager"] = session_manager

    def selected_runtime() -> tuple[PilotRuntime, bool]:
        if session_manager is None:
            return runtime, False
        if request.values.get("view") == "historical":
            return session_manager.historical_runtime, True
        active = session_manager.active_runtime()
        return (active, False) if active is not None else (session_manager.historical_runtime, True)

    def page(*, error: str | None = None, notice: str | None = None, status_code: int = 200):
        selected, historical = selected_runtime()
        status = selected.status()
        if historical:
            status["authorization"] = None
            status["sendable"] = False
        status["session"] = {
            "historical": historical,
            "activeTrackSAvailable": session_manager is not None and session_manager.active_runtime() is not None,
            "sessionId": selected.workspace.name,
            "sessionIsolationEnabled": session_manager is not None,
        }
        return (
            render_template("pilot_index.html", pilot=status, error=error, notice=notice),
            status_code,
        )

    def action(callback: Callable[[], Any], notice: str):
        try:
            callback()
            return page(notice=notice)
        except (PilotError, StateError, ValueError, OSError) as exc:
            return page(error=str(exc), status_code=409)

    @app.get("/")
    def index():
        return page()

    @app.post("/sessions/track-s/start")
    def start_track_s_session():
        if session_manager is None:
            return page(error="Track S session isolation is unavailable", status_code=409)
        return action(session_manager.start_track_s_session, "New isolated Track S single-view session started")

    @app.post("/bundle/import")
    def import_bundle():
        def execute():
            selected, historical = selected_runtime()
            if historical:
                raise PilotError("Historical multiview runs are read-only")
            uploads = []
            for role in ("top", "front", "right"):
                upload = request.files.get(role)
                if upload is None or not upload.filename:
                    raise PilotError(f"Missing required {role} authority view")
                uploads.append(
                    (
                        role,
                        upload.filename,
                        upload.read(),
                        request.form.get(f"{role}_provenance", ""),
                    )
                )
            selected.import_bundle(
                profile_id=request.form.get("profileId", ""),
                uploads=uploads,
                asset_id=request.form.get("assetId", "pilot.asset"),
            )

        return action(execute, "Three-view authority bundle imported and bound")

    @app.post("/bundle/approve")
    def approve_bundle():
        selected, historical = selected_runtime()
        if historical:
            return page(error="Historical multiview runs are read-only", status_code=409)
        return action(
            lambda: selected.approve(workflow_id=request.form.get("workflowId", "pilot-ui-human-approval")),
            "Exact on-disk authority bundle approved",
        )

    @app.post("/single-view/import")
    def import_single_view():
        def execute():
            selected, historical = selected_runtime()
            if historical:
                raise PilotError("Start a new Track S single-view session before importing")
            upload = request.files.get("beauty")
            if upload is None or not upload.filename:
                raise PilotError("Missing Track S three-quarter beauty reference")
            selected.import_single_view(
                profile_id=request.form.get("profileId", ""),
                upload_name=upload.filename,
                payload=upload.read(),
                provenance=request.form.get("provenance", ""),
                provenance_source_type=request.form.get("provenanceSourceType", ""),
                asset_id=request.form.get("assetId", "pilot.track-s.asset"),
            )

        return action(execute, "Single-view Track S reconstruction input imported and bound")

    @app.post("/bundle/discard")
    def discard_bundle():
        selected, historical = selected_runtime()
        if historical:
            return page(error="Historical multiview evidence cannot be discarded", status_code=409)
        callback = session_manager.discard_active_session if session_manager is not None else selected.discard
        return action(callback, "Active experimental workspace discarded")

    @app.get("/bundle/view/<role>")
    def bundle_view(role: str):
        selected, historical = selected_runtime()
        if historical and session_manager is not None:
            return send_file(session_manager.historical_view_path(role), conditional=True)
        bundle = selected.load_bundle(require_approved=False)
        item = next((entry for entry in bundle["views"] if entry["role"] == role), None)
        if item is None:
            raise PilotError("Unknown authority role")
        return send_file(selected.workspace / item["path"], conditional=True)

    @app.get("/single-view/source")
    def single_view_source():
        selected, historical = selected_runtime()
        if historical:
            raise PilotError("Historical run has no active Track S single-view input")
        document = selected.load_reconstruction_input(require_approved=False)
        if document.get("inputKind") != "single_view_v1":
            raise PilotError("No Track S single-view input is loaded")
        return send_file(selected.workspace / document["source"]["path"], conditional=True)

    @app.post("/contract/reverified")
    def contract_reverified():
        selected, historical = selected_runtime()
        if historical:
            return page(error="Historical multiview runs are read-only", status_code=409)
        return action(selected.request_contract_reverified, "Fresh committed contract snapshot accepted")

    @app.post("/authorization/preview")
    def authorization_preview():
        selected, historical = selected_runtime()
        if historical:
            return page(error="Historical multiview runs are read-only", status_code=409)
        return action(selected.preview_authorization, "Authorization digest previewed")

    @app.post("/authorization/approve")
    def authorization_approve():
        selected, historical = selected_runtime()
        if historical:
            return page(error="Historical multiview runs are read-only", status_code=409)
        return action(
            lambda: selected.approve_cost(request.form.get("authorizationDigest", "")),
            "Exact 20-credit authorization digest approved",
        )

    @app.post("/artifact/preflight")
    def artifact_preflight():
        selected, _historical = selected_runtime()
        report = selected.preflight(request.form.get("artifactUrl", ""))
        return page(notice=f"Artifact preflight decision: {report['finalDecision']}")

    @app.post("/provider/submit")
    def provider_submit():
        def execute():
            selected, historical = selected_runtime()
            if historical or not selected.status()["sendable"]:
                raise PilotError("Pilot is not sendable; API-key loading is refused")
            return selected.submit(api_key=key_loader())

        return action(execute, "Provider task submitted exactly once")

    @app.post("/provider/poll-and-capture")
    def provider_poll_and_capture():
        selected, historical = selected_runtime()
        if historical:
            return page(error="Historical multiview runs are read-only", status_code=409)
        return action(selected.poll_and_capture, "Provider terminal result captured immediately")

    return app


def main() -> None:
    app = create_pilot_app()
    runtime: PilotRuntime = app.extensions["skyforge_pilot_runtime"]
    port = runtime.config["pilotPort"]
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    os.environ.setdefault("SKYFORGE_PROVIDER_NETWORK_DISABLED", "1")
    main()
