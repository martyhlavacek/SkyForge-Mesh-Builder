from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image

from common.glb_facts import GlbFacts, parse_glb_facts

from .asset_migration import write_migration_artifacts
from .pipeline import JobPaths, read_job_status, verify_generation_contract, verify_required_outputs
from .vmp_builder import VmpBuildMetadata, VmpBuildResult, build_vmp

SIDECAR_VERSION = "0.7.1"
PROVIDER_ID = "local_deterministic"
PROVIDER_MODEL = "skyforge.authority-two-sided-field@0.6.0"
IDENTITY_MODEL = "deterministic_reproducibility"
SUPPORTED_ASSET_ROLE = "air_moving"
BLENDER_SILHOUETTE_IOU_MIN = 0.94
IMPORT_PROBE_RECEIPT_SCHEMA = "skyforge.sprite-foundry-import-receipt.v1"
AUTHORITY_PERMISSION_VALUES = frozenset({"permitted", "unknown", "prohibited"})


class JobVmpExportError(ValueError):
    """Raised when a rendered job cannot be exported without violating VMP v1."""


@dataclass(frozen=True)
class JobVmpExportRequest:
    asset_version: str
    authority_redistribution_permission: str
    authority_terms_basis: str
    asset_commercial_use_asserted: bool


@dataclass(frozen=True)
class JobVmpExportResult:
    build: VmpBuildResult
    receipt_path: Path
    receipt: dict[str, Any]



def resolve_import_probe_command(package_root: Path) -> tuple[str, ...] | None:
    root_value = os.environ.get("SKYFORGE_IMPORT_PROBE_ROOT", "").strip()
    python_value = os.environ.get("SKYFORGE_IMPORT_PROBE_PYTHON", "").strip()
    if not root_value and not python_value:
        config_path = package_root / "config.json"
        if config_path.is_file():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                config = {}
            if isinstance(config, dict):
                root_value = str(config.get("importProbeRoot") or "").strip()
                python_value = str(config.get("importProbePython") or "").strip()
    if not root_value or not python_value:
        return None
    probe_root = Path(root_value).expanduser().resolve()
    python_path = Path(os.path.abspath(os.fspath(Path(python_value).expanduser())))
    script = probe_root / "scripts/run_import_probe.py"
    binding = probe_root / "IMPORT_PROBE_SOURCE_BINDING.json"
    if not python_path.is_file() or not os.access(python_path, os.X_OK):
        return None
    if not script.is_file() or not binding.is_file():
        return None
    return (str(python_path), str(script))

def export_rendered_job_vmp(
    package_root: Path,
    job: JobPaths,
    request: JobVmpExportRequest,
    archive_path: Path,
    *,
    import_probe_command: Sequence[str],
) -> JobVmpExportResult:
    status = read_job_status(job)
    if status.get("status") != "rendered":
        raise JobVmpExportError("Only a rendered and verified job may be exported as VMP")
    manifest_path = job.root / "manifest.json"
    manifest = _load_object(manifest_path)
    _validate_request(request)
    _validate_job_contract(manifest)
    try:
        verify_generation_contract(job, manifest_path)
        verification = verify_required_outputs(job, manifest_path)
    except RuntimeError as exc:
        raise JobVmpExportError(f"Current job verification failed: {exc}") from exc
    payload, metadata = build_job_payload(
        package_root,
        job,
        manifest,
        status,
        verification,
        request,
    )
    build = build_vmp(payload, metadata, archive_path)
    receipt_path = archive_path.with_suffix(".import_receipt.json")
    receipt = run_import_probe(import_probe_command, archive_path, receipt_path)
    if receipt.get("schemaVersion") != IMPORT_PROBE_RECEIPT_SCHEMA or receipt.get("accepted") is not True:
        archive_path.unlink(missing_ok=True)
        receipt_path.unlink(missing_ok=True)
        raise JobVmpExportError("Independent Sprite Foundry Import Probe did not accept the VMP")
    if receipt.get("sourcePackageContentDigest") != build.package_content_digest:
        archive_path.unlink(missing_ok=True)
        receipt_path.unlink(missing_ok=True)
        raise JobVmpExportError("Import Receipt is bound to a different semantic package identity")
    if receipt.get("sourceArchiveSha256") != build.archive_sha256:
        archive_path.unlink(missing_ok=True)
        receipt_path.unlink(missing_ok=True)
        raise JobVmpExportError("Import Receipt is bound to a different transport archive")
    return JobVmpExportResult(build=build, receipt_path=receipt_path, receipt=receipt)


def build_job_payload(
    package_root: Path,
    job: JobPaths,
    manifest: Mapping[str, Any],
    status: Mapping[str, Any],
    verification: Mapping[str, Any],
    request: JobVmpExportRequest,
) -> tuple[dict[str, bytes], VmpBuildMetadata]:
    _validate_request(request)
    _validate_job_contract(manifest)
    settings = _object(manifest.get("settings"), "manifest.settings")
    _validate_frozen_frame_settings(settings)

    glb_path = job.output / "normalized.glb"
    legacy_asset_path = job.output / "asset.json"
    authority_record = _object(manifest.get("authority"), "manifest.authority")
    authority_path = job.source / _required_string(authority_record, "path")
    generation_path = job.source / _required_string(_object(manifest.get("mesh"), "manifest.mesh"), "generationReport")
    for path, label in (
        (glb_path, "normalized GLB"),
        (legacy_asset_path, "legacy asset contract"),
        (authority_path, "authority"),
        (generation_path, "generation report"),
    ):
        if not path.is_file() or path.stat().st_size == 0:
            raise JobVmpExportError(f"Required {label} is absent")
    if authority_path.suffix.lower() != ".png":
        raise JobVmpExportError("VMP v1 authority embedding/hash contract requires the approved authority to be PNG")

    glb_bytes = glb_path.read_bytes()
    glb_sha = hashlib.sha256(glb_bytes).hexdigest()
    glb_facts = parse_glb_facts(glb_bytes)
    generation = _load_object(generation_path)
    legacy_asset = _load_object(legacy_asset_path)
    run_report = _load_object(job.output / "run_report.json")
    measured_blender_iou = float(
        _object(_object(legacy_asset.get("measurements"), "asset.measurements").get("silhouetteIoU"),
                "asset.measurements.silhouetteIoU").get("value", 0.0)
    )
    if measured_blender_iou < BLENDER_SILHOUETTE_IOU_MIN:
        raise JobVmpExportError(
            f"Blender silhouette IoU {measured_blender_iou:.6f} is below the frozen 0.94 floor"
        )

    approval_time = _required_string(status, "renderedAt" if status.get("renderedAt") else "updatedAt")
    approval_event_id = "approval-" + hashlib.sha256(
        f"{job.root.name}\0{glb_sha}\0{request.asset_version}".encode("utf-8")
    ).hexdigest()[:20]
    approval = {
        "state": "approved",
        "approvedForDistribution": True,
        "eventId": approval_event_id,
        "artifactSha256": glb_sha,
        "recordedAt": approval_time,
    }
    staging = job.root / "vmp_staging"
    migration = write_migration_artifacts(
        legacy_asset_path,
        job.root / "manifest.json",
        staging,
        approval=approval,
        asset_version=request.asset_version,
        asset_role=SUPPORTED_ASSET_ROLE,
    )

    authority_bytes = authority_path.read_bytes()
    authority_sha = hashlib.sha256(authority_bytes).hexdigest()
    if authority_sha != authority_record.get("sha256"):
        raise JobVmpExportError("Approved authority bytes no longer match the job manifest")
    authority_set_sha = hashlib.sha256(authority_sha.encode("ascii")).hexdigest()
    profile = _object(manifest.get("profile"), "manifest.profile")
    asset_id = _required_string(manifest, "assetId")
    craft_profile_id = _required_string(profile, "id")

    payload: dict[str, bytes] = {
        "asset.json": migration.asset_bytes,
        "mesh/normalized.glb": glb_bytes,
        "mesh/semantic_identity.json": _json_bytes(
            _semantic_identity(glb_sha, measured_blender_iou)
        ),
        "mesh/component_manifest.json": _json_bytes(
            _component_manifest(glb_facts, generation)
        ),
        "mesh/bounds_and_scale.json": _json_bytes(
            _bounds_and_scale(glb_facts, job.output / "preview_neutral_96_lanczos.png")
        ),
        "role/asset_role.json": _json_bytes(_asset_role()),
        "role/manufacturing_axes.json": (
            package_root / "contracts/vmp/v1/examples/manufacturing_axes_valid.json"
        ).read_bytes(),
        "role/pivot_contract.json": _json_bytes(_pivot_contract()),
        "render/frame_contract.json": _json_bytes(_frame_contract(settings, glb_facts)),
        "materials/material_contract.json": _json_bytes(_material_contract()),
        "provenance/source_chain.json": _json_bytes(
            _source_chain(authority_set_sha, authority_sha, glb_sha, approval)
        ),
        "licensing_and_terms.json": _json_bytes(
            _licensing_and_terms(request, approval_time)
        ),
        "validation/geometry.json": _json_bytes(
            _geometry_validation(generation, glb_sha, approval_time)
        ),
        "validation/independent_reload.json": _json_bytes(
            _reload_validation(generation, glb_sha, approval_time)
        ),
        "validation/blender.json": _json_bytes(
            _blender_validation(run_report, verification, glb_sha, measured_blender_iou, approval_time)
        ),
        "previews/gameplay_scale_96.png": (job.output / "preview_neutral_96_lanczos.png").read_bytes(),
        "previews/silhouette_comparison.png": (job.output / "silhouette_comparison.png").read_bytes(),
        "known_limitations.json": (
            package_root / "contracts/vmp/v1/examples/known_limitations_valid.json"
        ).read_bytes(),
    }
    embedded = request.authority_redistribution_permission == "permitted"
    authority_item: dict[str, Any] = {
        "role": "silhouette_authority",
        "sourceSha256": authority_sha,
        "contentType": "image/png",
        "embedded": embedded,
        "redistributionPermission": request.authority_redistribution_permission,
        "embeddingDecision": "embedded" if embedded else "hash_only_due_to_terms",
        "independentReverification": "full" if embedded else "unavailable_due_to_terms",
        "generationProvenanceRef": "provenance/source_chain.json#authority-1",
    }
    if embedded:
        authority_item["embeddedPath"] = "authorities/silhouette_authority.png"
        payload["authorities/silhouette_authority.png"] = authority_bytes
    payload["authorities/authority_manifest.json"] = _json_bytes({
        "schemaVersion": "skyforge.authority-manifest.v1",
        "authoritySetSha256": authority_set_sha,
        "authorities": [authority_item],
    })
    metadata = VmpBuildMetadata(
        asset_id=asset_id,
        asset_version=request.asset_version,
        craft_profile_id=craft_profile_id,
        sidecar_version=SIDECAR_VERSION,
        provider_id=PROVIDER_ID,
        provider_model=PROVIDER_MODEL,
        identity_model=IDENTITY_MODEL,
        authority_set_sha256=authority_set_sha,
        minimum_importer_version="0.1.0",
    )
    return payload, metadata


def _probe_site_packages(interpreter: Path) -> Path:
    interpreter = interpreter.expanduser().absolute()
    environment_root = interpreter.parent.parent
    if not (environment_root / "pyvenv.cfg").is_file():
        raise JobVmpExportError("Independent Import Probe interpreter is not inside a bound virtual environment")
    candidates = sorted((environment_root / "lib").glob("python*/site-packages"))
    candidates = [path for path in candidates if path.is_dir()]
    if len(candidates) != 1:
        raise JobVmpExportError("Independent Import Probe virtual environment has an ambiguous site-packages layout")
    return candidates[0].absolute()


def _import_probe_environment(command: Sequence[str], *, platform_name: str | None = None) -> dict[str, str]:
    if not command:
        raise JobVmpExportError("Independent Import Probe command is not configured")
    interpreter = Path(command[0]).expanduser().absolute()
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(_probe_site_packages(interpreter)),
    }
    resolved_platform = sys.platform if platform_name is None else platform_name
    if resolved_platform == "darwin":
        environment["__PYVENV_LAUNCHER__"] = str(interpreter)
    return environment


def run_import_probe(command: Sequence[str], archive_path: Path, receipt_path: Path) -> dict[str, Any]:
    if not command:
        raise JobVmpExportError("Independent Import Probe command is not configured")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [*command, str(archive_path), "--receipt", str(receipt_path)],
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
        env=_import_probe_environment(command),
    )
    if completed.returncode != 0:
        receipt_path.unlink(missing_ok=True)
        detail = (completed.stderr or completed.stdout or "probe rejected package").strip()
        raise JobVmpExportError(f"Independent Import Probe failed: {detail[:4000]}")
    if not receipt_path.is_file():
        raise JobVmpExportError("Independent Import Probe did not issue an Import Receipt")
    return _load_object(receipt_path)


def _validate_request(request: JobVmpExportRequest) -> None:
    if not request.asset_version or not _is_semver(request.asset_version):
        raise JobVmpExportError("assetVersion must use numeric semantic version form, for example 1.0.0")
    if request.authority_redistribution_permission not in AUTHORITY_PERMISSION_VALUES:
        raise JobVmpExportError("Unknown authority redistribution permission")
    if not request.authority_terms_basis.strip():
        raise JobVmpExportError("Authority terms basis is required")
    if request.asset_commercial_use_asserted is not True:
        raise JobVmpExportError("Explicit commercial-use assertion is required for distribution export")


def _validate_job_contract(manifest: Mapping[str, Any]) -> None:
    experiment = _object(manifest.get("experiment"), "manifest.experiment")
    mesh = _object(manifest.get("mesh"), "manifest.mesh")
    generator = _object(manifest.get("generator"), "manifest.generator")
    gate = _object(manifest.get("distributionGate"), "manifest.distributionGate")
    if experiment.get("id") != "authority_mesh":
        raise JobVmpExportError("Only local Authority Mesh jobs may emit VMP v1")
    if mesh.get("origin") != "generated_from_authority" or mesh.get("generatedFromAuthority") is not True:
        raise JobVmpExportError("VMP export requires an authority-derived local mesh")
    if generator.get("generatorId") != "skyforge.authority-two-sided-field":
        raise JobVmpExportError("VMP export requires the frozen local deterministic producer")
    if gate.get("approved") is not True or generator.get("approvedForDistribution") is not True:
        raise JobVmpExportError("Explicit distribution approval metadata is missing")


def _validate_frozen_frame_settings(settings: Mapping[str, Any]) -> None:
    expected = {
        "bankDegrees": 18.0,
        "masterResolution": 384,
        "cameraPitchDegrees": 20.0,
        "forwardAxis": "+Y",
        "upAxis": "+Z",
        "renderSamples": 64,
    }
    for key, value in expected.items():
        actual = settings.get(key)
        if isinstance(value, float):
            if abs(float(actual) - value) > 1e-9:
                raise JobVmpExportError(f"VMP v1 requires frozen {key}={value:g}")
        elif actual != value:
            raise JobVmpExportError(f"VMP v1 requires frozen {key}={value}")


def _semantic_identity(glb_sha: str, blender_iou: float) -> dict[str, Any]:
    return {
        "schemaVersion": "skyforge.mesh-semantic-identity.v1",
        "identityModel": IDENTITY_MODEL,
        "reference": {"localReferenceGlbSha256": glb_sha},
        "localDeterministicContract": {
            "exactIndices": True,
            "exactXZ": True,
            "exactUV": True,
            "exactDecodedTexturePixels": True,
            "yMaxAbsTolerance": 1e-5,
            "yRmsTolerance": 1e-6,
            "rawGlbShaGating": False,
            "rawGlbShaInformational": True,
        },
        "blenderSilhouetteIoUMin": BLENDER_SILHOUETTE_IOU_MIN,
        "measuredResults": [{"name": "blenderSilhouetteIoU", "value": blender_iou}],
    }


def _component_manifest(facts: GlbFacts, generation: Mapping[str, Any]) -> dict[str, Any]:
    mesh = _object(generation.get("mesh"), "generation.mesh")
    metrics = _object(generation.get("geometryMetrics"), "generation.geometryMetrics")
    component_count = int(mesh.get("componentCount", 0))
    if component_count != 1:
        raise JobVmpExportError("VMP v1 requires exactly one independently reloaded mesh component")
    return {
        "schemaVersion": "skyforge.mesh-components.v1",
        "componentCount": component_count,
        "componentPolicy": "single_component_required",
        "components": [{
            "componentId": "component-0",
            "primitiveOrNodeRefs": [str(index) for index in range(max(facts.mesh_count, 1))],
            "vertexCount": facts.vertex_count,
            "triangleCount": facts.triangle_count,
            "bounds": {"min": list(facts.bounds_min), "max": list(facts.bounds_max)},
            "volumeFraction": 1.0,
            "watertight": bool(mesh.get("glbReloadWatertight")),
            "eulerNumber": int(metrics.get("eulerNumber", 0)),
            "genus": int(float(metrics.get("genus", -1))),
            "boundaryEdges": int(mesh.get("boundaryEdgeCount", 0)),
            "nonManifoldEdges": int(mesh.get("nonManifoldEdgeCount", 0)),
        }],
    }


def _bounds_and_scale(facts: GlbFacts, preview_path: Path) -> dict[str, Any]:
    target_min, target_max = _target_bounds(facts.bounds_min, facts.bounds_max)
    extents = [target_max[index] - target_min[index] for index in range(3)]
    planform = max(extents[0], extents[1])
    height = extents[2]
    fitted, margin = _preview_mapping(preview_path)
    return {
        "schemaVersion": "skyforge.mesh-bounds-scale.v1",
        "coordinateContract": "skyforge.mesh-coordinate.v1",
        "units": "skyforge_world_units",
        "bounds": {"min": target_min, "max": target_max, "extents": extents},
        "canonicalScale": {
            "longestPlanformExtentWorld": planform,
            "heightWorld": height,
            "heightToPlanformRatio": height / max(planform, 1e-12),
        },
        "gameplayPreviewMapping": {
            "referenceImage": "previews/gameplay_scale_96.png",
            "canvasPixels": [96, 96],
            "worldUnitsPerPixel": planform / max(fitted, 1),
            "fittedPlanformPixels": fitted,
            "transparentMarginPixels": margin,
        },
        "pivotFrame": "normalized_mesh_frame",
    }


def _asset_role() -> dict[str, Any]:
    return {
        "schemaVersion": "skyforge.asset-role.v1",
        "preset": SUPPORTED_ASSET_ROLE,
        "capabilities": {
            "timelineMovement": True,
            "airborne": True,
            "terrainPlacement": False,
            "directionalGroundSet": False,
        },
    }


def _pivot_contract() -> dict[str, Any]:
    return {
        "schemaVersion": "skyforge.pivot-contract.v1",
        "rootPivot": {
            "position": [0.0, 0.0, 0.0],
            "orientationQuaternion": [0.0, 0.0, 0.0, 1.0],
            "frame": "normalized_mesh_frame",
            "source": "deterministic",
            "approvalState": "approved",
        },
        "partPivots": [],
    }


def _frame_contract(settings: Mapping[str, Any], facts: GlbFacts) -> dict[str, Any]:
    calibration = _object(settings.get("canonicalFrameCalibration"), "settings.canonicalFrameCalibration")
    target_min, target_max = _target_bounds(facts.bounds_min, facts.bounds_max)
    extents = [target_max[index] - target_min[index] for index in range(3)]
    planform = max(extents[0], extents[1])
    height_ratio = extents[2] / max(planform, 1e-12)
    return {
        "schemaVersion": "skyforge.render-frame-contract.v1",
        "coordinateFrame": {"forwardAxis": "+Y", "upAxis": "+Z", "rightAxis": "+X"},
        "canonicalCamera": {
            "projection": "orthographic",
            "pitchDegrees": 20,
            "bankDegrees": 0,
            "yawDegrees": 0,
            "canonicalOrthoScale": float(calibration["canonicalOrthoScale"]),
            "requiredReviewOrthoScale": float(calibration["canonicalOrthoScale"]),
            "requiredSilhouetteOrthoScale": float(calibration["canonicalOrthoScale"]),
        },
        "headroom": {
            "worldUnits": float(calibration["fixtureHeadroomWorldUnits"]),
            "fractionOfPlanform": float(calibration["fixtureHeadroomFraction"]),
        },
        "calibration": {
            "method": str(calibration["method"]),
            "profileDigest": str(calibration["profileDigest"]),
            "pitchSamplesDegrees": [0, 20, 36],
            "bankSamplesDegrees": [-18, 0, 18],
            "referencePoseMap": {"bank_left": -18, "neutral": 0, "bank_right": 18},
        },
        "calibrationEnvelope": {
            "maximumHeightToPlanformRatio": float(calibration["maximumHeightToPlanformRatio"]),
            "heightEnvelopeBindingPitchDegrees": int(calibration["heightEnvelopeBindingPitchDegrees"]),
            "measuredMaximumRequiredOrthoScale": float(calibration["measuredMaximumRequiredOrthoScale"]),
            "measuredRequiredMargin": float(calibration["measuredRequiredMargin"]),
            "chosenMargin": float(calibration["chosenMargin"]),
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
        "heightToPlanformRatio": height_ratio,
        "consumerDeviationPolicy": {
            "spriteFoundryMayExtendBankPitchLadder": True,
            "extensionWithinCalibrationEnvelopeOnly": True,
            "newCalibrationRequiredOutsideEnvelope": True,
            "deviationMustBeRecorded": True,
        },
    }


def _material_contract() -> dict[str, Any]:
    return {
        "schemaVersion": "skyforge.mesh-material.v1",
        "baseColor": {
            "source": "authority_projection",
            "colorSpace": "sRGB",
            "lightingState": "unlit_albedo",
        },
        "alphaPolicy": "straight_alpha",
        "externalReferences": False,
        "providerProcessing": {
            "imageEnhancementApplied": False,
            "removeLightingApplied": "not_applicable",
            "aiTexturingApplied": False,
        },
        "semanticRegions": [],
        "textures": [],
    }


def _source_chain(
    authority_set_sha: str,
    authority_sha: str,
    glb_sha: str,
    approval: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schemaVersion": "skyforge.source-chain.v1",
        "authoritySetSha256": authority_set_sha,
        "lineage": [
            {"stage": "authority", "artifactSha256": authority_sha, "producerId": "mesh_foundry"},
            {
                "stage": "normalized_mesh",
                "artifactSha256": glb_sha,
                "producerId": "mesh_foundry",
                "providerModel": PROVIDER_MODEL,
            },
        ],
        "normalizationVersion": SIDECAR_VERSION,
        "approvalEvents": [{
            "eventId": approval["eventId"],
            "state": "approved",
            "artifactSha256": glb_sha,
            "recordedAt": approval["recordedAt"],
        }],
    }


def _licensing_and_terms(request: JobVmpExportRequest, recorded_at: str) -> dict[str, Any]:
    permission: bool | str = request.authority_redistribution_permission == "permitted"
    if request.authority_redistribution_permission == "unknown":
        permission = "unknown"
    return {
        "schemaVersion": "skyforge.licensing-terms.v1",
        "assetCommercialUseAsserted": True,
        "termsSnapshots": [{
            "source": request.authority_terms_basis,
            "versionOrDate": recorded_at[:10],
            "recordedAt": recorded_at,
        }],
        "authorityRedistribution": {
            "permitted": permission,
            "basis": request.authority_terms_basis,
        },
        "provider": {
            "modelId": PROVIDER_MODEL,
            "accountTier": "internal_no_charge",
            "modelAvailabilityRisk": "local_source_binding_required",
            "pricingSource": "not_applicable_local_deterministic",
            "pricingVerifiedAt": recorded_at,
        },
    }


def _geometry_validation(generation: Mapping[str, Any], glb_sha: str, executed_at: str) -> dict[str, Any]:
    mesh = _object(generation.get("mesh"), "generation.mesh")
    identity = _object(generation.get("identityMetrics"), "generation.identityMetrics")
    checks = _object(_object(generation.get("gateResults"), "generation.gateResults").get("checks"),
                     "generation.gateResults.checks")
    iou = float(identity.get("silhouetteIoU", 0.0))
    measured = [
        {"name": "sourceVertexCount", "value": str(int(mesh.get("vertexCount", 0)))},
        {"name": "sourceTriangleCount", "value": str(int(mesh.get("triangleCount", 0)))},
        {"name": "sourceBoundaryEdgeCount", "value": str(int(mesh.get("boundaryEdgeCount", 0)))},
        {"name": "sourceNonManifoldEdgeCount", "value": str(int(mesh.get("nonManifoldEdgeCount", 0)))},
        {"name": "sourceSilhouetteIoU", "value": iou},
    ]
    gates = [
        _gate("generatorGateSet", bool(_object(generation.get("gateResults"), "generation.gateResults").get("passed")), True),
        _gate("sourceSilhouetteIoU", iou >= 0.94, iou, ">=", 0.94),
        _gate("singleComponent", bool(checks.get("components")), True),
        _gate("watertight", bool(mesh.get("watertightByEdgeIncidence")), True),
    ]
    return _validation("geometry", glb_sha, executed_at, measured, gates)


def _reload_validation(generation: Mapping[str, Any], glb_sha: str, executed_at: str) -> dict[str, Any]:
    mesh = _object(generation.get("mesh"), "generation.mesh")
    coordinate = _object(mesh.get("coordinateContract"), "generation.mesh.coordinateContract")
    delta = float(coordinate.get("blenderImportBoundsDelta", 1.0))
    height_ratio = float(coordinate.get("blenderImportHeightToPlanformRatio", 1.0))
    values = [
        {"name": "glbReloadWatertight", "value": bool(mesh.get("glbReloadWatertight"))},
        {"name": "glbReloadWindingConsistent", "value": bool(mesh.get("glbReloadWindingConsistent"))},
        {"name": "blenderImportBoundsDelta", "value": delta},
        {"name": "blenderImportHeightToPlanformRatio", "value": height_ratio},
    ]
    gates = [
        _gate("glbReloadWatertight", bool(mesh.get("glbReloadWatertight")), True),
        _gate("glbReloadWindingConsistent", bool(mesh.get("glbReloadWindingConsistent")), True),
        _gate("coordinateBoundsDelta", delta <= 1e-5, delta, "<=", 1e-5),
        _gate("heightToPlanformRatio", height_ratio <= 0.45, height_ratio, "<=", 0.45),
    ]
    return _validation("independent_reload", glb_sha, executed_at, values, gates)


def _blender_validation(
    run_report: Mapping[str, Any],
    verification: Mapping[str, Any],
    glb_sha: str,
    blender_iou: float,
    executed_at: str,
) -> dict[str, Any]:
    values = [
        {"name": "blenderSilhouetteIoU", "value": blender_iou},
        {"name": "neutralPoseRestoredBeforeExport", "value": bool(run_report.get("neutralPoseRestoredBeforeExport"))},
        {"name": "meshMatricesIdentityAtExport", "value": bool(run_report.get("meshMatricesIdentityAtExport"))},
        {"name": "requiredOutputCount", "value": str(int(verification.get("requiredOutputCount", 0)))},
    ]
    gates = [
        _gate("blenderSilhouetteIoU", blender_iou >= 0.94, blender_iou, ">=", 0.94),
        _gate("neutralPoseRestoredBeforeExport", bool(run_report.get("neutralPoseRestoredBeforeExport")), True),
        _gate("meshMatricesIdentityAtExport", bool(run_report.get("meshMatricesIdentityAtExport")), True),
        _gate("noReviewRigInCleanExport", not bool(run_report.get("cleanExportContainsReviewRig")), False),
        _gate("worldBoundsPreserved", bool(run_report.get("meshWorldBoundsPreservedDuringBake")), True),
    ]
    return _validation("blender", glb_sha, executed_at, values, gates)


def _validation(
    validation_class: str,
    glb_sha: str,
    executed_at: str,
    measured_values: list[dict[str, Any]],
    gates: list[dict[str, Any]],
) -> dict[str, Any]:
    passed = all(bool(item["passed"]) for item in gates)
    value: dict[str, Any] = {
        "schemaVersion": "skyforge.validation-report.v1",
        "validationClass": validation_class,
        "validatorVersion": SIDECAR_VERSION,
        "sourceGlbSha256": glb_sha,
        "executedAt": executed_at,
        "measuredValues": measured_values,
        "gates": gates,
        "passed": passed,
    }
    if not passed:
        value["failureReasons"] = sorted(item["name"] for item in gates if not item["passed"])
    return value


def _gate(
    name: str,
    passed: bool,
    measured: Any,
    operator: str = "==",
    threshold: Any = True,
) -> dict[str, Any]:
    value = {
        "name": name,
        "passed": bool(passed),
        "measuredValue": measured,
        "thresholdOperator": operator,
        "thresholdValue": threshold,
    }
    if not passed:
        value["failureReason"] = f"{name} did not satisfy the frozen gate"
    return value


def _target_bounds(
    gltf_min: tuple[float, float, float], gltf_max: tuple[float, float, float]
) -> tuple[list[float], list[float]]:
    # Frozen generator encoding: target (x, y, z) -> glTF (x, z, -y).
    target_min = [gltf_min[0], -gltf_max[2], gltf_min[1]]
    target_max = [gltf_max[0], -gltf_min[2], gltf_max[1]]
    return target_min, target_max


def _preview_mapping(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        alpha = image.convert("RGBA").getchannel("A")
        box = alpha.getbbox()
    if box is None:
        raise JobVmpExportError("Gameplay preview is empty")
    width = box[2] - box[0]
    height = box[3] - box[1]
    fitted = max(width, height)
    margin = min(box[0], box[1], 96 - box[2], 96 - box[3])
    return fitted, max(margin, 0)


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JobVmpExportError(f"Invalid JSON artifact: {path.name}") from exc
    if not isinstance(value, dict):
        raise JobVmpExportError(f"JSON artifact is not an object: {path.name}")
    return value


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise JobVmpExportError(f"{label} must be an object")
    return value


def _required_string(value: Mapping[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item:
        raise JobVmpExportError(f"Required string is absent: {name}")
    return item


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _is_semver(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 3 and all(part.isdigit() and str(int(part)) == part for part in parts)
