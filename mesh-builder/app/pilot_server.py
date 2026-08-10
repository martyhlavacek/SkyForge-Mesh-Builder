from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import requests
from flask import Flask, render_template, request, send_file

from .reconstruction_v1.pilot import PilotError, PilotRuntime
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
    runtime = PilotRuntime(PACKAGE_ROOT, workspace, active_provider, now=now)
    key_loader = api_key_loader or (lambda: None)
    app.extensions["skyforge_pilot_runtime"] = runtime

    def page(*, error: str | None = None, notice: str | None = None, status_code: int = 200):
        return (
            render_template("pilot_index.html", pilot=runtime.status(), error=error, notice=notice),
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

    @app.post("/bundle/import")
    def import_bundle():
        def execute():
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
            runtime.import_bundle(
                profile_id=request.form.get("profileId", ""),
                uploads=uploads,
                asset_id=request.form.get("assetId", "pilot.asset"),
            )

        return action(execute, "Three-view authority bundle imported and bound")

    @app.post("/bundle/approve")
    def approve_bundle():
        return action(
            lambda: runtime.approve(workflow_id=request.form.get("workflowId", "pilot-ui-human-approval")),
            "Exact on-disk authority bundle approved",
        )

    @app.post("/single-view/import")
    def import_single_view():
        def execute():
            upload = request.files.get("beauty")
            if upload is None or not upload.filename:
                raise PilotError("Missing Track S three-quarter beauty reference")
            runtime.import_single_view(
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
        return action(runtime.discard, "Pilot workspace discarded; a new workflow may begin")

    @app.get("/bundle/view/<role>")
    def bundle_view(role: str):
        bundle = runtime.load_bundle(require_approved=False)
        item = next((entry for entry in bundle["views"] if entry["role"] == role), None)
        if item is None:
            raise PilotError("Unknown authority role")
        return send_file(runtime.workspace / item["path"], conditional=True)

    @app.get("/single-view/source")
    def single_view_source():
        document = runtime.load_reconstruction_input(require_approved=False)
        if document.get("inputKind") != "single_view_v1":
            raise PilotError("No Track S single-view input is loaded")
        return send_file(runtime.workspace / document["source"]["path"], conditional=True)

    @app.post("/contract/reverified")
    def contract_reverified():
        return action(runtime.request_contract_reverified, "Fresh committed contract snapshot accepted")

    @app.post("/authorization/preview")
    def authorization_preview():
        return action(runtime.preview_authorization, "Authorization digest previewed")

    @app.post("/authorization/approve")
    def authorization_approve():
        return action(
            lambda: runtime.approve_cost(request.form.get("authorizationDigest", "")),
            "Exact 20-credit authorization digest approved",
        )

    @app.post("/artifact/preflight")
    def artifact_preflight():
        report = runtime.preflight(request.form.get("artifactUrl", ""))
        return page(notice=f"Artifact preflight decision: {report['finalDecision']}")

    @app.post("/provider/submit")
    def provider_submit():
        def execute():
            if not runtime.status()["sendable"]:
                raise PilotError("Pilot is not sendable; API-key loading is refused")
            return runtime.submit(api_key=key_loader())

        return action(execute, "Provider task submitted exactly once")

    @app.post("/provider/poll-and-capture")
    def provider_poll_and_capture():
        return action(runtime.poll_and_capture, "Provider terminal result captured immediately")

    return app


def main() -> None:
    app = create_pilot_app()
    runtime: PilotRuntime = app.extensions["skyforge_pilot_runtime"]
    port = runtime.config["pilotPort"]
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    os.environ.setdefault("SKYFORGE_PROVIDER_NETWORK_DISABLED", "1")
    main()
