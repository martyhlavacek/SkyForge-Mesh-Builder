from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from PIL import Image, UnidentifiedImageError

from common.glb_facts import GlbFactsError, parse_glb_facts

WORKFLOW_ID = "external_glb_import"
SOURCE_PROVIDER = "meshy_web"
MAX_UPLOAD_BYTES = 250 * 1024 * 1024
_AXES = ("+X", "-X", "+Y", "-Y", "+Z", "-Z")
ORIENTATION_MAPPING_OPTIONS = tuple(
    f"{forward},{up}" for forward in _AXES for up in _AXES if forward[-1] != up[-1]
)
ORIENTATION_MAPPINGS = frozenset(ORIENTATION_MAPPING_OPTIONS)
TRANSITIONS = {
    "imported": {"inspected", "rejected"},
    "inspected": {"normalized", "rejected"},
    "normalized": {"validated", "rejected"},
    "validated": {"qa_ready", "rejected"},
    "qa_ready": {"approved", "rejected"},
    "approved": {"rejected"},
    "rejected": set(),
}
QA_FILES = (
    "gameplay_neutral.png", "bank_left.png", "bank_right.png", "top_ortho.png",
    "front.png", "side.png", "gameplay_scale_96.png",
)
QA_DIMENSIONS = {name: (96, 96) if name == "gameplay_scale_96.png" else (384, 384) for name in QA_FILES}


class ManualGlbImportError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_token(value: str, label: str) -> str:
    value = value.strip()
    if not value or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise ManualGlbImportError(f"{label} contains unsupported characters")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _attempt_diagnostics(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = root / "diagnostics/blender" / f"attempt-{stamp}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value


def _persist_execution(
    directory: Path, *, blender: Path, command: list[str], returncode: int | None,
    stdout: str | bytes | None, stderr: str | bytes | None, timed_out: bool = False,
) -> dict[str, Any]:
    stdout_text, stderr_text = _text(stdout), _text(stderr)
    (directory / "stdout.txt").write_text(stdout_text, encoding="utf-8")
    (directory / "stderr.txt").write_text(stderr_text, encoding="utf-8")
    signal_number = -returncode if returncode is not None and returncode < 0 else None
    try:
        signal_name = signal.Signals(signal_number).name if signal_number else None
    except ValueError:
        signal_name = None
    summary = {
        "schemaVersion": "skyforge.blender-subprocess-diagnostics.v1",
        "blenderExecutable": str(blender.resolve()),
        "command": command,
        "returnCode": returncode,
        "timedOut": timed_out,
        "terminatedBySignal": signal_number is not None,
        "signalNumber": signal_number,
        "signalName": signal_name,
        "stdoutFile": "stdout.txt",
        "stderrFile": "stderr.txt",
    }
    _write_json(directory / "execution.json", summary)
    return summary


def _validate_texture_preservation(source: dict[str, Any], normalized: Any) -> None:
    source_channels = {name for item in source.get("material_texture_channels", []) for name in item}
    normalized_channels = {name for item in normalized.material_texture_channels for name in item}
    missing_channels = sorted(source_channels - normalized_channels)
    if missing_channels:
        raise ManualGlbImportError("normalization removed material texture channels: " + ", ".join(missing_channels))
    for key in ("material_count", "texture_count", "image_count"):
        if int(source.get(key, 0)) > 0 and int(getattr(normalized, key)) <= 0:
            raise ManualGlbImportError(f"normalization removed required {key.replace('_', ' ')}")
    for key, label in (("uv_primitive_count", "UVs"), ("normal_primitive_count", "normals"),
                       ("tangent_primitive_count", "tangents")):
        if int(source.get(key, 0)) > 0 and int(getattr(normalized, key)) <= 0:
            raise ManualGlbImportError(f"normalization removed required {label}")


def _validate_qa_outputs(root: Path) -> None:
    for name, dimensions in QA_DIMENSIONS.items():
        path = root / "output/qa" / name
        if not path.is_file():
            raise ManualGlbImportError(f"Blender did not produce required QA output: {name}")
        if path.stat().st_size <= 0:
            raise ManualGlbImportError(f"QA output is empty: {name}")
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                actual = image.size
        except (OSError, UnidentifiedImageError) as exc:
            raise ManualGlbImportError(f"QA output is not a decodable PNG: {name}") from exc
        if actual != dimensions:
            raise ManualGlbImportError(
                f"QA output has wrong dimensions: {name} is {actual[0]}x{actual[1]}, expected {dimensions[0]}x{dimensions[1]}"
            )


def create_manual_import(
    workspace: Path, *, filename: str, stream: BinaryIO, asset_id: str, asset_version: str,
    asset_role: str = "air_moving", source_notes: str = "", orientation_mapping: str = "",
) -> Path:
    if Path(filename).suffix.lower() != ".glb":
        raise ManualGlbImportError("Manual textured import accepts .glb files only")
    asset_id = _safe_token(asset_id, "asset ID")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", asset_version.strip()):
        raise ManualGlbImportError("asset version must be numeric semantic version")
    if asset_role != "air_moving":
        raise ManualGlbImportError("only the frozen air_moving role is supported")
    if orientation_mapping and orientation_mapping not in ORIENTATION_MAPPINGS:
        raise ManualGlbImportError("source forward/up orientation mapping is invalid")
    payload = stream.read(MAX_UPLOAD_BYTES + 1)
    if not payload:
        raise ManualGlbImportError("uploaded GLB is empty")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ManualGlbImportError("uploaded GLB exceeds the 250 MiB limit")
    try:
        facts = parse_glb_facts(payload)
    except GlbFactsError as exc:
        raise ManualGlbImportError(str(exc)) from exc
    digest = _sha(payload)
    job_id = f"manual-{asset_id}-{digest[:12]}"
    root = workspace.resolve() / "_manual_glb" / _safe_token(job_id, "job ID")
    if root.exists():
        raise ManualGlbImportError("this exact source GLB is already imported for the asset")
    source = root / "source_quarantine"
    output = root / "output"
    qa = output / "qa"
    source.mkdir(parents=True)
    qa.mkdir(parents=True)
    original = source / "original.glb"
    original.write_bytes(payload)
    original.chmod(0o444)
    record = {
        "schemaVersion": "skyforge.manual-glb-import.v1",
        "workflowId": WORKFLOW_ID,
        "state": "inspected",
        "assetId": asset_id,
        "assetVersion": asset_version.strip(),
        "assetRole": asset_role,
        "source": {
            "type": "externally_authored", "provider": SOURCE_PROVIDER,
            "ingestionMethod": "manual_file_import", "originalFilename": Path(filename).name,
            "byteSize": len(payload), "sha256": digest, "importedAt": _now(),
            "notes": source_notes[:4000], "meshyTaskId": None,
        },
        "orientationMapping": orientation_mapping or None,
        "inspection": _inspection_report(facts, digest, len(payload)),
        "approval": None,
        "history": [
            {"state": "imported", "recordedAt": _now()},
            {"state": "inspected", "recordedAt": _now()},
        ],
    }
    _write_json(root / "job.json", record)
    inspection = root / "inspection"
    inspection.mkdir()
    _write_json(inspection / "glb_inspection.json", record["inspection"])
    return root


def load_manual_job(root: Path) -> dict[str, Any]:
    value = json.loads((root / "job.json").read_text(encoding="utf-8"))
    if value.get("workflowId") != WORKFLOW_ID:
        raise ManualGlbImportError("job is not a manual external GLB import")
    return value


def transition(root: Path, target: str, **updates: Any) -> dict[str, Any]:
    job = load_manual_job(root)
    current = str(job.get("state"))
    if target not in TRANSITIONS.get(current, set()):
        raise ManualGlbImportError(f"invalid manual import transition: {current} -> {target}")
    job.update(updates)
    job["state"] = target
    job.setdefault("history", []).append({"state": target, "recordedAt": _now()})
    _write_json(root / "job.json", job)
    return job


def verify_source_artifact(root: Path, job: dict[str, Any] | None = None) -> Path:
    job = job or load_manual_job(root)
    source = root / "source_quarantine/original.glb"
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise ManualGlbImportError("imported source artifact is missing after ingestion") from exc
    expected = job.get("source", {})
    if len(payload) != expected.get("byteSize") or _sha(payload) != expected.get("sha256"):
        raise ManualGlbImportError("imported source artifact changed after ingestion")
    return source


def reinspect_manual_import(root: Path) -> dict[str, Any]:
    job = load_manual_job(root)
    source = verify_source_artifact(root, job)
    facts = parse_glb_facts(source.read_bytes())
    report = _inspection_report(facts, job["source"]["sha256"], job["source"]["byteSize"])
    _write_json(root / "inspection/glb_inspection.json", report)
    job["inspection"] = report
    _write_json(root / "job.json", job)
    return report


def set_orientation_mapping(root: Path, mapping: str) -> dict[str, Any]:
    if mapping not in ORIENTATION_MAPPINGS:
        raise ManualGlbImportError("explicit source forward/up orientation is required before normalization")
    job = load_manual_job(root)
    if job["state"] != "inspected":
        raise ManualGlbImportError("orientation may only be set before normalization")
    verify_source_artifact(root, job)
    job["orientationMapping"] = mapping
    _write_json(root / "job.json", job)
    return job


def normalize_manual_import(root: Path, blender: Path, script: Path) -> dict[str, Any]:
    job = load_manual_job(root)
    if job["state"] != "inspected":
        raise ManualGlbImportError("only inspected jobs may be normalized")
    verify_source_artifact(root, job)
    if job.get("orientationMapping") not in ORIENTATION_MAPPINGS:
        raise ManualGlbImportError("explicit source forward/up orientation is required before normalization")
    diagnostics = _attempt_diagnostics(root)
    normalized_path = root / "output/normalized.glb"
    normalized_path.unlink(missing_ok=True)
    for name in QA_FILES:
        (root / "output/qa" / name).unlink(missing_ok=True)
    command = [
        str(blender), "--background", "--factory-startup", "--python", str(script), "--",
        "--job-root", str(root), "--orientation", job["orientationMapping"],
        "--diagnostics", str(diagnostics),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=600, check=False,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
        )
    except subprocess.TimeoutExpired as exc:
        _persist_execution(
            diagnostics, blender=blender, command=command, returncode=None,
            stdout=exc.stdout, stderr=exc.stderr, timed_out=True,
        )
        raise ManualGlbImportError("Blender normalization timed out after 600 seconds") from exc
    execution = _persist_execution(
        diagnostics, blender=blender, command=command, returncode=completed.returncode,
        stdout=completed.stdout, stderr=completed.stderr,
    )
    if completed.returncode:
        detail = "\n".join(value for value in (completed.stdout, completed.stderr) if value).strip()
        if execution["terminatedBySignal"]:
            identity = f"signal {execution['signalNumber']}"
            if execution["signalName"]:
                identity += f" ({execution['signalName']})"
            prefix = f"Blender terminated by {identity}"
        else:
            prefix = f"Blender normalization exited with code {completed.returncode}"
        raise ManualGlbImportError((prefix + (f": {detail}" if detail else ""))[-4000:])
    script_diagnostics_path = diagnostics / "blender_script.json"
    if not script_diagnostics_path.is_file():
        raise ManualGlbImportError("Blender exited successfully without producing script diagnostics")
    try:
        script_diagnostics = json.loads(script_diagnostics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManualGlbImportError("Blender script diagnostics are missing or malformed") from exc
    if script_diagnostics.get("error"):
        error_lines = [line.strip() for line in str(script_diagnostics["error"]).splitlines() if line.strip()]
        raise ManualGlbImportError("Blender normalization script failed: " + (error_lines[-1] if error_lines else "unknown error"))
    stages = [item.get("stage") for item in script_diagnostics.get("stageMarkers", []) if isinstance(item, dict)]
    if not stages or stages[-1] != "script_completed":
        raise ManualGlbImportError("Blender exited without completing the normalization script")
    if not normalized_path.is_file():
        raise ManualGlbImportError("Blender exited successfully without producing normalized.glb")
    normalized_payload = normalized_path.read_bytes()
    facts = parse_glb_facts(normalized_payload)
    _validate_texture_preservation(job["inspection"]["facts"], facts)
    _validate_qa_outputs(root)
    job = transition(root, "normalized", normalized={"sha256": _sha(normalized_payload), "inspection": _facts_dict(facts)})
    job = transition(root, "validated", validation={"passed": True, "gates": _validation_gates(facts)})
    return transition(root, "qa_ready", qaOutputs=list(QA_FILES))


def approve_manual_import(root: Path, approved: bool) -> dict[str, Any]:
    if not approved:
        return transition(root, "rejected")
    job = load_manual_job(root)
    verify_source_artifact(root, job)
    if job["state"] != "qa_ready":
        raise ManualGlbImportError("only QA-ready jobs may be approved")
    normalized = root / "output/normalized.glb"
    digest = _sha(normalized.read_bytes())
    if digest != job.get("normalized", {}).get("sha256"):
        raise ManualGlbImportError("normalized GLB changed; normalization and QA must be repeated")
    approval = {
        "state": "approved", "assetId": job["assetId"], "assetVersion": job["assetVersion"],
        "provider": SOURCE_PROVIDER, "originalGlbSha256": job["source"]["sha256"],
        "normalizedGlbSha256": digest, "approvedAt": _now(), "qaOutputs": job["qaOutputs"],
    }
    return transition(root, "approved", approval=approval)


def require_current_approval(root: Path) -> dict[str, Any]:
    job = load_manual_job(root)
    verify_source_artifact(root, job)
    if job["state"] != "approved" or not isinstance(job.get("approval"), dict):
        raise ManualGlbImportError("manual import requires explicit approval before export")
    current = _sha((root / "output/normalized.glb").read_bytes())
    if current != job["approval"].get("normalizedGlbSha256"):
        job["approval"] = None
        job["state"] = "qa_ready"
        job.setdefault("history", []).append({"state": "approval_invalidated", "recordedAt": _now()})
        _write_json(root / "job.json", job)
        raise ManualGlbImportError("normalized GLB changed and invalidated approval")
    return job


def _facts_dict(facts: Any) -> dict[str, Any]:
    value = asdict(facts)
    value["bounds"] = {"min": value.pop("bounds_min"), "max": value.pop("bounds_max")}
    return value


def _inspection_report(facts: Any, source_sha256: str, byte_size: int) -> dict[str, Any]:
    values = _facts_dict(facts)
    warnings = []
    if facts.tangent_primitive_count < facts.primitive_count:
        warnings.append("one or more primitives have no tangent attribute")
    if facts.normal_primitive_count < facts.primitive_count:
        warnings.append("one or more primitives have no normal attribute")
    if not facts.material_count:
        warnings.append("GLB has no materials")
    if not facts.texture_count:
        warnings.append("GLB has no textures")
    warnings.extend(f"extension requires compatibility review: {item}" for item in facts.suspicious_extensions)
    return {
        "schemaVersion": "skyforge.glb-inspection.v1",
        "sourceGlbSha256": source_sha256,
        "sourceByteSize": byte_size,
        "classification": "accepted_with_warnings" if warnings else "accepted",
        "facts": values,
        "warnings": warnings,
        "hardRejections": [],
    }


def _validation_gates(facts: Any) -> list[dict[str, Any]]:
    return [
        {"name": "selfContainedGlb2", "status": "passed"},
        {"name": "trianglePrimitives", "status": "passed"},
        {"name": "independentInspection", "status": "passed"},
        {"name": "authoritySilhouetteIoU", "status": "not_applicable", "reason": "no reconstruction authority supplied"},
        {"name": "attachmentPoints", "status": "not_applicable", "reason": "not authored or approved"},
    ]
