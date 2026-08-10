from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from .cross_view import CAMERA_DECLARATION_PASS, CrossViewError, require_cross_view_consistency
from .quarantine import QuarantineError, assert_reconstruction_hashes_eligible

VIEW_ORDER = ("top", "front", "right")
SUPPORTED_PROFILES = frozenset({"enemy_gunship", "enemy_interceptor"})
SCHEMA_VERSION = "skyforge.multiview-authority-bundle.v1"


class BundleError(ValueError):
    """Raised when a multiview authority bundle is unsafe or invalid."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(path: str) -> PurePosixPath:
    value = PurePosixPath(path)
    if value.is_absolute() or ".." in value.parts or not value.parts:
        raise BundleError(f"Unsafe bundle-relative path: {path}")
    return value


def content_digest(bundle: dict[str, Any]) -> str:
    projection = {k: v for k, v in bundle.items() if k not in {"approval", "bundleDigest"}}
    return hashlib.sha256(canonical_bytes(projection)).hexdigest()


def build_bundle(
    root: Path,
    *,
    asset_id: str,
    profile_id: str,
    source_commit: str,
    created_at: str,
    views: list[tuple[str, Path]],
    contact_sheet: Path | None = None,
) -> dict[str, Any]:
    if profile_id not in SUPPORTED_PROFILES:
        raise BundleError(f"Unsupported reconstruction profile: {profile_id}")
    roles = [role for role, _path in views]
    if roles != list(VIEW_ORDER):
        raise BundleError("Views must be exactly top, front, right in that order")
    if len(set(roles)) != 3:
        raise BundleError("Duplicate multiview authority role")
    records = []
    for role, path in views:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise BundleError("Authority views must be contained in the bundle root") from exc
        if path.is_symlink() or not path.is_file():
            raise BundleError("Authority views must be regular non-symlink files")
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            records.append(
                {
                    "role": role,
                    "path": relative,
                    "sha256": sha256_file(path),
                    "dimensions": [image.width, image.height],
                    "mode": image.mode,
                    "hasAlpha": "A" in image.getbands(),
                    "backgroundStatus": "alpha_or_neutral_declared",
                }
            )
    if len({item["sha256"] for item in records}) != 3:
        raise BundleError("Every authority view must contain independently stored image bytes")
    try:
        assert_reconstruction_hashes_eligible(item["sha256"] for item in records)
    except QuarantineError as exc:
        raise BundleError(str(exc)) from exc
    measurement_paths = {role: path for role, path in views}
    try:
        cross_view = require_cross_view_consistency(measurement_paths)
    except CrossViewError as exc:
        raise BundleError(str(exc)) from exc
    if cross_view.get("result") != "PASS":
        raise BundleError("Cross-view measurement did not produce a passing result")
    bundle = {
        "schemaVersion": SCHEMA_VERSION,
        "assetId": asset_id,
        "profileId": profile_id,
        "createdAt": created_at,
        "sourceCommit": source_commit,
        "viewOrder": list(VIEW_ORDER),
        "cameraDeclaration": CAMERA_DECLARATION_PASS,
        "crossViewConsistency": cross_view,
        "views": records,
        "contactSheet": None
        if contact_sheet is None
        else {"path": contact_sheet.resolve().relative_to(root.resolve()).as_posix(), "sha256": sha256_file(contact_sheet)},
        "approval": None,
    }
    bundle["bundleDigest"] = content_digest(bundle)
    validate_bundle(root, bundle, require_approved=False)
    return bundle


def validate_bundle(root: Path, bundle: dict[str, Any], *, require_approved: bool = True) -> str:
    if bundle.get("schemaVersion") != SCHEMA_VERSION:
        raise BundleError("Unsupported multiview bundle schema")
    if bundle.get("profileId") not in SUPPORTED_PROFILES:
        raise BundleError(f"Unsupported reconstruction profile: {bundle.get('profileId')}")
    roles = [item.get("role") for item in bundle.get("views", [])]
    if roles != list(VIEW_ORDER) or bundle.get("viewOrder") != list(VIEW_ORDER):
        raise BundleError("Views must be exactly top, front, right in that order")
    if len(set(roles)) != 3:
        raise BundleError("Duplicate multiview authority role")
    hashes = [item.get("sha256") for item in bundle["views"]]
    if len(set(hashes)) != 3:
        raise BundleError("Every authority view must contain independently stored image bytes")
    for item in bundle["views"]:
        relative = _safe_relative(item["path"])
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise BundleError(f"Missing or unsafe authority view: {relative}")
        if sha256_file(path) != item["sha256"]:
            raise BundleError(f"Authority view mutated after binding: {relative}")
        with Image.open(path) as image:
            if [image.width, image.height] != item["dimensions"] or image.mode != item["mode"]:
                raise BundleError(f"Authority image metadata mismatch: {relative}")
    measurement_paths = {item["role"]: root / _safe_relative(item["path"]) for item in bundle["views"]}
    try:
        recomputed_cross_view = require_cross_view_consistency(measurement_paths)
    except CrossViewError as exc:
        raise BundleError(str(exc)) from exc
    if recomputed_cross_view.get("result") != "PASS":
        raise BundleError("Cross-view measurement did not produce a passing result")
    if bundle.get("crossViewConsistency") != recomputed_cross_view:
        raise BundleError("Cross-view measurement record mismatch")
    if bundle.get("cameraDeclaration") != CAMERA_DECLARATION_PASS:
        raise BundleError("Camera declaration is not derived from passing cross-view measurement")
    contact_sheet = bundle.get("contactSheet")
    if contact_sheet is not None:
        relative = _safe_relative(contact_sheet["path"])
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise BundleError(f"Missing or unsafe contact sheet: {relative}")
        if sha256_file(path) != contact_sheet["sha256"]:
            raise BundleError(f"Contact sheet mutated after binding: {relative}")
    digest = content_digest(bundle)
    if digest != bundle.get("bundleDigest"):
        raise BundleError("Bundle digest mismatch")
    approval = bundle.get("approval")
    if require_approved and (
        not approval
        or approval.get("status") != "APPROVED"
        or approval.get("bundleDigest") != digest
    ):
        raise BundleError("Bundle is not approved for its exact current digest")
    return digest


def approve_bundle(root: Path, bundle: dict[str, Any], *, approved_at: str, workflow_id: str) -> dict[str, Any]:
    digest = validate_bundle(root, bundle, require_approved=False)
    try:
        assert_reconstruction_hashes_eligible(item["sha256"] for item in bundle["views"])
    except QuarantineError as exc:
        raise BundleError(str(exc)) from exc
    approved = json.loads(json.dumps(bundle))
    approved["approval"] = {
        "status": "APPROVED",
        "approvedAt": approved_at,
        "workflowId": workflow_id,
        "bundleDigest": digest,
    }
    return approved


def render_contact_sheet(root: Path, bundle: dict[str, Any], output: Path) -> None:
    canvas = Image.new("RGB", (768, 284), "#161a20")
    draw = ImageDraw.Draw(canvas)
    for index, item in enumerate(bundle["views"]):
        with Image.open(root / _safe_relative(item["path"])) as source:
            fitted = ImageOps.contain(source.convert("RGB"), (240, 240))
        x = index * 256 + (256 - fitted.width) // 2
        canvas.paste(fitted, (x, 36 + (240 - fitted.height) // 2))
        draw.text((index * 256 + 8, 8), item["role"].upper(), fill="white")
    canvas.save(output)
