from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = PACKAGE_ROOT / "contracts" / "vmp" / "v1" / "schemas"
EXAMPLE_ROOT = PACKAGE_ROOT / "contracts" / "vmp" / "v1" / "examples"
DRAFT = "https://json-schema.org/draft/2020-12/schema"
HEX64 = "^[0-9a-f]{64}$"
SEMVER = r"^[0-9]+\.[0-9]+\.[0-9]+$"
PACKAGE_ID = r"^sfmeshpack:[0-9a-f]{64}$"

DIGEST_FIELDS = [
    "schemaVersion",
    "packageVersion",
    "assetId",
    "assetVersion",
    "craftProfileId",
    "producer.foundry",
    "producer.sidecarVersion",
    "producer.providerId",
    "producer.providerModel",
    "producer.identityModel",
    "contracts.coordinateContract",
    "contracts.assetRoleContract",
    "contracts.frameContract",
    "contracts.materialContract",
    "contracts.minimumSpriteFoundryImporter",
    "source.authoritySetSha256",
    "source.providerEvidencePackageSha256",
    "supersession.supersedesPackageContentDigest",
    "supersession.reasonCode",
    "contentIndex",
]

MANUFACTURING_AXES = {
    "runtimeTransforms": ["yaw", "position", "alpha", "approved_tint"],
    "bakedCandidateAxes": ["bank", "pitch", "damage_state", "destruction_sequence"],
    "independentLayers": ["hull", "thruster", "shadow", "emission", "recolour_mask"],
    "crossProductBakeProhibited": True,
    "ownership": {
        "bankPitchRendering": "sprite_foundry",
        "perFrameSocketProjection": "sprite_foundry",
        "runtimeSocketAcceptance": "gameplay_integration",
    },
}


def schema(name: str, title: str, required: list[str], properties: dict[str, Any], **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "$schema": DRAFT,
        "$id": f"https://skyforge.local/contracts/vmp/v1/{name}",
        "title": title,
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }
    result.update(extra)
    return result


def obj(required: list[str], properties: dict[str, Any], **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }
    result.update(extra)
    return result


def text(*, const: str | None = None, enum: list[str] | None = None, pattern: str | None = None, min_length: int = 1) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "string", "minLength": min_length}
    if const is not None:
        result["const"] = const
    if enum is not None:
        result["enum"] = enum
    if pattern is not None:
        result["pattern"] = pattern
    return result


def number(*, minimum: float | None = None, exclusive_minimum: float | None = None, const: float | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "number"}
    if minimum is not None:
        result["minimum"] = minimum
    if exclusive_minimum is not None:
        result["exclusiveMinimum"] = exclusive_minimum
    if const is not None:
        result["const"] = const
    return result


def integer(*, minimum: int = 0) -> dict[str, Any]:
    return {"type": "integer", "minimum": minimum}


def boolean(*, const: bool | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "boolean"}
    if const is not None:
        result["const"] = const
    return result


def vec(size: int) -> dict[str, Any]:
    return {
        "type": "array",
        "minItems": size,
        "maxItems": size,
        "items": {"type": "number"},
    }


def string_array(*, const: list[str] | None = None, unique: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "array", "items": {"type": "string"}, "uniqueItems": unique}
    if const is not None:
        result["const"] = const
    return result


def digest_profile_schema() -> dict[str, Any]:
    return schema(
        "vmp_content_digest_profile.schema.json",
        "SkyForge VMP v1 semantic digest profile",
        [
            "profileVersion",
            "canonicalization",
            "hashAlgorithm",
            "includedManifestFields",
            "unknownFieldPolicy",
            "optionalFieldEncoding",
        ],
        {
            "profileVersion": text(const="skyforge.vmp-content-digest.v1"),
            "canonicalization": text(const="RFC8785-JCS"),
            "hashAlgorithm": text(const="sha256"),
            "includedManifestFields": {"type": "array", "const": DIGEST_FIELDS},
            "unknownFieldPolicy": text(const="excluded"),
            "optionalFieldEncoding": obj(
                ["absent", "explicitNull"],
                {
                    "absent": text(const="omitted"),
                    "explicitNull": text(const="prohibited"),
                },
            ),
        },
    )


def manifest_schema() -> dict[str, Any]:
    content_entry = obj(
        ["sha256", "sizeBytes"],
        {"sha256": text(pattern=HEX64), "sizeBytes": integer(minimum=0)},
    )
    producer = obj(
        ["foundry", "sidecarVersion", "providerId", "identityModel"],
        {
            "foundry": text(const="mesh_foundry"),
            "sidecarVersion": text(pattern=SEMVER),
            "providerId": text(),
            "providerModel": text(),
            "identityModel": text(enum=["deterministic_reproducibility", "approved_artifact_immutability"]),
        },
    )
    approval = obj(
        ["state", "approvedForDistribution", "distributionTarget"],
        {
            "state": text(const="approved"),
            "approvedForDistribution": boolean(const=True),
            "distributionTarget": text(const="sprite_foundry"),
        },
    )
    contracts = obj(
        [
            "coordinateContract",
            "assetRoleContract",
            "frameContract",
            "materialContract",
            "minimumSpriteFoundryImporter",
        ],
        {
            "coordinateContract": text(const="skyforge.mesh-coordinate.v1"),
            "assetRoleContract": text(const="skyforge.asset-role.v1"),
            "frameContract": text(const="skyforge.render-frame-contract.v1"),
            "materialContract": text(const="skyforge.mesh-material.v1"),
            "minimumSpriteFoundryImporter": text(pattern=SEMVER),
        },
    )
    source = obj(
        ["authoritySetSha256"],
        {
            "authoritySetSha256": text(pattern=HEX64),
            "providerEvidencePackageSha256": text(pattern=HEX64),
        },
    )
    supersession = obj(
        ["supersedesPackageContentDigest", "reasonCode"],
        {
            "supersedesPackageContentDigest": text(pattern=HEX64),
            "reasonCode": text(enum=["producer_version_rebuild", "asset_revision", "provider_candidate_superseded"]),
        },
    )
    return schema(
        "validated_mesh_package.schema.json",
        "Validated Mesh Package manifest v1",
        [
            "schemaVersion",
            "packageId",
            "packageContentDigest",
            "packageVersion",
            "assetId",
            "assetVersion",
            "craftProfileId",
            "producer",
            "approval",
            "contracts",
            "source",
            "contentIndex",
            "digestProfile",
        ],
        {
            "schemaVersion": text(const="skyforge.validated-mesh-package.v1"),
            "packageId": text(pattern=PACKAGE_ID),
            "packageContentDigest": text(pattern=HEX64),
            "packageVersion": text(const="1.0.0"),
            "assetId": text(),
            "assetVersion": text(pattern=SEMVER),
            "craftProfileId": text(),
            "producer": producer,
            "approval": approval,
            "contracts": contracts,
            "source": source,
            "contentIndex": {
                "type": "object",
                "minProperties": 1,
                "propertyNames": {"type": "string", "pattern": r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))(?!.*\\).+$"},
                "additionalProperties": content_entry,
            },
            "digestProfile": digest_profile_schema(),
            "supersession": supersession,
        },
    )


def authority_manifest_schema() -> dict[str, Any]:
    authority = obj(
        [
            "role",
            "sourceSha256",
            "contentType",
            "embedded",
            "redistributionPermission",
            "embeddingDecision",
            "independentReverification",
            "generationProvenanceRef",
        ],
        {
            "role": text(enum=["silhouette_authority", "identity_authority"]),
            "sourceSha256": text(pattern=HEX64),
            "contentType": text(const="image/png"),
            "embedded": boolean(),
            "embeddedPath": text(pattern=r"^authorities/[A-Za-z0-9._-]+\.png$"),
            "redistributionPermission": text(enum=["permitted", "prohibited", "unknown"]),
            "embeddingDecision": text(enum=["embedded", "hash_only_due_to_terms", "absent_not_authored"]),
            "independentReverification": text(enum=["full", "unavailable_due_to_terms"]),
            "generationProvenanceRef": text(),
        },
        allOf=[
            {
                "if": {"properties": {"embedded": {"const": True}}, "required": ["embedded"]},
                "then": {
                    "required": ["embeddedPath"],
                    "properties": {
                        "redistributionPermission": {"const": "permitted"},
                        "embeddingDecision": {"const": "embedded"},
                        "independentReverification": {"const": "full"},
                    },
                },
            },
            {
                "if": {
                    "properties": {"redistributionPermission": {"enum": ["unknown", "prohibited"]}},
                    "required": ["redistributionPermission"],
                },
                "then": {
                    "properties": {
                        "embedded": {"const": False},
                        "embeddingDecision": {"const": "hash_only_due_to_terms"},
                        "independentReverification": {"const": "unavailable_due_to_terms"},
                    },
                    "not": {"required": ["embeddedPath"]},
                },
            },
            {
                "if": {"properties": {"embedded": {"const": False}}, "required": ["embedded"]},
                "then": {"not": {"required": ["embeddedPath"]}},
            },
        ],
    )
    return schema(
        "authority_manifest.schema.json",
        "Authority provenance and licence-conditional embedding",
        ["schemaVersion", "authoritySetSha256", "authorities"],
        {
            "schemaVersion": text(const="skyforge.authority-manifest.v1"),
            "authoritySetSha256": text(pattern=HEX64),
            "authorities": {"type": "array", "minItems": 1, "items": authority},
        },
    )


def build_schemas() -> dict[str, dict[str, Any]]:
    measured_value = obj(
        ["name", "value"],
        {
            "name": text(),
            "value": {"oneOf": [{"type": "number"}, {"type": "integer"}, {"type": "boolean"}, {"type": "string"}]},
            "unit": text(),
        },
    )
    gate = obj(
        ["name", "passed", "measuredValue", "thresholdOperator", "thresholdValue"],
        {
            "name": text(),
            "passed": boolean(),
            "measuredValue": {"oneOf": [{"type": "number"}, {"type": "integer"}, {"type": "boolean"}, {"type": "string"}]},
            "thresholdOperator": text(enum=[">=", "<=", "==", "informational"]),
            "thresholdValue": {"oneOf": [{"type": "number"}, {"type": "integer"}, {"type": "boolean"}, {"type": "string"}]},
            "failureReason": text(),
        },
    )
    schemas: dict[str, dict[str, Any]] = {}
    schemas["vmp_content_digest_profile.schema.json"] = digest_profile_schema()
    schemas["validated_mesh_package.schema.json"] = manifest_schema()
    schemas["asset_v3.schema.json"] = schema(
        "asset_v3.schema.json",
        "SkyForge mesh asset metadata v3",
        ["schemaVersion", "assetId", "assetVersion", "craftProfileId", "assetRole", "provider", "geometry", "approval", "anchorState"],
        {
            "schemaVersion": text(const="skyforge.asset.v3"),
            "assetId": text(),
            "assetVersion": text(pattern=SEMVER),
            "craftProfileId": text(),
            "assetRole": text(const="air_moving"),
            "provider": obj(["id", "identityModel"], {"id": text(), "identityModel": text(enum=["deterministic_reproducibility", "approved_artifact_immutability"])}),
            "geometry": obj(["normalizedGlb"], {"normalizedGlb": text(const="mesh/normalized.glb")}),
            "approval": obj(["state", "approvedForDistribution"], {"state": text(const="approved"), "approvedForDistribution": boolean(const=True)}),
            "collisionHint": obj(
                ["authoritative", "consumerMustIgnoreForRuntime", "sourceSchema"],
                {
                    "authoritative": boolean(const=False),
                    "consumerMustIgnoreForRuntime": boolean(const=True),
                    "sourceSchema": text(),
                    "description": text(),
                },
            ),
            "anchorState": text(enum=["authored", "not_authored", "not_applicable"]),
        },
    )
    schemas["semantic_identity.schema.json"] = schema(
        "semantic_identity.schema.json",
        "Semantic mesh identity contract",
        ["schemaVersion", "identityModel", "reference", "localDeterministicContract", "blenderSilhouetteIoUMin", "measuredResults"],
        {
            "schemaVersion": text(const="skyforge.mesh-semantic-identity.v1"),
            "identityModel": text(enum=["deterministic_reproducibility", "approved_artifact_immutability"]),
            "reference": obj([], {"localReferenceGlbSha256": text(pattern=HEX64), "approvedArtifactGlbSha256": text(pattern=HEX64)}, minProperties=1, maxProperties=1),
            "localDeterministicContract": obj(
                ["exactIndices", "exactXZ", "exactUV", "exactDecodedTexturePixels", "yMaxAbsTolerance", "yRmsTolerance", "rawGlbShaGating", "rawGlbShaInformational"],
                {
                    "exactIndices": boolean(const=True),
                    "exactXZ": boolean(const=True),
                    "exactUV": boolean(const=True),
                    "exactDecodedTexturePixels": boolean(const=True),
                    "yMaxAbsTolerance": number(const=0.00001),
                    "yRmsTolerance": number(const=0.000001),
                    "rawGlbShaGating": boolean(const=False),
                    "rawGlbShaInformational": boolean(const=True),
                },
            ),
            "blenderSilhouetteIoUMin": number(const=0.94),
            "measuredResults": {"type": "array", "minItems": 1, "items": measured_value},
        },
    )
    component = obj(
        ["componentId", "primitiveOrNodeRefs", "vertexCount", "triangleCount", "bounds", "volumeFraction", "watertight", "eulerNumber", "genus", "boundaryEdges", "nonManifoldEdges"],
        {
            "componentId": text(),
            "primitiveOrNodeRefs": string_array(),
            "vertexCount": integer(minimum=1),
            "triangleCount": integer(minimum=1),
            "bounds": obj(["min", "max"], {"min": vec(3), "max": vec(3)}),
            "volumeFraction": number(minimum=0),
            "watertight": boolean(),
            "eulerNumber": integer(minimum=-1000000),
            "genus": integer(minimum=0),
            "boundaryEdges": integer(minimum=0),
            "nonManifoldEdges": integer(minimum=0),
        },
    )
    schemas["component_manifest.schema.json"] = schema(
        "component_manifest.schema.json",
        "Mesh component facts",
        ["schemaVersion", "componentCount", "componentPolicy", "components"],
        {
            "schemaVersion": text(const="skyforge.mesh-components.v1"),
            "componentCount": integer(minimum=1),
            "componentPolicy": text(const="single_component_required"),
            "components": {"type": "array", "minItems": 1, "maxItems": 1, "items": component},
        },
    )
    schemas["bounds_and_scale.schema.json"] = schema(
        "bounds_and_scale.schema.json",
        "Normalized bounds, scale, and gameplay preview mapping",
        ["schemaVersion", "coordinateContract", "units", "bounds", "canonicalScale", "gameplayPreviewMapping", "pivotFrame"],
        {
            "schemaVersion": text(const="skyforge.mesh-bounds-scale.v1"),
            "coordinateContract": text(const="skyforge.mesh-coordinate.v1"),
            "units": text(const="skyforge_world_units"),
            "bounds": obj(["min", "max", "extents"], {"min": vec(3), "max": vec(3), "extents": vec(3)}),
            "canonicalScale": obj(
                ["longestPlanformExtentWorld", "heightWorld", "heightToPlanformRatio"],
                {
                    "longestPlanformExtentWorld": number(exclusive_minimum=0),
                    "heightWorld": number(exclusive_minimum=0),
                    "heightToPlanformRatio": number(exclusive_minimum=0),
                },
            ),
            "gameplayPreviewMapping": obj(
                ["referenceImage", "canvasPixels", "worldUnitsPerPixel", "fittedPlanformPixels", "transparentMarginPixels"],
                {
                    "referenceImage": text(const="previews/gameplay_scale_96.png"),
                    "canvasPixels": {"type": "array", "const": [96, 96]},
                    "worldUnitsPerPixel": number(exclusive_minimum=0),
                    "fittedPlanformPixels": integer(minimum=1),
                    "transparentMarginPixels": integer(minimum=0),
                },
            ),
            "pivotFrame": text(const="normalized_mesh_frame"),
        },
    )
    schemas["authority_manifest.schema.json"] = authority_manifest_schema()
    schemas["asset_role.schema.json"] = schema(
        "asset_role.schema.json",
        "Air-moving asset role contract",
        ["schemaVersion", "preset", "capabilities"],
        {
            "schemaVersion": text(const="skyforge.asset-role.v1"),
            "preset": text(const="air_moving"),
            "capabilities": obj(
                ["timelineMovement", "airborne", "terrainPlacement", "directionalGroundSet"],
                {
                    "timelineMovement": boolean(const=True),
                    "airborne": boolean(const=True),
                    "terrainPlacement": boolean(const=False),
                    "directionalGroundSet": boolean(const=False),
                },
            ),
        },
    )
    schemas["manufacturing_axes.schema.json"] = schema(
        "manufacturing_axes.schema.json",
        "SF-AM-0001 manufacturing-axis ownership enumeration",
        ["schemaVersion", *MANUFACTURING_AXES.keys()],
        {
            "schemaVersion": text(const="skyforge.manufacturing-axes.v1"),
            "runtimeTransforms": {"type": "array", "const": MANUFACTURING_AXES["runtimeTransforms"]},
            "bakedCandidateAxes": {"type": "array", "const": MANUFACTURING_AXES["bakedCandidateAxes"]},
            "independentLayers": {"type": "array", "const": MANUFACTURING_AXES["independentLayers"]},
            "crossProductBakeProhibited": boolean(const=True),
            "ownership": obj(
                list(MANUFACTURING_AXES["ownership"]),
                {key: text(const=value) for key, value in MANUFACTURING_AXES["ownership"].items()},
            ),
        },
    )
    pivot = obj(
        ["position", "orientationQuaternion", "frame", "source", "approvalState"],
        {
            "position": vec(3),
            "orientationQuaternion": vec(4),
            "frame": text(const="normalized_mesh_frame"),
            "source": text(enum=["deterministic", "human_approved", "provider_candidate"]),
            "approvalState": text(const="approved"),
        },
    )
    schemas["pivot_contract.schema.json"] = schema(
        "pivot_contract.schema.json",
        "Root and authored-part pivots",
        ["schemaVersion", "rootPivot", "partPivots"],
        {"schemaVersion": text(const="skyforge.pivot-contract.v1"), "rootPivot": pivot, "partPivots": {"type": "array", "items": pivot}},
    )
    schemas["part_contract.schema.json"] = schema(
        "part_contract.schema.json",
        "Optional semantic or candidate mesh parts",
        ["schemaVersion", "parts"],
        {
            "schemaVersion": text(const="skyforge.part-contract.v1"),
            "parts": {
                "type": "array",
                "minItems": 1,
                "items": obj(
                    ["partId", "glbNodeOrPrimitiveRefs", "bounds", "volumeFraction", "parentPartId", "classificationSource", "approvalState", "allowedDownstreamUse"],
                    {
                        "partId": text(),
                        "glbNodeOrPrimitiveRefs": string_array(),
                        "bounds": obj(["min", "max"], {"min": vec(3), "max": vec(3)}),
                        "volumeFraction": number(minimum=0),
                        "parentPartId": text(),
                        "classificationSource": text(enum=["deterministic", "human_approved", "provider_candidate"]),
                        "approvalState": text(enum=["approved", "candidate", "rejected"]),
                        "allowedDownstreamUse": string_array(),
                    },
                ),
            },
        },
    )
    schemas["socket_candidates.schema.json"] = schema(
        "socket_candidates.schema.json",
        "Optional 3D socket candidates owned by Mesh Foundry",
        ["schemaVersion", "coordinateFrame", "sockets"],
        {
            "schemaVersion": text(const="skyforge.socket-candidates.v1"),
            "coordinateFrame": text(const="normalized_mesh_frame"),
            "sockets": {
                "type": "array",
                "minItems": 1,
                "items": obj(
                    ["socketId", "position", "orientationQuaternion", "radiusOrExtent", "semanticType", "source", "confidence", "approvalState"],
                    {
                        "socketId": text(),
                        "position": vec(3),
                        "orientationQuaternion": vec(4),
                        "radiusOrExtent": vec(3),
                        "semanticType": text(),
                        "source": text(enum=["deterministic", "human_approved", "provider_candidate"]),
                        "confidence": number(minimum=0),
                        "approvalState": text(enum=["approved", "candidate", "rejected"]),
                    },
                ),
            },
        },
    )
    schemas["frame_contract.schema.json"] = schema(
        "frame_contract.schema.json",
        "Calibrated Blender frame contract and extension envelope",
        ["schemaVersion", "coordinateFrame", "canonicalCamera", "headroom", "calibration", "calibrationEnvelope", "renderState", "silhouetteProtocol", "heightToPlanformRatio", "consumerDeviationPolicy"],
        {
            "schemaVersion": text(const="skyforge.render-frame-contract.v1"),
            "coordinateFrame": obj(["forwardAxis", "upAxis", "rightAxis"], {"forwardAxis": text(const="+Y"), "upAxis": text(const="+Z"), "rightAxis": text(const="+X")}),
            "canonicalCamera": obj(
                ["projection", "pitchDegrees", "bankDegrees", "yawDegrees", "canonicalOrthoScale", "requiredReviewOrthoScale", "requiredSilhouetteOrthoScale"],
                {
                    "projection": text(const="orthographic"),
                    "pitchDegrees": number(const=20),
                    "bankDegrees": number(const=0),
                    "yawDegrees": number(const=0),
                    "canonicalOrthoScale": number(exclusive_minimum=0),
                    "requiredReviewOrthoScale": number(exclusive_minimum=0),
                    "requiredSilhouetteOrthoScale": number(exclusive_minimum=0),
                },
            ),
            "headroom": obj(["worldUnits", "fractionOfPlanform"], {"worldUnits": number(minimum=0), "fractionOfPlanform": number(minimum=0)}),
            "calibration": obj(
                ["method", "profileDigest", "pitchSamplesDegrees", "bankSamplesDegrees", "referencePoseMap"],
                {
                    "method": text(),
                    "profileDigest": text(pattern=HEX64),
                    "pitchSamplesDegrees": {"type": "array", "const": [0, 20, 36]},
                    "bankSamplesDegrees": {"type": "array", "const": [-18, 0, 18]},
                    "referencePoseMap": obj(["bank_left", "neutral", "bank_right"], {"bank_left": number(const=-18), "neutral": number(const=0), "bank_right": number(const=18)}),
                },
            ),
            "calibrationEnvelope": obj(
                ["maximumHeightToPlanformRatio", "heightEnvelopeBindingPitchDegrees", "measuredMaximumRequiredOrthoScale", "measuredRequiredMargin", "chosenMargin", "runtimeEffectsEnabled"],
                {
                    "maximumHeightToPlanformRatio": number(exclusive_minimum=0),
                    "heightEnvelopeBindingPitchDegrees": number(minimum=0),
                    "measuredMaximumRequiredOrthoScale": number(exclusive_minimum=0),
                    "measuredRequiredMargin": number(minimum=0),
                    "chosenMargin": number(minimum=0),
                    "runtimeEffectsEnabled": boolean(const=False),
                },
            ),
            "renderState": obj(
                ["engine", "resolution", "samples", "viewTransform", "exposure", "gamma", "transparentFilm"],
                {
                    "engine": text(const="BLENDER_EEVEE"),
                    "resolution": {"type": "array", "const": [384, 384]},
                    "samples": integer(minimum=1),
                    "viewTransform": text(const="Standard"),
                    "exposure": number(const=0),
                    "gamma": number(const=1),
                    "transparentFilm": boolean(const=True),
                },
            ),
            "silhouetteProtocol": obj(
                ["fitCanvasPixels", "fitMarginPixels", "resample", "alphaThreshold", "maskPolarity"],
                {
                    "fitCanvasPixels": integer(minimum=1),
                    "fitMarginPixels": integer(minimum=0),
                    "resample": text(const="NEAREST"),
                    "alphaThreshold": integer(minimum=0),
                    "maskPolarity": text(const="foreground_true"),
                },
            ),
            "heightToPlanformRatio": number(exclusive_minimum=0),
            "consumerDeviationPolicy": obj(
                ["spriteFoundryMayExtendBankPitchLadder", "extensionWithinCalibrationEnvelopeOnly", "newCalibrationRequiredOutsideEnvelope", "deviationMustBeRecorded"],
                {
                    "spriteFoundryMayExtendBankPitchLadder": boolean(const=True),
                    "extensionWithinCalibrationEnvelopeOnly": boolean(const=True),
                    "newCalibrationRequiredOutsideEnvelope": boolean(const=True),
                    "deviationMustBeRecorded": boolean(const=True),
                },
            ),
        },
    )
    texture = obj(["path", "contentType", "sha256", "decodedPixelSha256"], {"path": text(pattern=r"^materials/textures/"), "contentType": text(enum=["image/png"]), "sha256": text(pattern=HEX64), "decodedPixelSha256": text(pattern=HEX64)})
    schemas["material_contract.schema.json"] = schema(
        "material_contract.schema.json",
        "Mesh material and lighting-state contract",
        ["schemaVersion", "baseColor", "alphaPolicy", "externalReferences", "providerProcessing", "semanticRegions", "textures"],
        {
            "schemaVersion": text(const="skyforge.mesh-material.v1"),
            "baseColor": obj(
                ["source", "colorSpace", "lightingState"],
                {
                    "source": text(enum=["authority_projection", "provider_texture", "ai_retexture", "procedural"]),
                    "colorSpace": text(const="sRGB"),
                    "lightingState": text(enum=["unlit_albedo", "baked_lighting", "mixed", "unknown"]),
                    "decodedPixelSha256": text(pattern=HEX64),
                },
            ),
            "alphaPolicy": text(enum=["opaque", "binary_mask", "straight_alpha"]),
            "externalReferences": boolean(const=False),
            "providerProcessing": obj(
                ["imageEnhancementApplied", "removeLightingApplied", "aiTexturingApplied"],
                {
                    "imageEnhancementApplied": {"oneOf": [boolean(), text(enum=["not_supported", "unknown"])]},
                    "removeLightingApplied": {"oneOf": [boolean(), text(enum=["not_applicable", "unknown"])]},
                    "aiTexturingApplied": boolean(const=False),
                },
            ),
            "semanticRegions": {"type": "array", "items": obj(["regionId", "materialSlot"], {"regionId": text(), "materialSlot": text()})},
            "textures": {"type": "array", "items": texture},
        },
    )
    schemas["source_chain.schema.json"] = schema(
        "source_chain.schema.json",
        "Immutable concept, authority, generator/provider, normalization, and approval chain",
        ["schemaVersion", "authoritySetSha256", "lineage", "normalizationVersion", "approvalEvents"],
        {
            "schemaVersion": text(const="skyforge.source-chain.v1"),
            "authoritySetSha256": text(pattern=HEX64),
            "lineage": {"type": "array", "minItems": 1, "items": obj(["stage", "artifactSha256", "producerId"], {"stage": text(enum=["concept", "authority", "mesh_candidate", "normalized_mesh"]), "artifactSha256": text(pattern=HEX64), "producerId": text(), "providerModel": text()})},
            "normalizationVersion": text(pattern=SEMVER),
            "approvalEvents": {"type": "array", "minItems": 1, "items": obj(["eventId", "state", "artifactSha256", "recordedAt"], {"eventId": text(), "state": text(enum=["approved", "rejected", "superseded"]), "artifactSha256": text(pattern=HEX64), "recordedAt": {"type": "string", "format": "date-time"}})},
            "priorSupersededPackageDigests": {"type": "array", "items": text(pattern=HEX64), "uniqueItems": True},
        },
    )
    terms_snapshot = obj(["source", "versionOrDate", "recordedAt"], {"source": text(), "versionOrDate": text(), "recordedAt": {"type": "string", "format": "date-time"}})
    schemas["licensing_and_terms.schema.json"] = schema(
        "licensing_and_terms.schema.json",
        "Commercial-use and redistribution assertions",
        ["schemaVersion", "assetCommercialUseAsserted", "termsSnapshots", "authorityRedistribution", "provider"],
        {
            "schemaVersion": text(const="skyforge.licensing-terms.v1"),
            "assetCommercialUseAsserted": boolean(),
            "termsSnapshots": {"type": "array", "minItems": 1, "items": terms_snapshot},
            "authorityRedistribution": obj(["permitted", "basis"], {"permitted": {"oneOf": [boolean(), text(const="unknown")]}, "basis": text()}),
            "provider": obj([], {"accountTier": text(), "modelId": text(), "modelAvailabilityRisk": text(), "pricingVerifiedAt": {"type": "string", "format": "date-time"}, "pricingSource": text()}),
        },
    )
    schemas["validation_report.schema.json"] = schema(
        "validation_report.schema.json",
        "Measured producer validation report without downstream readiness claim",
        ["schemaVersion", "validationClass", "validatorVersion", "sourceGlbSha256", "executedAt", "measuredValues", "gates", "passed"],
        {
            "schemaVersion": text(const="skyforge.validation-report.v1"),
            "validationClass": text(enum=["geometry", "independent_reload", "blender"]),
            "validatorVersion": text(pattern=SEMVER),
            "sourceGlbSha256": text(pattern=HEX64),
            "executedAt": {"type": "string", "format": "date-time"},
            "measuredValues": {"type": "array", "minItems": 1, "items": measured_value},
            "gates": {"type": "array", "minItems": 1, "items": gate},
            "passed": boolean(),
            "failureReasons": string_array(),
        },
    )
    schemas["structural_measurements.schema.json"] = schema(
        "structural_measurements.schema.json",
        "Optional factual structural measurements without eligibility decisions",
        ["schemaVersion", "sourceGlbSha256", "measurements", "topologyLimitations"],
        {
            "schemaVersion": text(const="skyforge.structural-measurements.v1"),
            "sourceGlbSha256": text(pattern=HEX64),
            "measurements": {"type": "array", "items": measured_value},
            "topologyLimitations": string_array(),
        },
    )
    limitation_item = obj(
        ["code", "severity", "description", "affectedConsumers", "evidenceRefs"],
        {
            "code": text(pattern=r"^[a-z0-9_]+$"),
            "severity": text(enum=["info", "warning", "blocking_downstream_feature"]),
            "description": text(),
            "affectedConsumers": string_array(),
            "workaround": text(),
            "evidenceRefs": string_array(),
            "excludedRuntimeEffects": string_array(),
        },
    )
    schemas["known_limitations.schema.json"] = schema(
        "known_limitations.schema.json",
        "Known limitations including calibrated-frame runtime-effect exclusions",
        ["schemaVersion", "limitations"],
        {
            "schemaVersion": text(const="skyforge.known-limitations.v1"),
            "limitations": {
                "type": "array",
                "minItems": 1,
                "items": limitation_item,
                "contains": {
                    "properties": {
                        "code": {"const": "calibrated_frame_excludes_runtime_effects"},
                        "excludedRuntimeEffects": {"const": ["thrusters", "muzzle_flashes", "shadows", "debris", "other_sprite_foundry_effects"]},
                    },
                    "required": ["code", "excludedRuntimeEffects"],
                },
                "minContains": 1,
            },
        },
    )
    schemas["provider_capabilities.schema.json"] = schema(
        "provider_capabilities.schema.json",
        "Provider capability and authority-input preservation claims",
        ["schemaVersion", "providerId", "modelId", "operations", "authorityInputPreservation", "geometryDeterminism", "costUnit", "captureRequiredBeforeReview", "approvalIdentityModel", "verifiedAt", "sourceUrls", "modelAvailabilityRisk"],
        {
            "schemaVersion": text(const="skyforge.mesh-provider-capabilities.v1"),
            "providerId": text(),
            "modelId": text(),
            "operations": string_array(),
            "authorityInputPreservation": obj(["status", "controlField", "claimAllowed"], {"status": text(enum=["verified_controlled", "unverifiable", "not_applicable"]), "controlField": text(), "claimAllowed": boolean()}),
            "geometryDeterminism": obj(["status"], {"status": text(enum=["deterministic", "nondeterministic", "unknown"])}),
            "costUnit": text(enum=["credits", "usd", "none"]),
            "captureRequiredBeforeReview": boolean(const=True),
            "approvalIdentityModel": text(enum=["deterministic_reproducibility", "approved_artifact_immutability"]),
            "verifiedAt": {"type": "string", "format": "date-time"},
            "sourceUrls": string_array(),
            "modelAvailabilityRisk": text(),
        },
    )
    option = obj(["name", "valueCanonicalSha256"], {"name": text(), "valueCanonicalSha256": text(pattern=HEX64)})
    schemas["mesh_build_request.schema.json"] = schema(
        "mesh_build_request.schema.json",
        "Provider-neutral mesh build request",
        ["schemaVersion", "requestId", "assetId", "assetVersion", "assetRole", "authoritySetSha256", "operationClass", "providerId", "estimatedCost", "outputContract", "providerOptions", "automaticRetry"],
        {
            "schemaVersion": text(const="skyforge.mesh-build-request.v1"),
            "requestId": text(),
            "assetId": text(),
            "assetVersion": text(pattern=SEMVER),
            "assetRole": text(const="air_moving"),
            "authoritySetSha256": text(pattern=HEX64),
            "operationClass": text(const="authority_to_mesh"),
            "providerId": text(enum=["local_deterministic", "mock", "meshy_test_mode"]),
            "estimatedCost": obj(["unit", "amount"], {"unit": text(enum=["credits", "usd", "none"]), "amount": number(minimum=0)}),
            "outputContract": text(const="normalized_glb_and_vmp"),
            "providerOptions": {"type": "array", "items": option},
            "automaticRetry": boolean(const=False),
        },
    )
    recovery = obj(
        ["requestDigest", "providerId", "providerModel", "resolvedProviderOptionsDigest", "authoritySetSha256", "accountIdentityDigest", "dispatchWindowStart", "dispatchWindowEnd", "expectedCost"],
        {
            "requestDigest": text(pattern=HEX64),
            "providerId": text(),
            "providerModel": text(),
            "resolvedProviderOptionsDigest": text(pattern=HEX64),
            "authoritySetSha256": text(pattern=HEX64),
            "accountIdentityDigest": text(pattern=HEX64),
            "dispatchWindowStart": {"type": "string", "format": "date-time"},
            "dispatchWindowEnd": {"type": "string", "format": "date-time"},
            "expectedCost": obj(["unit", "amount"], {"unit": text(enum=["credits", "usd", "none"]), "amount": number(minimum=0)}),
        },
    )
    schemas["provider_task_record.schema.json"] = schema(
        "provider_task_record.schema.json",
        "Provider task state with MBS-136 recovery correlation",
        ["schemaVersion", "reservationId", "requestDigest", "state", "sequence", "timestamps", "resolvedRequestDigest", "evidenceClass", "recoveryCorrelation", "correspondenceStatus"],
        {
            "schemaVersion": text(const="skyforge.provider-task-record.v1"),
            "reservationId": text(),
            "requestDigest": text(pattern=HEX64),
            "providerTaskId": text(),
            "state": text(enum=["intent_persisted", "reserved", "submitted", "observing", "completed", "failed", "reconciled", "released", "unresolved", "expired_uncaptured"]),
            "sequence": integer(minimum=1),
            "timestamps": obj(["createdAt", "updatedAt"], {"createdAt": {"type": "string", "format": "date-time"}, "updatedAt": {"type": "string", "format": "date-time"}}),
            "resolvedRequestDigest": text(pattern=HEX64),
            "evidenceClass": text(enum=["local_deterministic", "mock_provider", "transport_lifecycle_only", "production_candidate"]),
            "recoveryCorrelation": recovery,
            "correspondenceStatus": text(enum=["known_task_id", "unique_correlated_match", "zero_matches_unresolved", "multiple_matches_unresolved", "not_required_local"]),
        },
    )
    schemas["provider_spend_reservation.schema.json"] = schema(
        "provider_spend_reservation.schema.json",
        "Write-ahead provider spend reservation",
        ["schemaVersion", "sequence", "reservationId", "requestDigest", "providerId", "estimatedCost", "state", "createdAt", "updatedAt", "process"],
        {
            "schemaVersion": text(const="skyforge.provider-spend-reservation.v1"),
            "sequence": integer(minimum=1),
            "reservationId": text(),
            "requestDigest": text(pattern=HEX64),
            "providerId": text(),
            "estimatedCost": obj(["unit", "amount"], {"unit": text(enum=["credits", "usd", "none"]), "amount": number(minimum=0)}),
            "state": text(enum=["intent_persisted", "reserved", "submitted", "reconciled", "released", "unresolved"]),
            "createdAt": {"type": "string", "format": "date-time"},
            "updatedAt": {"type": "string", "format": "date-time"},
            "providerTaskId": text(),
            "process": obj(["pid", "heartbeatAt"], {"pid": integer(minimum=1), "heartbeatAt": {"type": "string", "format": "date-time"}}),
        },
    )
    schemas["provider_evidence_package.schema.json"] = schema(
        "provider_evidence_package.schema.json",
        "Separate untrusted provider evidence package metadata",
        ["schemaVersion", "providerId", "modelId", "evidenceClass", "promotionPermitted", "resolvedRequestDigest", "taskSnapshots", "capturedArtifacts", "reservationRecordSha256", "sanitization", "capturedAt"],
        {
            "schemaVersion": text(const="skyforge.provider-evidence-package.v1"),
            "providerId": text(),
            "modelId": text(),
            "evidenceClass": text(enum=["transport_lifecycle_only", "exploratory_provider_candidate", "authority_bearing_candidate"]),
            "promotionPermitted": boolean(),
            "resolvedRequestDigest": text(pattern=HEX64),
            "taskSnapshots": {"type": "array", "minItems": 1, "items": obj(["phase", "state", "capturedAt", "sanitizedObjectSha256"], {"phase": text(enum=["submit", "progress", "terminal"]), "state": text(), "capturedAt": {"type": "string", "format": "date-time"}, "sanitizedObjectSha256": text(pattern=HEX64)})},
            "capturedArtifacts": {"type": "array", "items": obj(["path", "sha256", "contentType", "capturedAt"], {"path": text(), "sha256": text(pattern=HEX64), "contentType": text(), "capturedAt": {"type": "string", "format": "date-time"}})},
            "reservationRecordSha256": text(pattern=HEX64),
            "sanitization": obj(["secretsRemoved", "signedUrlsRemoved", "localPathsRemoved"], {"secretsRemoved": boolean(const=True), "signedUrlsRemoved": boolean(const=True), "localPathsRemoved": boolean(const=True)}),
            "expiresAt": {"type": "string", "format": "date-time"},
            "capturedAt": {"type": "string", "format": "date-time"},
        },
        allOf=[
            {
                "if": {"properties": {"evidenceClass": {"const": "transport_lifecycle_only"}}, "required": ["evidenceClass"]},
                "then": {"properties": {"promotionPermitted": {"const": False}}},
            }
        ],
    )
    schemas["sprite_foundry_import_receipt.schema.json"] = schema(
        "sprite_foundry_import_receipt.schema.json",
        "Authoritative consumer import receipt",
        ["schemaVersion", "receiptId", "sourceArchiveSha256", "sourcePackageContentDigest", "sourcePackageId", "importerVersion", "accepted", "schemasAccepted", "authorityReverification", "manufacturingAxesVerified", "collisionHintsIgnoredForRuntime", "createdAt"],
        {
            "schemaVersion": text(const="skyforge.sprite-foundry-import-receipt.v1"),
            "receiptId": text(),
            "sourceArchiveSha256": text(pattern=HEX64),
            "sourcePackageContentDigest": text(pattern=HEX64),
            "sourcePackageId": text(pattern=PACKAGE_ID),
            "importerVersion": text(pattern=SEMVER),
            "accepted": boolean(),
            "schemasAccepted": string_array(),
            "authorityReverification": text(enum=["full", "unavailable_due_to_terms"]),
            "manufacturingAxesVerified": boolean(),
            "collisionHintsIgnoredForRuntime": boolean(const=True),
            "diagnostics": string_array(),
            "createdAt": {"type": "string", "format": "date-time"},
        },
    )
    return schemas


def digest_profile_value() -> dict[str, Any]:
    return {
        "profileVersion": "skyforge.vmp-content-digest.v1",
        "canonicalization": "RFC8785-JCS",
        "hashAlgorithm": "sha256",
        "includedManifestFields": DIGEST_FIELDS,
        "unknownFieldPolicy": "excluded",
        "optionalFieldEncoding": {"absent": "omitted", "explicitNull": "prohibited"},
    }


def base_manifest() -> dict[str, Any]:
    digest = "a" * 64
    return {
        "schemaVersion": "skyforge.validated-mesh-package.v1",
        "packageId": f"sfmeshpack:{digest}",
        "packageContentDigest": digest,
        "packageVersion": "1.0.0",
        "assetId": "approved_gunship",
        "assetVersion": "1.0.0",
        "craftProfileId": "enemy_gunship",
        "producer": {
            "foundry": "mesh_foundry",
            "sidecarVersion": "0.7.1",
            "providerId": "local_deterministic",
            "identityModel": "deterministic_reproducibility",
        },
        "approval": {"state": "approved", "approvedForDistribution": True, "distributionTarget": "sprite_foundry"},
        "contracts": {
            "coordinateContract": "skyforge.mesh-coordinate.v1",
            "assetRoleContract": "skyforge.asset-role.v1",
            "frameContract": "skyforge.render-frame-contract.v1",
            "materialContract": "skyforge.mesh-material.v1",
            "minimumSpriteFoundryImporter": "0.1.0",
        },
        "source": {"authoritySetSha256": "b" * 64},
        "contentIndex": {"asset.json": {"sha256": "c" * 64, "sizeBytes": 123}},
        "digestProfile": digest_profile_value(),
    }


def build_examples() -> dict[str, Any]:
    embedded = {
        "schemaVersion": "skyforge.authority-manifest.v1",
        "authoritySetSha256": "1" * 64,
        "authorities": [
            {
                "role": "silhouette_authority",
                "sourceSha256": "2" * 64,
                "contentType": "image/png",
                "embedded": True,
                "embeddedPath": "authorities/silhouette_authority.png",
                "redistributionPermission": "permitted",
                "embeddingDecision": "embedded",
                "independentReverification": "full",
                "generationProvenanceRef": "provenance/source_chain.json#authority-1",
            }
        ],
    }
    hash_only = json.loads(json.dumps(embedded))
    hash_authority = hash_only["authorities"][0]
    hash_authority.pop("embeddedPath")
    hash_authority.update(
        {
            "embedded": False,
            "redistributionPermission": "unknown",
            "embeddingDecision": "hash_only_due_to_terms",
            "independentReverification": "unavailable_due_to_terms",
        }
    )
    invalid_embedded = json.loads(json.dumps(hash_only))
    invalid_embedded["authorities"][0]["embedded"] = True
    invalid_embedded["authorities"][0]["embeddedPath"] = "authorities/silhouette_authority.png"

    absent = base_manifest()
    present = base_manifest()
    present["producer"]["providerModel"] = "local-authority-field-v0.6"
    present["source"]["providerEvidencePackageSha256"] = "d" * 64
    present["supersession"] = {
        "supersedesPackageContentDigest": "e" * 64,
        "reasonCode": "producer_version_rebuild",
    }
    explicit_null = base_manifest()
    explicit_null["producer"]["providerModel"] = None

    frame = {
        "schemaVersion": "skyforge.render-frame-contract.v1",
        "coordinateFrame": {"forwardAxis": "+Y", "upAxis": "+Z", "rightAxis": "+X"},
        "canonicalCamera": {
            "projection": "orthographic",
            "pitchDegrees": 20,
            "bankDegrees": 0,
            "yawDegrees": 0,
            "canonicalOrthoScale": 4.2,
            "requiredReviewOrthoScale": 4.4,
            "requiredSilhouetteOrthoScale": 4.3,
        },
        "headroom": {"worldUnits": 0.3, "fractionOfPlanform": 0.075},
        "calibration": {
            "method": "v0.6.0 canonical_frame_calibration",
            "profileDigest": "f" * 64,
            "pitchSamplesDegrees": [0, 20, 36],
            "bankSamplesDegrees": [-18, 0, 18],
            "referencePoseMap": {"bank_left": -18, "neutral": 0, "bank_right": 18},
        },
        "calibrationEnvelope": {
            "maximumHeightToPlanformRatio": 0.35,
            "heightEnvelopeBindingPitchDegrees": 36,
            "measuredMaximumRequiredOrthoScale": 4.35,
            "measuredRequiredMargin": 0.25,
            "chosenMargin": 0.3,
            "runtimeEffectsEnabled": False,
        },
        "renderState": {
            "engine": "BLENDER_EEVEE",
            "resolution": [384, 384],
            "samples": 64,
            "viewTransform": "Standard",
            "exposure": 0,
            "gamma": 1,
            "transparentFilm": True,
        },
        "silhouetteProtocol": {
            "fitCanvasPixels": 512,
            "fitMarginPixels": 28,
            "resample": "NEAREST",
            "alphaThreshold": 128,
            "maskPolarity": "foreground_true",
        },
        "heightToPlanformRatio": 0.3,
        "consumerDeviationPolicy": {
            "spriteFoundryMayExtendBankPitchLadder": True,
            "extensionWithinCalibrationEnvelopeOnly": True,
            "newCalibrationRequiredOutsideEnvelope": True,
            "deviationMustBeRecorded": True,
        },
    }
    limitations = {
        "schemaVersion": "skyforge.known-limitations.v1",
        "limitations": [
            {
                "code": "calibrated_frame_excludes_runtime_effects",
                "severity": "warning",
                "description": "Calibrated hull headroom excludes composited runtime and Sprite Foundry effects.",
                "affectedConsumers": ["sprite_foundry"],
                "evidenceRefs": ["render/frame_contract.json#calibrationEnvelope"],
                "excludedRuntimeEffects": ["thrusters", "muzzle_flashes", "shadows", "debris", "other_sprite_foundry_effects"],
            }
        ],
    }
    manufacturing = {"schemaVersion": "skyforge.manufacturing-axes.v1", **MANUFACTURING_AXES}
    recovery = {
        "schemaVersion": "skyforge.provider-task-record.v1",
        "reservationId": "reservation-0001",
        "requestDigest": "1" * 64,
        "state": "unresolved",
        "sequence": 1,
        "timestamps": {"createdAt": "2026-08-01T00:00:00Z", "updatedAt": "2026-08-01T00:01:00Z"},
        "resolvedRequestDigest": "2" * 64,
        "evidenceClass": "mock_provider",
        "recoveryCorrelation": {
            "requestDigest": "1" * 64,
            "providerId": "mock",
            "providerModel": "mock-v1",
            "resolvedProviderOptionsDigest": "3" * 64,
            "authoritySetSha256": "4" * 64,
            "accountIdentityDigest": "5" * 64,
            "dispatchWindowStart": "2026-08-01T00:00:00Z",
            "dispatchWindowEnd": "2026-08-01T00:02:00Z",
            "expectedCost": {"unit": "credits", "amount": 20},
        },
        "correspondenceStatus": "zero_matches_unresolved",
    }
    return {
        "authority_embedded_valid.json": embedded,
        "authority_hash_only_valid.json": hash_only,
        "authority_unknown_embedded_invalid.json": invalid_embedded,
        "manifest_optional_absent_valid.json": absent,
        "manifest_optional_present_valid.json": present,
        "manifest_explicit_null_invalid.json": explicit_null,
        "manifest_producer_version_rebuild_valid.json": present,
        "frame_contract_valid.json": frame,
        "known_limitations_valid.json": limitations,
        "manufacturing_axes_valid.json": manufacturing,
        "provider_task_recovery_valid.json": recovery,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    schemas = build_schemas()
    examples = build_examples()
    SCHEMA_ROOT.mkdir(parents=True, exist_ok=True)
    EXAMPLE_ROOT.mkdir(parents=True, exist_ok=True)
    for existing in SCHEMA_ROOT.glob("*.json"):
        existing.unlink()
    for existing in EXAMPLE_ROOT.glob("*.json"):
        existing.unlink()
    for filename, value in sorted(schemas.items()):
        write_json(SCHEMA_ROOT / filename, value)
    for filename, value in sorted(examples.items()):
        write_json(EXAMPLE_ROOT / filename, value)
    index = {
        "schemaVersion": "skyforge.vmp-contract-index.v1",
        "packageVersion": "1.0.0",
        "digestProfile": "skyforge.vmp-content-digest.v1",
        "schemas": sorted(schemas),
        "examples": sorted(examples),
    }
    write_json(PACKAGE_ROOT / "contracts" / "vmp" / "v1" / "SCHEMA_INDEX.json", index)


if __name__ == "__main__":
    main()
