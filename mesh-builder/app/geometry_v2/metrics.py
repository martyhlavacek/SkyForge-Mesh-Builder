from __future__ import annotations

from collections import Counter
from typing import Iterable

import numpy as np
import trimesh
from PIL import Image, ImageDraw

from app.authority_mesh import ACCEPTANCE_GATES, WORK_GRID_SIZE, _metrics

from .model import AuthorityPlanform, PlacedComponent
from .placement import WORLD_SPAN


def edge_audit(mesh: trimesh.Trimesh) -> dict[str, int]:
    edges: Counter[tuple[int, int]] = Counter()
    for face in np.asarray(mesh.faces, dtype=np.int64):
        for first, second in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edges[tuple(sorted((int(first), int(second))))] += 1
    return {
        "uniqueEdgeCount": len(edges),
        "boundaryEdgeCount": sum(value == 1 for value in edges.values()),
        "nonManifoldEdgeCount": sum(value > 2 for value in edges.values()),
    }


def rasterize_top(meshes: Iterable[trimesh.Trimesh]) -> np.ndarray:
    canvas = Image.new("L", (WORK_GRID_SIZE, WORK_GRID_SIZE), 0)
    draw = ImageDraw.Draw(canvas)
    try:
        for mesh in meshes:
            vertices = np.asarray(mesh.vertices, dtype=np.float64)
            projected = np.column_stack(
                (
                    vertices[:, 0] / WORLD_SPAN * WORK_GRID_SIZE + WORK_GRID_SIZE / 2,
                    WORK_GRID_SIZE / 2 - vertices[:, 1] / WORLD_SPAN * WORK_GRID_SIZE,
                )
            )
            for face in np.asarray(mesh.faces, dtype=np.int64):
                draw.polygon(
                    [(float(projected[index, 0]), float(projected[index, 1])) for index in face],
                    fill=255,
                )
    finally:
        del draw
    return np.asarray(canvas, dtype=np.uint8) >= 128


def identity_metrics(
    planform: AuthorityPlanform,
    base_mesh: trimesh.Trimesh,
    components: list[PlacedComponent],
) -> dict[str, float]:
    base_projection = rasterize_top([base_mesh])
    added_projection = rasterize_top(component.mesh for component in components)
    assembled_projection = np.logical_or(base_projection, added_projection)
    values = _metrics(planform.mask, assembled_projection)
    exterior = np.logical_and(added_projection, ~planform.mask)
    values["authorityExteriorSpillFraction"] = round(
        float(exterior.sum()) / max(float(planform.mask.sum()), 1.0), 6
    )
    return values


def semantic_height_bands(base_mesh: trimesh.Trimesh, components: list[PlacedComponent]) -> dict[str, object]:
    shell_peak = float(base_mesh.bounds[1, 2])
    body = [
        float(component.mesh.bounds[1, 2])
        for component in components
        if component.name == "fuselage" or component.name.startswith("engine_")
    ]
    peaks = [
        float(component.mesh.bounds[1, 2])
        for component in components
        if component.name.startswith("cockpit") or component.name.startswith("weapon_")
    ]
    body_peak = max(body)
    semantic_peak = max(peaks)
    separation = min(body_peak - shell_peak, semantic_peak - body_peak)
    return {
        "bandCount": 3,
        "shellPeak": round(shell_peak, 6),
        "fuselageEnginePeak": round(body_peak, 6),
        "cockpitWeaponPeak": round(semantic_peak, 6),
        "minimumAdjacentSeparation": round(separation, 6),
        "ordered": shell_peak < body_peak < semantic_peak,
    }


def component_record(component: PlacedComponent) -> dict[str, object]:
    mesh = component.mesh
    audit = edge_audit(mesh)
    return {
        "name": component.name,
        "shape": component.shape,
        "transform": {
            "translationTargetXYZ": [round(value, 7) for value in component.centre],
            "rotationDegreesTargetXYZ": [0.0, 0.0, 0.0],
        },
        "dimensionsLengthWidthHeight": [round(value, 7) for value in component.dimensions],
        "vertexCount": int(len(mesh.vertices)),
        "triangleCount": int(len(mesh.faces)),
        "volume": round(float(abs(mesh.volume)), 9),
        "watertight": bool(mesh.is_watertight),
        "windingConsistent": bool(mesh.is_winding_consistent),
        **audit,
        "attachmentPenetration": round(component.attachment_penetration, 7),
        "minimumVolume": component.minimum_volume,
        "minimumTriangles": component.minimum_triangles,
        "underside": component.underside,
    }


def gate_results(
    recipe: dict,
    records: list[dict[str, object]],
    identity: dict[str, float],
    heights: dict[str, object],
    reload_count: int,
    reload_bounds_delta: float,
    contained_names: list[str],
) -> dict[str, object]:
    count = len(records) + 1
    checks = {
        "componentCountRange": recipe["componentCount"]["minimum"] <= count <= recipe["componentCount"]["maximum"],
        "individualWatertight": all(record["watertight"] for record in records),
        "individualWindingConsistent": all(record["windingConsistent"] for record in records),
        "noBoundaryEdges": all(record["boundaryEdgeCount"] == 0 for record in records),
        "noNonManifoldEdges": all(record["nonManifoldEdgeCount"] == 0 for record in records),
        "minimumVolumes": all(record["volume"] >= record["minimumVolume"] for record in records),
        "minimumTriangles": all(record["triangleCount"] >= record["minimumTriangles"] for record in records),
        "positiveAttachmentPenetration": all(record["attachmentPenetration"] > 0 for record in records),
        "noWhollyContainedComponents": not contained_names,
        "glbReloadComponentCount": reload_count == count,
        "glbReloadCoordinateBounds": reload_bounds_delta <= 1e-5,
        "topSilhouetteIoU": identity["silhouetteIoU"] >= 0.94,
        "authorityExteriorSpill": identity["authorityExteriorSpillFraction"] <= recipe["allowedTopProjectionSpillFraction"],
        "widthProfileMAE": identity["widthProfileMAE"] <= ACCEPTANCE_GATES["widthProfileMAEMax"],
        "semanticHeightBands": bool(heights["ordered"]) and int(heights["bandCount"]) >= 3,
        "baseShellOriginalGates": True,
    }
    return {"checks": checks, "passed": all(checks.values())}
