from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, session

from .external_glb_vmp_export import export_manual_glb_vmp
from .manual_glb_import import (
    QA_FILES,
    ManualGlbImportError,
    approve_manual_import,
    create_manual_import,
    load_manual_job,
    normalize_manual_import,
    reinspect_manual_import,
    set_orientation_mapping,
)
from .pipeline import resolve_blender_path
from .vmp_job_export import JobVmpExportError, resolve_import_probe_command

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def create_manual_glb_app(package_root: Path | None = None, workspace: Path | None = None) -> Flask:
    root = (package_root or PACKAGE_ROOT).resolve()
    workspace_root = (workspace or root / "workspace").resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    app = Flask(__name__)
    app.secret_key = os.environ.get("SKYFORGE_SESSION_SECRET") or secrets.token_hex(32)
    app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024

    def csrf() -> str:
        return session.setdefault("manual_glb_csrf", secrets.token_urlsafe(32))

    def require_csrf() -> None:
        if not secrets.compare_digest(request.headers.get("X-SkyForge-CSRF", ""), session.get("manual_glb_csrf", "")):
            raise PermissionError("invalid or missing CSRF token")

    def job_root(job_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}", job_id):
            raise ManualGlbImportError("invalid job ID")
        base = (workspace_root / "_manual_glb").resolve()
        target = (base / job_id).resolve()
        target.relative_to(base)
        return target

    @app.get("/")
    def index():
        return render_template("manual_glb.html", csrf_token=csrf(), blender_available=resolve_blender_path(root) is not None)

    @app.post("/api/import")
    def import_glb():
        try:
            require_csrf()
            upload = request.files.get("glb")
            if upload is None or not upload.filename:
                raise ManualGlbImportError("a .glb upload is required")
            result = create_manual_import(
                workspace_root, filename=upload.filename, stream=upload.stream,
                asset_id=request.form.get("assetId", ""), asset_version=request.form.get("assetVersion", ""),
                asset_role=request.form.get("assetRole", "air_moving"), source_notes=request.form.get("sourceNotes", ""),
                orientation_mapping=request.form.get("orientationMapping", ""),
            )
            return jsonify(ok=True, jobId=result.name, job=load_manual_job(result))
        except (ManualGlbImportError, PermissionError) as exc:
            return jsonify(ok=False, error=str(exc)), 400

    @app.post("/api/jobs/<job_id>/normalize")
    def normalize(job_id: str):
        try:
            require_csrf()
            body = request.get_json(silent=True) or {}
            if body.get("orientationMapping"):
                set_orientation_mapping(job_root(job_id), str(body["orientationMapping"]))
            blender = resolve_blender_path(root)
            if blender is None:
                raise ManualGlbImportError("Blender is not configured")
            return jsonify(ok=True, job=normalize_manual_import(job_root(job_id), blender, root / "blender/normalize_external_glb.py"))
        except (ManualGlbImportError, PermissionError, ValueError) as exc:
            return jsonify(ok=False, error=str(exc)), 400

    @app.post("/api/jobs/<job_id>/inspect")
    def inspect(job_id: str):
        try:
            require_csrf()
            return jsonify(ok=True, inspection=reinspect_manual_import(job_root(job_id)))
        except (ManualGlbImportError, PermissionError, ValueError) as exc:
            return jsonify(ok=False, error=str(exc)), 400

    @app.post("/api/jobs/<job_id>/decision")
    def decision(job_id: str):
        try:
            require_csrf()
            value = (request.get_json(silent=True) or {}).get("decision")
            if value not in {"approve", "reject"}:
                raise ManualGlbImportError("decision must be approve or reject")
            return jsonify(ok=True, job=approve_manual_import(job_root(job_id), value == "approve"))
        except (ManualGlbImportError, PermissionError, ValueError) as exc:
            return jsonify(ok=False, error=str(exc)), 400

    @app.get("/api/jobs/<job_id>/qa/<filename>")
    def qa(job_id: str, filename: str):
        if filename not in QA_FILES:
            return jsonify(ok=False, error="unknown QA output"), 404
        return send_file(job_root(job_id) / "output/qa" / filename, mimetype="image/png", conditional=True)

    @app.post("/api/jobs/<job_id>/vmp")
    def export(job_id: str):
        try:
            require_csrf()
            probe = resolve_import_probe_command(root)
            if probe is None:
                raise ManualGlbImportError("independent Sprite Foundry Import Probe is not configured")
            v2_script = Path(probe[1]).parents[1].parent / "import-probe-v2/run_import_probe_v2.py"
            if not v2_script.is_file():
                raise ManualGlbImportError("independent VMP v2 Import Probe is not configured")
            probe = (probe[0], str(v2_script))
            body = request.get_json(silent=True) or {}
            result = export_manual_glb_vmp(
                root, job_root(job_id), workspace_root / "_vmp" / f"{job_id}.sfmeshpack",
                import_probe_command=probe, commercial_use_asserted=body.get("commercialUseAsserted") is True,
                terms_basis=str(body.get("termsBasis") or ""),
            )
            return jsonify(ok=True, packageContentDigest=result.build.package_content_digest, archiveSha256=result.build.archive_sha256)
        except (ManualGlbImportError, JobVmpExportError, PermissionError, ValueError) as exc:
            return jsonify(ok=False, error=str(exc)), 400

    return app


if __name__ == "__main__":
    create_manual_glb_app().run(host="127.0.0.1", port=8043, threaded=True)
