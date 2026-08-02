from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.vmp_builder import VmpBuildMetadata


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def metadata(authority_set_sha256: str, *, sidecar_version: str = "0.7.1") -> VmpBuildMetadata:
    return VmpBuildMetadata(
        asset_id="approved_gunship",
        asset_version="1.0.0",
        craft_profile_id="enemy_gunship",
        sidecar_version=sidecar_version,
        provider_id="local_deterministic",
        provider_model="skyforge.authority-two-sided-field@0.6.0",
        identity_model="deterministic_reproducibility",
        authority_set_sha256=authority_set_sha256,
    )


def payload(package_root: Path, *, embedded_authority: bool = True) -> tuple[dict[str, bytes], str]:
    glb = (package_root / "samples/v053_field_gunship_baseline.glb").read_bytes()
    authority_png = (package_root / "samples/approved_gunship_authority.png").read_bytes()
    authority_sha = hashlib.sha256(authority_png).hexdigest()
    authority_set_sha = hashlib.sha256(authority_sha.encode()).hexdigest()
    glb_sha = hashlib.sha256(glb).hexdigest()
    preview = authority_png
    zero = [0.0, 0.0, 0.0]
    one = [1.0, 1.0, 1.0]
    files = {
        "asset.json": json_bytes({
            "schemaVersion": "skyforge.asset.v3",
            "assetId": "approved_gunship",
            "assetVersion": "1.0.0",
            "craftProfileId": "enemy_gunship",
            "assetRole": "air_moving",
            "provider": {"id": "local_deterministic", "identityModel": "deterministic_reproducibility"},
            "geometry": {"normalizedGlb": "mesh/normalized.glb"},
            "approval": {"state": "approved", "approvedForDistribution": True},
            "anchorState": "not_authored",
        }),
        "mesh/normalized.glb": glb,
        "mesh/semantic_identity.json": json_bytes({
            "schemaVersion": "skyforge.mesh-semantic-identity.v1",
            "identityModel": "deterministic_reproducibility",
            "reference": {"localReferenceGlbSha256": glb_sha},
            "localDeterministicContract": {
                "exactIndices": True, "exactXZ": True, "exactUV": True,
                "exactDecodedTexturePixels": True, "yMaxAbsTolerance": 1e-5,
                "yRmsTolerance": 1e-6, "rawGlbShaGating": False, "rawGlbShaInformational": True,
            },
            "blenderSilhouetteIoUMin": 0.94,
            "measuredResults": [{"name": "blenderSilhouetteIoU", "value": 0.97}],
        }),
        "mesh/component_manifest.json": json_bytes({
            "schemaVersion": "skyforge.mesh-components.v1", "componentCount": 1,
            "componentPolicy": "single_component_required",
            "components": [{"componentId": "component-0", "primitiveOrNodeRefs": ["0"],
                "vertexCount": 19720, "triangleCount": 39460,
                "bounds": {"min": [-2.543750047683716, -0.11999999731779099, -2.440624952316284],
                           "max": [2.543750047683716, 0.7370193004608154, 2.440624952316284]},
                "volumeFraction": 1.0, "watertight": True, "eulerNumber": 2, "genus": 0,
                "boundaryEdges": 0, "nonManifoldEdges": 0}],
        }),
        "mesh/bounds_and_scale.json": json_bytes({
            "schemaVersion": "skyforge.mesh-bounds-scale.v1", "coordinateContract": "skyforge.mesh-coordinate.v1",
            "units": "skyforge_world_units", "bounds": {"min": zero, "max": one, "extents": one},
            "canonicalScale": {"longestPlanformExtentWorld": 1.0, "heightWorld": 0.2,
                "heightToPlanformRatio": 0.2},
            "gameplayPreviewMapping": {"referenceImage": "previews/gameplay_scale_96.png",
                "canvasPixels": [96, 96], "worldUnitsPerPixel": 0.01,
                "fittedPlanformPixels": 80, "transparentMarginPixels": 8},
            "pivotFrame": "normalized_mesh_frame",
        }),
        "role/asset_role.json": json_bytes({
            "schemaVersion": "skyforge.asset-role.v1", "preset": "air_moving",
            "capabilities": {"timelineMovement": True, "airborne": True,
                "terrainPlacement": False, "directionalGroundSet": False},
        }),
        "role/manufacturing_axes.json": (package_root / "contracts/vmp/v1/examples/manufacturing_axes_valid.json").read_bytes(),
        "role/pivot_contract.json": json_bytes({
            "schemaVersion": "skyforge.pivot-contract.v1",
            "rootPivot": {"position": zero, "orientationQuaternion": [0, 0, 0, 1],
                "frame": "normalized_mesh_frame", "source": "deterministic", "approvalState": "approved"},
            "partPivots": [],
        }),
        "render/frame_contract.json": (package_root / "contracts/vmp/v1/examples/frame_contract_valid.json").read_bytes(),
        "materials/material_contract.json": json_bytes({
            "schemaVersion": "skyforge.mesh-material.v1",
            "baseColor": {"source": "authority_projection", "colorSpace": "sRGB", "lightingState": "unlit_albedo"},
            "alphaPolicy": "straight_alpha", "externalReferences": False,
            "providerProcessing": {"imageEnhancementApplied": False, "removeLightingApplied": "not_applicable",
                "aiTexturingApplied": False}, "semanticRegions": [], "textures": [],
        }),
        "provenance/source_chain.json": json_bytes({
            "schemaVersion": "skyforge.source-chain.v1", "authoritySetSha256": authority_set_sha,
            "lineage": [
                {"stage": "authority", "artifactSha256": authority_sha, "producerId": "mesh_foundry"},
                {"stage": "normalized_mesh", "artifactSha256": glb_sha, "producerId": "mesh_foundry",
                 "providerModel": "skyforge.authority-two-sided-field@0.6.0"},
            ], "normalizationVersion": "0.7.1",
            "approvalEvents": [{"eventId": "approval-1", "state": "approved", "artifactSha256": glb_sha,
                "recordedAt": "2026-08-01T00:00:00Z"}],
        }),
        "licensing_and_terms.json": json_bytes({
            "schemaVersion": "skyforge.licensing-terms.v1", "assetCommercialUseAsserted": True,
            "termsSnapshots": [{"source": "project-governance", "versionOrDate": "2026-08-01",
                "recordedAt": "2026-08-01T00:00:00Z"}],
            "authorityRedistribution": {"permitted": embedded_authority, "basis": "explicit fixture assertion"},
            "provider": {},
        }),
        "previews/gameplay_scale_96.png": preview,
        "previews/silhouette_comparison.png": preview,
        "known_limitations.json": (package_root / "contracts/vmp/v1/examples/known_limitations_valid.json").read_bytes(),
    }
    for validation_class, path in (
        ("geometry", "validation/geometry.json"),
        ("independent_reload", "validation/independent_reload.json"),
        ("blender", "validation/blender.json"),
    ):
        files[path] = json_bytes({
            "schemaVersion": "skyforge.validation-report.v1", "validationClass": validation_class,
            "validatorVersion": "0.7.1", "sourceGlbSha256": glb_sha,
            "executedAt": "2026-08-01T00:00:00Z",
            "measuredValues": [{"name": "passed", "value": True}],
            "gates": [{"name": "fixture_gate", "passed": True, "measuredValue": True,
                "thresholdOperator": "==", "thresholdValue": True}], "passed": True,
        })
    authority_record = {
        "role": "silhouette_authority", "sourceSha256": authority_sha, "contentType": "image/png",
        "embedded": embedded_authority,
        "redistributionPermission": "permitted" if embedded_authority else "unknown",
        "embeddingDecision": "embedded" if embedded_authority else "hash_only_due_to_terms",
        "independentReverification": "full" if embedded_authority else "unavailable_due_to_terms",
        "generationProvenanceRef": "provenance/source_chain.json#authority-1",
    }
    if embedded_authority:
        authority_record["embeddedPath"] = "authorities/silhouette_authority.png"
        files["authorities/silhouette_authority.png"] = authority_png
    files["authorities/authority_manifest.json"] = json_bytes({
        "schemaVersion": "skyforge.authority-manifest.v1", "authoritySetSha256": authority_set_sha,
        "authorities": [authority_record],
    })
    return files, authority_set_sha
