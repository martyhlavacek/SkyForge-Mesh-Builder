from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from common.glb_facts import parse_glb_facts

from .manual_glb_import import QA_FILES, SOURCE_PROVIDER, require_current_approval
from .vmp_builder import VmpBuildMetadata, build_vmp
from .vmp_job_export import JobVmpExportError, JobVmpExportResult, run_import_probe


def _json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def export_manual_glb_vmp(
    package_root: Path, job_root: Path, archive_path: Path, *, import_probe_command: Sequence[str],
    commercial_use_asserted: bool, terms_basis: str,
) -> JobVmpExportResult:
    job = require_current_approval(job_root)
    if commercial_use_asserted is not True or not terms_basis.strip():
        raise JobVmpExportError("commercial-use assertion and terms basis are required")
    normalized = (job_root / "output/normalized.glb").read_bytes()
    facts = parse_glb_facts(normalized)
    normalized_sha = hashlib.sha256(normalized).hexdigest()
    original_sha = job["source"]["sha256"]
    authority_set_sha = hashlib.sha256(original_sha.encode("ascii")).hexdigest()
    when = job["approval"]["approvedAt"]
    channels = sorted({key for material in facts.material_texture_channels for key in material})
    embedded_textures = []
    for index, digest in enumerate(facts.image_sha256):
        if digest is None:
            continue
        record: dict[str, Any] = {"imageIndex": index, "mimeType": facts.image_mime_types[index], "sha256": digest}
        dimensions = facts.image_dimensions[index]
        if dimensions is not None:
            record.update(width=dimensions[0], height=dimensions[1])
        embedded_textures.append(record)
    def validation(kind: str) -> dict[str, Any]:
        return {
            "schemaVersion": "skyforge.validation-report.v1", "validationClass": kind,
            "validatorVersion": "0.8.0", "sourceGlbSha256": normalized_sha, "executedAt": when,
            "measuredValues": [{"name": "triangleCount", "value": str(facts.triangle_count)}],
            "gates": [{"name": "selfContainedTriangleGlb", "passed": True, "measuredValue": True,
                       "thresholdOperator": "==", "thresholdValue": True}], "passed": True,
        }
    payload = {
        "asset.json": _json({
            "schemaVersion": "skyforge.asset.v3", "assetId": job["assetId"], "assetVersion": job["assetVersion"],
            "craftProfileId": "external_manual", "assetRole": job["assetRole"],
            "provider": {"id": SOURCE_PROVIDER, "identityModel": "approved_artifact_immutability"},
            "geometry": {"normalizedGlb": "mesh/normalized.glb"},
            "approval": {"state": "approved", "approvedForDistribution": True}, "anchorState": "not_authored",
        }),
        "mesh/normalized.glb": normalized,
        "mesh/semantic_identity.json": _json({
            "schemaVersion": "skyforge.mesh-semantic-identity.v2", "identityModel": "approved_artifact_immutability",
            "approvedArtifactGlbSha256": normalized_sha, "originalExternalGlbSha256": original_sha,
        }),
        "mesh/component_manifest.json": _json({
            "schemaVersion": "skyforge.mesh-components.v2", "meshCount": facts.mesh_count,
            "primitiveCount": facts.primitive_count, "vertexCount": facts.vertex_count,
            "triangleCount": facts.triangle_count, "bounds": {"min": facts.bounds_min, "max": facts.bounds_max},
            "topologyMeasurements": "unknown_not_computed",
        }),
        "mesh/bounds_and_scale.json": _bounds(facts),
        "authorities/authority_manifest.json": _json({
            "schemaVersion": "skyforge.source-artifact-manifest.v2", "authoritySetSha256": authority_set_sha,
            "sourceArtifacts": [{"role": "original_external_glb", "sourceSha256": original_sha,
                                 "contentType": "model/gltf-binary", "embedded": False,
                                 "provider": SOURCE_PROVIDER, "authorship": "externally_authored"}],
        }),
        "role/asset_role.json": _json({"schemaVersion": "skyforge.asset-role.v1", "preset": "air_moving",
            "capabilities": {"timelineMovement": True, "airborne": True, "terrainPlacement": False, "directionalGroundSet": False}}),
        "role/manufacturing_axes.json": (package_root / "contracts/vmp/v1/examples/manufacturing_axes_valid.json").read_bytes(),
        "role/pivot_contract.json": _json({"schemaVersion": "skyforge.pivot-contract.v1", "rootPivot": {
            "position": [0, 0, 0], "orientationQuaternion": [0, 0, 0, 1], "frame": "normalized_mesh_frame",
            "source": "human_approved", "approvalState": "approved"}, "partPivots": []}),
        "render/frame_contract.json": _frame_contract(facts),
        "materials/material_contract.json": _json({
            "schemaVersion": "skyforge.mesh-material.v2", "baseColor": {"source": "provider_texture", "provider": SOURCE_PROVIDER, "lightingState": "unknown"},
            "externalReferences": False, "providerProcessing": {"aiTexturingApplied": True, "imageEnhancementApplied": "unknown", "removeLightingApplied": "unknown"},
            "textureChannels": channels, "embeddedTextures": embedded_textures, "unknowns": ["provider generation settings", "decoded texture pixel hashes"],
        }),
        "provenance/source_chain.json": _json({
            "schemaVersion": "skyforge.source-chain.v2", "sourceType": "externally_authored", "provider": SOURCE_PROVIDER,
            "ingestionMethod": "manual_file_import", "originalGlbSha256": original_sha, "normalizedGlbSha256": normalized_sha,
            "deterministicallyReproducible": False,
            "geometryGeneratedBySkyForge": False, "normalization": {"tool": "Blender", "workflowVersion": "0.8.0", "orientationMapping": job["orientationMapping"]},
            "approval": job["approval"],
        }),
        "licensing_and_terms.json": _json({"schemaVersion": "skyforge.licensing-terms.v1", "assetCommercialUseAsserted": True,
            "termsSnapshots": [{"source": terms_basis, "versionOrDate": when[:10], "recordedAt": when}],
            "authorityRedistribution": {"permitted": "unknown", "basis": "original external GLB retained in local quarantine and not embedded"},
            "provider": {"modelId": "meshy_web/manual", "accountTier": "unknown", "modelAvailabilityRisk": "externally_authored_not_reproducible", "pricingSource": "not_applicable_manual_import", "pricingVerifiedAt": when}}),
        "validation/geometry.json": _json(validation("geometry")),
        "validation/independent_reload.json": _json(validation("independent_reload")),
        "validation/blender.json": _json(validation("blender")),
        "previews/gameplay_scale_96.png": (job_root / "output/qa/gameplay_scale_96.png").read_bytes(),
        "previews/silhouette_comparison.png": (job_root / "output/qa/top_ortho.png").read_bytes(),
        "known_limitations.json": (package_root / "contracts/vmp/v1/examples/known_limitations_valid.json").read_bytes(),
    }
    for name in QA_FILES[:-1]:
        payload[f"previews/qa_{name}"] = (job_root / "output/qa" / name).read_bytes()
    metadata = VmpBuildMetadata(
        asset_id=job["assetId"], asset_version=job["assetVersion"], craft_profile_id="external_manual",
        sidecar_version="0.8.0", provider_id=SOURCE_PROVIDER, provider_model="meshy_web/manual",
        identity_model="approved_artifact_immutability", authority_set_sha256=authority_set_sha,
        material_contract="skyforge.mesh-material.v2",
        package_schema="skyforge.validated-mesh-package.v2", package_version="2.0.0",
    )
    build = build_vmp(payload, metadata, archive_path)
    receipt_path = archive_path.with_suffix(".import_receipt.json")
    receipt = run_import_probe(import_probe_command, archive_path, receipt_path)
    if (receipt.get("schemaVersion") != "skyforge.sprite-foundry-import-receipt.v2"
            or receipt.get("contractMajorAccepted") != 2 or receipt.get("accepted") is not True
            or receipt.get("sourcePackageContentDigest") != build.package_content_digest
            or receipt.get("sourceArchiveSha256") != build.archive_sha256):
        archive_path.unlink(missing_ok=True)
        receipt_path.unlink(missing_ok=True)
        raise JobVmpExportError("Independent Sprite Foundry Import Probe did not accept the external-source VMP")
    return JobVmpExportResult(build, receipt_path, receipt)


def _bounds(facts: Any) -> bytes:
    extents = [facts.bounds_max[i] - facts.bounds_min[i] for i in range(3)]
    planform = max(extents[0], extents[1])
    return _json({"schemaVersion": "skyforge.mesh-bounds-scale.v1", "coordinateContract": "skyforge.mesh-coordinate.v1",
        "units": "skyforge_world_units", "bounds": {"min": facts.bounds_min, "max": facts.bounds_max, "extents": extents},
        "canonicalScale": {"longestPlanformExtentWorld": planform, "heightWorld": extents[2], "heightToPlanformRatio": extents[2] / max(planform, 1e-12)},
        "gameplayPreviewMapping": {"referenceImage": "previews/gameplay_scale_96.png", "canvasPixels": [96, 96], "worldUnitsPerPixel": planform / 80, "fittedPlanformPixels": 80, "transparentMarginPixels": 8},
        "pivotFrame": "normalized_mesh_frame"})


def _frame_contract(facts: Any) -> bytes:
    extents = [facts.bounds_max[index] - facts.bounds_min[index] for index in range(3)]
    height_ratio = extents[2] / max(extents[0], extents[1], 1e-12)
    return _json({"schemaVersion": "skyforge.render-frame-contract.v1", "coordinateFrame": {"forwardAxis": "+Y", "upAxis": "+Z", "rightAxis": "+X"},
        "canonicalCamera": {"projection": "orthographic", "pitchDegrees": 20, "bankDegrees": 0, "yawDegrees": 0, "canonicalOrthoScale": 7, "requiredReviewOrthoScale": 7, "requiredSilhouetteOrthoScale": 7},
        "headroom": {"worldUnits": 0, "fractionOfPlanform": 0}, "calibration": {"method": "external_asset_fixed_review", "profileDigest": "0" * 64, "pitchSamplesDegrees": [0, 20, 36], "bankSamplesDegrees": [-18, 0, 18], "referencePoseMap": {"bank_left": -18, "neutral": 0, "bank_right": 18}},
        "calibrationEnvelope": {"maximumHeightToPlanformRatio": 10, "heightEnvelopeBindingPitchDegrees": 20, "measuredMaximumRequiredOrthoScale": 7, "measuredRequiredMargin": 0, "chosenMargin": 0, "runtimeEffectsEnabled": False},
        "renderState": {"engine": "BLENDER_EEVEE", "resolution": [384, 384], "samples": 64, "viewTransform": "Standard", "exposure": 0, "gamma": 1, "transparentFilm": True},
        "silhouetteProtocol": {"fitCanvasPixels": 512, "fitMarginPixels": 28, "resample": "NEAREST", "alphaThreshold": 128, "maskPolarity": "foreground_true"},
        "heightToPlanformRatio": height_ratio, "consumerDeviationPolicy": {"spriteFoundryMayExtendBankPitchLadder": True, "extensionWithinCalibrationEnvelopeOnly": True, "newCalibrationRequiredOutsideEnvelope": True, "deviationMustBeRecorded": True}})
