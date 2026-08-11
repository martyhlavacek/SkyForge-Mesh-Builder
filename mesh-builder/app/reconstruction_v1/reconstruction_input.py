from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image

from common.canonical_json import canonicalize

from .bundle import SCHEMA_VERSION as MULTIVIEW_SCHEMA_VERSION
from .bundle import SUPPORTED_PROFILES, validate_bundle
from .quarantine import assert_reconstruction_hashes_eligible

MULTIVIEW_KIND = "multiview_bundle_v1"
SINGLE_VIEW_KIND = "single_view_v1"
SUPPORTED_INPUT_KINDS = frozenset({MULTIVIEW_KIND, SINGLE_VIEW_KIND})
INPUT_REFERENCE_SCHEMA_VERSION = "skyforge.reconstruction-input-reference.v1"
SINGLE_VIEW_SCHEMA_VERSION = "skyforge.single-view-reconstruction-input.v1"
SINGLE_VIEW_ROLE = "beauty_three_quarter_reconstruction_reference"
SINGLE_VIEW_PROVENANCE = "human_approved_beauty_reference"


class ReconstructionInputError(ValueError):
    """Raised when a reconstruction input is malformed, unsafe, or unapproved."""


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ReconstructionInputError(f"Unsafe reconstruction-input path: {value}")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def single_view_content_digest(document: dict[str, Any]) -> str:
    projection = {
        key: value for key, value in document.items() if key not in {"approval", "inputDigest"}
    }
    return hashlib.sha256(canonicalize(projection)).hexdigest()


def build_single_view_input(
    root: Path,
    *,
    source_path: Path,
    asset_id: str,
    profile_id: str,
    original_filename: str,
    provenance: str,
    provenance_source_type: str,
    imported_at: str,
    source_commit: str,
) -> dict[str, Any]:
    if profile_id not in SUPPORTED_PROFILES:
        raise ReconstructionInputError(f"Unsupported reconstruction profile: {profile_id}")
    if source_path.is_symlink() or not source_path.is_file():
        raise ReconstructionInputError("Single-view source must be a regular non-symlink file")
    resolved_root = root.resolve()
    resolved = source_path.resolve()
    try:
        relative = resolved.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise ReconstructionInputError("Single-view source must be contained in its workspace") from exc
    _safe_relative(relative)
    digest = _sha256(source_path)
    assert_reconstruction_hashes_eligible([digest])
    try:
        with Image.open(source_path) as image:
            image.verify()
        with Image.open(source_path) as image:
            dimensions = [image.width, image.height]
            mode = image.mode
    except Exception as exc:
        raise ReconstructionInputError("Single-view source is not a readable supported image") from exc
    if provenance != SINGLE_VIEW_PROVENANCE or not provenance_source_type.strip():
        raise ReconstructionInputError("Single-view source requires explicit human beauty provenance")
    document = {
        "schemaVersion": SINGLE_VIEW_SCHEMA_VERSION,
        "inputKind": SINGLE_VIEW_KIND,
        "assetId": asset_id,
        "profileId": profile_id,
        "declaredRole": SINGLE_VIEW_ROLE,
        "source": {
            "path": relative,
            "sha256": digest,
            "dimensions": dimensions,
            "mode": mode,
            "provenance": provenance,
            "provenanceSourceType": provenance_source_type,
            "originalFilename": Path(original_filename).name,
        },
        "importedAt": imported_at,
        "sourceCommit": source_commit,
        "approval": None,
    }
    document["inputDigest"] = single_view_content_digest(document)
    validate_single_view_input(root, document, require_approved=False)
    return document


def validate_single_view_input(
    root: Path, document: dict[str, Any], *, require_approved: bool = True
) -> str:
    if document.get("schemaVersion") != SINGLE_VIEW_SCHEMA_VERSION:
        raise ReconstructionInputError("Unsupported single-view reconstruction-input schema")
    if document.get("inputKind") != SINGLE_VIEW_KIND:
        raise ReconstructionInputError("Single-view reconstruction inputKind changed")
    if document.get("profileId") not in SUPPORTED_PROFILES:
        raise ReconstructionInputError("Unsupported single-view reconstruction profile")
    if document.get("declaredRole") != SINGLE_VIEW_ROLE:
        raise ReconstructionInputError("Single-view reconstruction role changed")
    source = document.get("source")
    if not isinstance(source, dict):
        raise ReconstructionInputError("Single-view source record is unavailable")
    relative = _safe_relative(source.get("path", ""))
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise ReconstructionInputError("Single-view source must be a regular non-symlink file")
    actual_hash = _sha256(path)
    if source.get("sha256") != actual_hash:
        raise ReconstructionInputError("Single-view source mutated after binding")
    assert_reconstruction_hashes_eligible([actual_hash])
    try:
        with Image.open(path) as image:
            if source.get("dimensions") != [image.width, image.height] or source.get("mode") != image.mode:
                raise ReconstructionInputError("Single-view image metadata changed")
    except ReconstructionInputError:
        raise
    except Exception as exc:
        raise ReconstructionInputError("Single-view source is unreadable") from exc
    if source.get("provenance") != SINGLE_VIEW_PROVENANCE or not source.get("provenanceSourceType"):
        raise ReconstructionInputError("Single-view provenance is not approvable")
    if source.get("originalFilename") != Path(str(source.get("originalFilename", ""))).name:
        raise ReconstructionInputError("Single-view original filename is unsafe")
    digest = single_view_content_digest(document)
    if document.get("inputDigest") != digest:
        raise ReconstructionInputError("Single-view canonical digest mismatch")
    approval = document.get("approval")
    if require_approved and (
        not isinstance(approval, dict)
        or approval.get("status") != "APPROVED"
        or approval.get("inputDigest") != digest
        or not approval.get("approvedAt")
        or not approval.get("workflowId")
    ):
        raise ReconstructionInputError("Single-view input is not approved for its exact digest")
    return digest


def approve_single_view_input(
    root: Path, document: dict[str, Any], *, approved_at: str, workflow_id: str
) -> dict[str, Any]:
    digest = validate_single_view_input(root, document, require_approved=False)
    approved = json.loads(json.dumps(document))
    approved["approval"] = {
        "status": "APPROVED",
        "approvedAt": approved_at,
        "workflowId": workflow_id,
        "inputDigest": digest,
    }
    return approved


def input_kind(document: dict[str, Any]) -> str:
    if document.get("schemaVersion") == MULTIVIEW_SCHEMA_VERSION:
        return MULTIVIEW_KIND
    kind = document.get("inputKind")
    if kind == SINGLE_VIEW_KIND and document.get("schemaVersion") == SINGLE_VIEW_SCHEMA_VERSION:
        return SINGLE_VIEW_KIND
    raise ReconstructionInputError("Unknown reconstruction inputKind")


def validate_reconstruction_input(
    root: Path, document: dict[str, Any], *, require_approved: bool = True
) -> str:
    kind = input_kind(document)
    if kind == MULTIVIEW_KIND:
        digest = validate_bundle(root, document, require_approved=require_approved)
        assert_reconstruction_hashes_eligible(item["sha256"] for item in document["views"])
        return digest
    return validate_single_view_input(root, document, require_approved=require_approved)


def reconstruction_input_reference(root: Path, document: dict[str, Any]) -> dict[str, Any]:
    kind = input_kind(document)
    digest = validate_reconstruction_input(root, document, require_approved=True)
    if kind == MULTIVIEW_KIND:
        hashes = [item["sha256"] for item in document["views"]]
        paths = [item["path"] for item in document["views"]]
    else:
        hashes = [document["source"]["sha256"]]
        paths = [document["source"]["path"]]
    return {
        "schemaVersion": INPUT_REFERENCE_SCHEMA_VERSION,
        "inputKind": kind,
        "reconstructionInputDigest": digest,
        "sourceSha256s": hashes,
        "sourcePaths": paths,
        "profileId": document["profileId"],
    }


def reconstruction_image_paths(root: Path, document: dict[str, Any]) -> list[Path]:
    reference = reconstruction_input_reference(root, document)
    return [root / _safe_relative(path) for path in reference["sourcePaths"]]


def human_approval(document: dict[str, Any]) -> dict[str, str]:
    approval = document.get("approval") or {}
    return {"approvedAt": approval.get("approvedAt"), "workflowId": approval.get("workflowId")}
