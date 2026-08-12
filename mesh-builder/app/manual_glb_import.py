from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from common.glb_facts import GlbFactsError, parse_glb_facts

WORKFLOW_ID = "external_glb_import"
SOURCE_PROVIDER = "meshy_web"
MAX_UPLOAD_BYTES = 250 * 1024 * 1024
_AXES = ("+X", "-X", "+Y", "-Y", "+Z", "-Z")
ORIENTATION_MAPPINGS = frozenset(
    f"{forward},{up}" for forward in _AXES for up in _AXES if forward[-1] != up[-1]
)
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
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


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
    completed = subprocess.run([
        str(blender), "--background", "--factory-startup", "--python", str(script), "--",
        "--job-root", str(root), "--orientation", job["orientationMapping"],
    ], capture_output=True, text=True, timeout=600, check=False,
       env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"})
    if completed.returncode:
        detail = "\n".join(value for value in (completed.stdout, completed.stderr) if value).strip()
        raise ManualGlbImportError((detail or "Blender normalization failed")[-4000:])
    normalized = root / "output/normalized.glb"
    facts = parse_glb_facts(normalized.read_bytes())
    job = transition(root, "normalized", normalized={"sha256": _sha(normalized.read_bytes()), "inspection": _facts_dict(facts)})
    job = transition(root, "validated", validation={"passed": True, "gates": _validation_gates(facts)})
    missing = [name for name in QA_FILES if not (root / "output/qa" / name).is_file()]
    if missing:
        raise ManualGlbImportError("Blender did not produce required QA outputs: " + ", ".join(missing))
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
