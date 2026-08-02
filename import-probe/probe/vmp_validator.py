from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .archive_reader import ArchiveLimits, read_archive
from .canonical_digest import build_digest_payload, canonicalize
from .contracts import ProbeContractError, validate
from .errors import ProbeReject
from .glb_reader import embedded_images, parse_glb
from .texture_reader import decode_png

IMPORTER_VERSION = "1.0.0"
REQUIRED_FILES = {
    "VMP_MANIFEST.json", "SHA256SUMS.txt", "asset.json", "mesh/normalized.glb",
    "mesh/semantic_identity.json", "mesh/component_manifest.json", "mesh/bounds_and_scale.json",
    "authorities/authority_manifest.json", "role/asset_role.json", "role/manufacturing_axes.json",
    "role/pivot_contract.json", "render/frame_contract.json", "materials/material_contract.json",
    "provenance/source_chain.json", "licensing_and_terms.json", "validation/geometry.json",
    "validation/independent_reload.json", "validation/blender.json", "previews/gameplay_scale_96.png",
    "previews/silhouette_comparison.png", "known_limitations.json",
}
SCHEMAS = {
    "VMP_MANIFEST.json": "validated_mesh_package.schema.json",
    "asset.json": "asset_v3.schema.json",
    "mesh/semantic_identity.json": "semantic_identity.schema.json",
    "mesh/component_manifest.json": "component_manifest.schema.json",
    "mesh/bounds_and_scale.json": "bounds_and_scale.schema.json",
    "authorities/authority_manifest.json": "authority_manifest.schema.json",
    "role/asset_role.json": "asset_role.schema.json",
    "role/manufacturing_axes.json": "manufacturing_axes.schema.json",
    "role/pivot_contract.json": "pivot_contract.schema.json",
    "render/frame_contract.json": "frame_contract.schema.json",
    "materials/material_contract.json": "material_contract.schema.json",
    "provenance/source_chain.json": "source_chain.schema.json",
    "licensing_and_terms.json": "licensing_and_terms.schema.json",
    "validation/geometry.json": "validation_report.schema.json",
    "validation/independent_reload.json": "validation_report.schema.json",
    "validation/blender.json": "validation_report.schema.json",
    "known_limitations.json": "known_limitations.schema.json",
}


def import_vmp(
    archive_path: Path,
    *,
    limits: ArchiveLimits | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    snapshot = read_archive(archive_path, limits)
    entries = snapshot.entries
    missing = sorted(REQUIRED_FILES - set(entries))
    if missing:
        raise ProbeReject("required_file_missing", ", ".join(missing))
    _verify_checksums(entries)
    documents = _load_and_validate_documents(entries)
    manifest = documents["VMP_MANIFEST.json"]
    _verify_content_index(entries, manifest)
    _verify_package_identity(manifest)
    _verify_compatibility(manifest)
    _verify_cross_contracts(entries, documents)
    glb = parse_glb(entries["mesh/normalized.glb"])
    _verify_glb_contract(entries, documents, glb)
    authority_reverification = _verify_authority(entries, documents)
    collision_ignored = _verify_collision_hint(documents["asset.json"])
    manufacturing_verified = documents["role/manufacturing_axes.json"]["ownership"] == {
        "bankPitchRendering": "sprite_foundry",
        "perFrameSocketProjection": "sprite_foundry",
        "runtimeSocketAcceptance": "gameplay_integration",
    }
    if not manufacturing_verified:
        raise ProbeReject("manufacturing_axis_ownership", "manufacturing-axis ownership is not exact")
    source_archive_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    when = created_at or datetime.now(timezone.utc).isoformat()
    receipt = {
        "schemaVersion": "skyforge.sprite-foundry-import-receipt.v1",
        "receiptId": "sfimport:" + hashlib.sha256(
            f"{source_archive_sha}:{manifest['packageContentDigest']}:{IMPORTER_VERSION}".encode()
        ).hexdigest(),
        "sourceArchiveSha256": source_archive_sha,
        "sourcePackageContentDigest": manifest["packageContentDigest"],
        "sourcePackageId": manifest["packageId"],
        "importerVersion": IMPORTER_VERSION,
        "accepted": True,
        "schemasAccepted": sorted(set(SCHEMAS.values())),
        "authorityReverification": authority_reverification,
        "manufacturingAxesVerified": True,
        "collisionHintsIgnoredForRuntime": collision_ignored,
        "createdAt": when,
        "diagnostics": [
            f"glb_vertices={glb.vertex_count}",
            f"glb_triangles={glb.triangle_count}",
            f"glb_materials={glb.material_count}",
            f"glb_images={glb.image_count}",
        ],
    }
    try:
        validate("sprite_foundry_import_receipt.schema.json", receipt)
    except ProbeContractError as exc:
        raise ProbeReject("receipt_schema", str(exc)) from exc
    return receipt


def _verify_checksums(entries: dict[str, bytes]) -> None:
    try:
        text = entries["SHA256SUMS.txt"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProbeReject("checksum_manifest", "SHA256SUMS.txt is not UTF-8") from exc
    declared: dict[str, str] = {}
    for line in text.splitlines():
        if len(line) < 67 or line[64:66] != "  ":
            raise ProbeReject("checksum_manifest", "malformed checksum line")
        digest, path = line[:64], line[66:]
        if any(character not in "0123456789abcdef" for character in digest) or path in declared:
            raise ProbeReject("checksum_manifest", "invalid or duplicate checksum entry")
        declared[path] = digest
    actual_paths = set(entries) - {"SHA256SUMS.txt"}
    if set(declared) != actual_paths:
        added = sorted(actual_paths - set(declared))
        missing = sorted(set(declared) - actual_paths)
        raise ProbeReject(
            "checksum_file_set",
            "unlisted package-root members=" + (", ".join(added) if added else "none")
            + "; missing declared members=" + (", ".join(missing) if missing else "none"),
        )
    for path, digest in declared.items():
        if hashlib.sha256(entries[path]).hexdigest() != digest:
            raise ProbeReject("checksum_mismatch", path)


def _load_and_validate_documents(entries: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for path, schema in SCHEMAS.items():
        try:
            document = json.loads(entries[path])
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProbeReject("json_decode", path) from exc
        _precheck_semantic_mutations(path, document)
        try:
            validate(schema, document)
        except ProbeContractError as exc:
            raise ProbeReject("schema_rejection", f"{path}: {exc}") from exc
        documents[path] = document
    return documents



def _precheck_semantic_mutations(path: str, document: dict[str, Any]) -> None:
    expected_schema = {
        "VMP_MANIFEST.json": "skyforge.validated-mesh-package.v1",
        "asset.json": "skyforge.asset.v3",
        "mesh/bounds_and_scale.json": "skyforge.mesh-bounds-scale.v1",
        "authorities/authority_manifest.json": "skyforge.authority-manifest.v1",
        "role/asset_role.json": "skyforge.asset-role.v1",
        "render/frame_contract.json": "skyforge.render-frame-contract.v1",
    }.get(path)
    if expected_schema is not None and document.get("schemaVersion") != expected_schema:
        raise ProbeReject("unsupported_schema_major", f"{path}: {document.get('schemaVersion')!r}")
    if path == "VMP_MANIFEST.json" and document.get("approval", {}).get("approvedForDistribution") is not True:
        raise ProbeReject("approval_not_granted", "package is not approved for Sprite Foundry distribution")
    if path == "asset.json":
        if document.get("assetRole") != "air_moving":
            raise ProbeReject("role_incompatible", "only air_moving is supported")
        hint = document.get("collisionHint")
        if isinstance(hint, dict) and (
            hint.get("authoritative") is not False or hint.get("consumerMustIgnoreForRuntime") is not True
        ):
            raise ProbeReject("collision_hint_authoritative", "collision hint attempted to become runtime authority")
    if path == "mesh/bounds_and_scale.json" and document.get("coordinateContract") != "skyforge.mesh-coordinate.v1":
        raise ProbeReject("coordinate_mismatch", "unsupported coordinate contract")
    if path == "role/asset_role.json" and document.get("preset") != "air_moving":
        raise ProbeReject("role_incompatible", "only air_moving is supported")
    if path == "render/frame_contract.json":
        deviation = document.get("consumerDeviationPolicy", {})
        if deviation.get("spriteFoundryMayExtendBankPitchLadder") is True and "calibrationEnvelope" not in document:
            raise ProbeReject("frame_calibration_envelope_missing", "pose extension requires calibrationEnvelope")
        axes = document.get("coordinateFrame")
        if axes != {"forwardAxis": "+Y", "upAxis": "+Z", "rightAxis": "+X"}:
            raise ProbeReject("coordinate_mismatch", "frame coordinate axes differ from frozen contract")
    if path == "authorities/authority_manifest.json":
        for item in document.get("authorities", []):
            if item.get("embedded") is True and item.get("redistributionPermission") != "permitted":
                raise ProbeReject("authority_embedding_terms", "embedded authority lacks permitted redistribution")

def _verify_content_index(entries: dict[str, bytes], manifest: dict[str, Any]) -> None:
    index = manifest["contentIndex"]
    actual_payload = set(entries) - {"VMP_MANIFEST.json", "SHA256SUMS.txt"}
    if set(index) != actual_payload:
        raise ProbeReject("content_index_file_set", "content index does not match payload members")
    for path, record in index.items():
        data = entries[path]
        if record["sizeBytes"] != len(data) or record["sha256"] != hashlib.sha256(data).hexdigest():
            raise ProbeReject("content_index_mismatch", path)


def _verify_package_identity(manifest: dict[str, Any]) -> None:
    digest = hashlib.sha256(canonicalize(build_digest_payload(manifest))).hexdigest()
    if digest != manifest["packageContentDigest"]:
        raise ProbeReject("package_digest_mismatch", "semantic package digest does not match")
    if manifest["packageId"] != f"sfmeshpack:{digest}":
        raise ProbeReject("package_id_mismatch", "packageId does not derive from package digest")


def _verify_compatibility(manifest: dict[str, Any]) -> None:
    minimum = manifest["contracts"]["minimumSpriteFoundryImporter"]
    if _semver_tuple(IMPORTER_VERSION) < _semver_tuple(minimum):
        raise ProbeReject("importer_incompatible", f"requires importer {minimum}")


def _verify_cross_contracts(entries: dict[str, bytes], documents: dict[str, dict[str, Any]]) -> None:
    manifest = documents["VMP_MANIFEST.json"]
    asset = documents["asset.json"]
    authority = documents["authorities/authority_manifest.json"]
    role = documents["role/asset_role.json"]
    bounds = documents["mesh/bounds_and_scale.json"]
    frame = documents["render/frame_contract.json"]
    source = documents["provenance/source_chain.json"]
    identity = documents["mesh/semantic_identity.json"]
    if asset["assetId"] != manifest["assetId"] or asset["assetVersion"] != manifest["assetVersion"]:
        raise ProbeReject("asset_identity_mismatch", "asset identity differs from manifest")
    if asset["craftProfileId"] != manifest["craftProfileId"]:
        raise ProbeReject("craft_profile_mismatch", "craft profile differs from manifest")
    if asset["assetRole"] != "air_moving" or role["preset"] != "air_moving":
        raise ProbeReject("role_incompatible", "only air_moving is supported")
    if asset["provider"]["id"] != manifest["producer"]["providerId"]:
        raise ProbeReject("provider_identity_mismatch", "provider differs from manifest")
    if authority["authoritySetSha256"] != manifest["source"]["authoritySetSha256"]:
        raise ProbeReject("authority_set_mismatch", "authority set differs from manifest")
    if source["authoritySetSha256"] != authority["authoritySetSha256"]:
        raise ProbeReject("authority_provenance_mismatch", "source chain differs from authority manifest")
    if bounds["coordinateContract"] != manifest["contracts"]["coordinateContract"]:
        raise ProbeReject("coordinate_mismatch", "bounds coordinate contract differs from manifest")
    axes = frame["coordinateFrame"]
    if axes != {"forwardAxis": "+Y", "upAxis": "+Z", "rightAxis": "+X"}:
        raise ProbeReject("coordinate_mismatch", "frame coordinate axes differ from frozen contract")
    if frame["heightToPlanformRatio"] > frame["calibrationEnvelope"]["maximumHeightToPlanformRatio"]:
        raise ProbeReject("frame_contract_mismatch", "asset exceeds calibration height envelope")
    if identity["blenderSilhouetteIoUMin"] != 0.94:
        raise ProbeReject("silhouette_floor", "Blender IoU floor changed")
    for path in ("validation/geometry.json", "validation/independent_reload.json", "validation/blender.json"):
        if not documents[path]["passed"]:
            raise ProbeReject("validation_not_passed", path)


def _verify_glb_contract(entries: dict[str, bytes], documents: dict[str, dict[str, Any]], glb) -> None:
    glb_sha = hashlib.sha256(entries["mesh/normalized.glb"]).hexdigest()
    components = documents["mesh/component_manifest.json"]
    component = components["components"][0]
    if components["componentCount"] != 1 or len(components["components"]) != 1:
        raise ProbeReject("component_policy", "single component is required")
    if component["vertexCount"] != glb.vertex_count or component["triangleCount"] != glb.triangle_count:
        raise ProbeReject("component_count_mismatch", "GLB counts differ from component manifest")
    for validation in ("validation/geometry.json", "validation/independent_reload.json", "validation/blender.json"):
        if documents[validation]["sourceGlbSha256"] != glb_sha:
            raise ProbeReject("validation_glb_mismatch", validation)
    material = documents["materials/material_contract.json"]
    if material["externalReferences"] is not False or material["providerProcessing"]["aiTexturingApplied"] is not False:
        raise ProbeReject("material_contract", "external references or AI texturing are prohibited")
    decoded_glb_images = []
    for mime, data in embedded_images(glb):
        if mime != "image/png":
            raise ProbeReject("texture_content_type", f"unsupported embedded image type: {mime}")
        decoded_glb_images.append(decode_png(data))
    for texture in material["textures"]:
        path = texture["path"]
        if path not in entries:
            raise ProbeReject("texture_missing", path)
        facts = decode_png(entries[path])
        if facts.content_sha256 != texture["sha256"] or facts.decoded_pixel_sha256 != texture["decodedPixelSha256"]:
            raise ProbeReject("texture_hash_mismatch", path)


def _verify_authority(entries: dict[str, bytes], documents: dict[str, dict[str, Any]]) -> str:
    authority = documents["authorities/authority_manifest.json"]
    licensing = documents["licensing_and_terms.json"]
    results = set()
    for item in authority["authorities"]:
        if item["embedded"]:
            path = item["embeddedPath"]
            if licensing["authorityRedistribution"]["permitted"] is not True:
                raise ProbeReject("authority_embedding_terms", "embedded authority is not redistribution-permitted")
            if path not in entries or hashlib.sha256(entries[path]).hexdigest() != item["sourceSha256"]:
                raise ProbeReject("authority_hash_mismatch", path)
            decode_png(entries[path])
            results.add("full")
        else:
            if "embeddedPath" in item or item["embeddingDecision"] != "hash_only_due_to_terms":
                raise ProbeReject("authority_hash_only_contract", "hash-only authority declaration is inconsistent")
            results.add("unavailable_due_to_terms")
    if len(results) != 1:
        raise ProbeReject("authority_reverification_mixed", "mixed authority reverification states are unsupported")
    return results.pop()


def _verify_collision_hint(asset: dict[str, Any]) -> bool:
    hint = asset.get("collisionHint")
    if hint is not None and (hint.get("authoritative") is not False or hint.get("consumerMustIgnoreForRuntime") is not True):
        raise ProbeReject("collision_hint_authoritative", "collision hint attempted to become runtime authority")
    return True


def _semver_tuple(value: str) -> tuple[int, int, int]:
    try:
        major, minor, patch = value.split(".")
        return int(major), int(minor), int(patch)
    except (ValueError, AttributeError) as exc:
        raise ProbeReject("semver_invalid", value) from exc
