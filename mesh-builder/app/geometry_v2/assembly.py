from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from PIL import Image
from trimesh.visual.texture import TextureVisuals

from app.authority_mesh import (
    GENERATOR_ID as LEGACY_GENERATOR_ID,
)
from app.authority_mesh import (
    GENERATOR_VERSION as LEGACY_GENERATOR_VERSION,
)
from app.authority_mesh import (
    GLTF_TO_BLENDER,
    TARGET_TO_GLTF,
    generate_authority_mesh,
)

from .evidence import (
    DIAGNOSTIC_COLOURS,
    comparison_sheet,
    render_components,
    render_cross_sections,
    render_overlay,
    render_textured_top,
    sha256_file,
    write_manifest,
)
from .metrics import (
    component_record,
    gate_results,
    identity_metrics,
    semantic_height_bands,
    topology_passed,
    topology_record,
)
from .model import ExperimentResult, PlacedComponent
from .placement import fit_planform_dimensions, measure_planform, normalized_anchor
from .primitives import create_primitive
from .recipes import DEFAULT_RECIPE_PATH, load_recipe

GENERATOR_ID = "skyforge.authority-multivolume-experiment"
GENERATOR_VERSION = "0.8.0-alpha.1"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _target_mesh_from_legacy_glb(path: Path) -> trimesh.Trimesh:
    encoded = trimesh.load(path, force="mesh", process=False)
    target = encoded.copy()
    target.apply_transform(GLTF_TO_BLENDER)
    return target


def _surface_height(base: trimesh.Trimesh, x: float, y: float, upper: bool) -> float:
    vertices = np.asarray(base.vertices, dtype=np.float64)
    distance = np.square(vertices[:, 0] - x) + np.square(vertices[:, 1] - y)
    nearest = np.argpartition(distance, min(31, len(distance) - 1))[:32]
    values = vertices[nearest, 2]
    return float(np.max(values) if upper else np.min(values))


def _place_components(authority_path: Path, recipe: dict[str, Any], base_mesh: trimesh.Trimesh) -> tuple[Any, list[PlacedComponent]]:
    planform = measure_planform(authority_path)
    placed: list[PlacedComponent] = []
    for declaration in recipe["components"]:
        x, y = normalized_anchor(
            planform,
            float(declaration["longitudinalAnchor"]),
            float(declaration["lateralAnchor"]),
        )
        desired_length = float(declaration["normalizedLength"]) * planform.planform_length
        desired_width = float(declaration["normalizedWidth"]) * planform.planform_width
        length, width = fit_planform_dimensions(planform, (x, y), desired_length, desired_width)
        height = float(declaration["normalizedHeight"]) * planform.planform_length
        penetration = float(declaration["attachmentPenetration"]) * planform.planform_length
        underside = declaration["name"] in {"belly", "keel"}
        surface = _surface_height(base_mesh, x, y, upper=not underside)
        centre_z = surface + height / 2.0 - penetration
        if underside:
            centre_z = surface - height / 2.0 + penetration
        dimensions = (length, width, height)
        mesh = create_primitive(
            declaration["shape"],
            dimensions,
            int(declaration.get("subdivisions", 2)),
        )
        mesh.apply_translation([x, y, centre_z])
        placed.append(
            PlacedComponent(
                name=declaration["name"],
                shape=declaration["shape"],
                mesh=mesh,
                dimensions=dimensions,
                centre=(x, y, centre_z),
                attachment_penetration=penetration,
                minimum_volume=float(declaration["minimumVolume"]),
                minimum_triangles=int(declaration["minimumTriangles"]),
                underside=underside,
            )
        )
    return planform, placed


def _assign_planar_texture(mesh: trimesh.Trimesh, image: Image.Image) -> None:
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    uv = np.column_stack((vertices[:, 0] / 5.5 + 0.5, vertices[:, 1] / 5.5 + 0.5))
    mesh.visual = TextureVisuals(uv=np.clip(uv, 0.0, 1.0), image=image.copy())


def _encoded_scene(
    base_encoded: trimesh.Trimesh,
    components: list[PlacedComponent],
    texture: Image.Image,
    clay: bool,
) -> trimesh.Scene:
    scene = trimesh.Scene()
    base = base_encoded.copy()
    if clay:
        base.visual.vertex_colors = np.tile(DIAGNOSTIC_COLOURS["base_shell"], (len(base.vertices), 1))
    scene.add_geometry(base, geom_name="base_shell", node_name="base_shell")
    for component in components:
        encoded = component.mesh.copy()
        if clay:
            colour = DIAGNOSTIC_COLOURS.get(component.name, (170, 170, 170, 255))
            encoded.visual.vertex_colors = np.tile(colour, (len(encoded.vertices), 1))
        else:
            _assign_planar_texture(encoded, texture)
        encoded.apply_transform(TARGET_TO_GLTF)
        scene.add_geometry(encoded, geom_name=component.name, node_name=component.name)
    return scene


def _reload_audit(path: Path, expected_meshes: dict[str, trimesh.Trimesh]) -> dict[str, Any]:
    scene = trimesh.load(path, force="scene", process=False)
    target_meshes: dict[str, trimesh.Trimesh] = {}
    for name, geometry in scene.geometry.items():
        mesh = geometry.copy()
        mesh.apply_transform(GLTF_TO_BLENDER)
        target_meshes[name] = mesh
    expected = trimesh.util.concatenate([mesh.copy() for mesh in expected_meshes.values()])
    reloaded = trimesh.util.concatenate([mesh.copy() for mesh in target_meshes.values()])
    delta = float(np.max(np.abs(np.asarray(reloaded.bounds) - np.asarray(expected.bounds))))
    records = [topology_record(name, mesh) for name, mesh in sorted(target_meshes.items())]
    return {
        "componentCountBefore": len(expected_meshes),
        "componentCountAfter": len(target_meshes),
        "geometryNamesAfter": sorted(target_meshes),
        "geometryNamesMatch": sorted(target_meshes) == sorted(expected_meshes),
        "coordinateBoundsDelta": round(delta, 9),
        "coordinateEncoding": "target_xyz_to_gltf_x_z_neg_y",
        "topology": records,
        "topologyPassed": topology_passed(records),
        "targetMeshes": target_meshes,
    }


def _export_obj(meshes: list[trimesh.Trimesh], path: Path) -> None:
    combined = trimesh.util.concatenate([mesh.copy() for mesh in meshes])
    payload = trimesh.exchange.obj.export_obj(combined, include_texture=False)
    path.write_text(payload, encoding="utf-8")


def generate_multivolume_experiment(
    authority_path: Path,
    profile_id: str,
    output_dir: Path,
    recipe_path: Path = DEFAULT_RECIPE_PATH,
) -> ExperimentResult:
    authority_path = authority_path.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    recipe, recipe_digest = load_recipe(profile_id, recipe_path)
    legacy_dir = output_dir / "legacy_v0.7.1"
    legacy = generate_authority_mesh(authority_path, legacy_dir)
    legacy_gates_passed = bool(legacy.report["gateResults"]["passed"])
    if not legacy_gates_passed:
        raise RuntimeError("Nested legacy base-shell report did not pass all original gates")

    base_encoded = trimesh.load(legacy.mesh_path, force="mesh", process=False)
    base_target = _target_mesh_from_legacy_glb(legacy.mesh_path)
    planform, components = _place_components(authority_path, recipe, base_target)
    texture = Image.open(legacy.texture_path).convert("RGBA")
    try:
        textured_scene = _encoded_scene(base_encoded, components, texture, clay=False)
        clay_scene = _encoded_scene(base_encoded, components, texture, clay=True)
        mesh_path = output_dir / "multivolume_experiment.glb"
        clay_path = output_dir / "multivolume_component_clay.glb"
        mesh_path.write_bytes(trimesh.exchange.gltf.export_glb(textured_scene))
        clay_path.write_bytes(trimesh.exchange.gltf.export_glb(clay_scene))
    finally:
        texture.close()

    named_meshes = {"base_shell": base_target, **{item.name: item.mesh for item in components}}
    target_meshes = list(named_meshes.values())
    obj_path = output_dir / "multivolume_experiment.obj"
    _export_obj(target_meshes, obj_path)
    reload_audit = _reload_audit(mesh_path, named_meshes)
    records = [component_record(component, base_target) for component in components]
    identity = identity_metrics(planform, base_target, components)
    heights = semantic_height_bands(reload_audit["targetMeshes"], recipe["heightBandModel"])
    gates = gate_results(recipe, records, identity, heights, reload_audit, legacy_gates_passed)

    registry = {
        "schemaVersion": "skyforge.multivolume-component-registry.v1",
        "profileId": profile_id,
        "components": [
            {
                "name": "base_shell",
                "shape": "unchanged_v0.7.1_two_sided_shell",
                "sourceGlbSha256": sha256_file(legacy.mesh_path),
                "vertexCount": int(len(base_target.vertices)),
                "triangleCount": int(len(base_target.faces)),
                "watertight": bool(base_target.is_watertight),
                "windingConsistent": bool(base_target.is_winding_consistent),
            },
            *records,
        ],
    }
    registry_path = output_dir / "component_registry.json"
    registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    preview_paths: list[Path] = []
    for view in ("top", "bank_left", "bank_right", "front", "side"):
        path = output_dir / f"multivolume_preview_{view}.png"
        render_components(named_meshes, path, view)
        preview_paths.append(path)
    texture_top_path = output_dir / "multivolume_textured_top.png"
    with Image.open(authority_path) as authority_texture:
        render_textured_top(named_meshes, authority_texture, texture_top_path)
    preview_paths.append(texture_top_path)
    overlay_path = output_dir / "semantic_component_planform_overlay.png"
    render_overlay(planform, components, overlay_path)
    preview_paths.append(overlay_path)
    cross_section_path = output_dir / "multivolume_cross_section_sheet.png"
    render_cross_sections(components, cross_section_path)
    preview_paths.append(cross_section_path)
    attachment_path = output_dir / "attachment_exposure_diagnostic.png"
    render_components(named_meshes, attachment_path, "side")
    preview_paths.append(attachment_path)
    comparison_path = output_dir / "legacy_alpha1_comparison_contact_sheet.png"
    comparison_sheet(
        authority_path,
        legacy_dir / "authority_mesh_preview_top.png",
        output_dir / "multivolume_preview_top.png",
        comparison_path,
    )
    preview_paths.append(comparison_path)
    authority_copy = output_dir / f"authority_source_{authority_path.name}"
    authority_copy.write_bytes(authority_path.read_bytes())
    preview_paths.append(authority_copy)

    measurement_artifacts = {
        "authority_reference.json": {
            "file": authority_path.name,
            "sha256": sha256_file(authority_path),
            "constraintUse": "silhouette extents and occupied-row span only",
        },
        "iou_decomposition.json": identity["iouDecomposition"],
        "measured_height_bands.json": heights,
        "pre_export_topology.json": [
            topology_record(name, mesh) for name, mesh in sorted(named_meshes.items())
        ],
        "post_reload_topology.json": reload_audit["topology"],
        "attachment_exposure_measurements.json": {
            record["name"]: record["attachmentMeasurement"] for record in records
        },
    }
    for filename, payload in measurement_artifacts.items():
        path = output_dir / filename
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        preview_paths.append(path)

    legacy_report_bytes = legacy.report_path.read_bytes()
    report = {
        "schemaVersion": "skyforge.multivolume-experiment-report.v1",
        "generator": {"id": GENERATOR_ID, "version": GENERATOR_VERSION},
        "authority": {"file": authority_path.name, "sha256": sha256_file(authority_path)},
        "profileId": profile_id,
        "recipe": {
            "path": recipe_path.name,
            "version": recipe["recipeVersion"],
            "sha256": recipe_digest,
        },
        "legacyBase": {
            "generatorId": LEGACY_GENERATOR_ID,
            "generatorVersion": LEGACY_GENERATOR_VERSION,
            "reportSha256": _sha256_bytes(legacy_report_bytes),
            "reportPath": str(legacy.report_path.relative_to(output_dir)),
            "meshSha256": sha256_file(legacy.mesh_path),
            "allOriginalGatesPassed": legacy_gates_passed,
        },
        "geometryInputs": ["approved_authority_planform", "selected_profile_geometry_recipe"],
        "albedoGeometryInfluence": False,
        "albedoUse": "planar_texture_projection_only",
        "components": registry["components"],
        "identityMetrics": identity,
        "semanticHeightBands": heights,
        "preExportTopology": measurement_artifacts["pre_export_topology.json"],
        "assemblyReload": {key: value for key, value in reload_audit.items() if key != "targetMeshes"},
        "gateResults": gates,
        "limitations": [
            "Alpha 1 candidate-addresses MBS-151 through MBS-154; no finding is closed.",
            "MBS-150 perimeter terracing remains open for Alpha 2 smooth-shell/contour-loft work.",
            "Overlapping watertight components are not boolean-unioned.",
            "Alpha 1 does not yet claim MBS-153 closure; the gunship recipe includes an explicit belly volume.",
            "The experiment remains offline and outside VMP, UI, provider, and Sprite Foundry workflows.",
        ],
        "vmpExportAuthorized": False,
        "userTestingAuthorized": False,
        "paidProviderWorkAuthorized": False,
    }
    report_path = output_dir / "multivolume_generation_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = output_dir / "SHA256_MANIFEST.json"
    write_manifest(output_dir, manifest_path)
    if not gates["passed"]:
        failed = [name for name, passed in gates["checks"].items() if not passed]
        raise RuntimeError("Multivolume Alpha 1 gates failed: " + ", ".join(failed))
    return ExperimentResult(
        output_dir=output_dir,
        mesh_path=mesh_path,
        clay_mesh_path=clay_path,
        obj_path=obj_path,
        report_path=report_path,
        registry_path=registry_path,
        manifest_path=manifest_path,
        preview_paths=tuple(preview_paths),
        report=report,
    )
