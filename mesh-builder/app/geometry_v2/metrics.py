from __future__ import annotations

from collections import Counter
from typing import Iterable

import numpy as np
import trimesh
from PIL import Image, ImageDraw

from app.authority_mesh import ACCEPTANCE_GATES, WORK_GRID_SIZE, _metrics

from .model import AuthorityPlanform, PlacedComponent
from .placement import WORLD_SPAN

ATTACHMENT_THRESHOLDS = {
    "minimumEmbeddedFraction": 0.01,
    "minimumExposedFraction": 0.01,
    "surfaceTolerance": 1e-5,
    "xyNeighbourCount": 32,
}


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


def topology_record(name: str, mesh: trimesh.Trimesh) -> dict[str, object]:
    areas = np.asarray(mesh.area_faces, dtype=np.float64)
    finite = bool(np.isfinite(mesh.vertices).all() and np.isfinite(mesh.faces).all())
    audit = edge_audit(mesh)
    return {
        "name": name,
        "vertexCount": int(len(mesh.vertices)),
        "triangleCount": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "windingConsistent": bool(mesh.is_winding_consistent),
        "finiteCoordinates": finite,
        "degenerateTriangleCount": int(np.count_nonzero(~np.isfinite(areas) | (areas <= 1e-12))),
        **audit,
        "bounds": np.round(np.asarray(mesh.bounds, dtype=np.float64), 9).tolist(),
    }


def topology_passed(records: list[dict[str, object]]) -> bool:
    return all(
        record["watertight"]
        and record["windingConsistent"]
        and record["finiteCoordinates"]
        and record["degenerateTriangleCount"] == 0
        and record["boundaryEdgeCount"] == 0
        and record["nonManifoldEdgeCount"] == 0
        for record in records
    )


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
) -> dict[str, object]:
    base_projection = rasterize_top([base_mesh])
    component_projection = rasterize_top(component.mesh for component in components)
    assembled_projection = np.logical_or(base_projection, component_projection)
    base = _metrics(planform.mask, base_projection)
    component = _metrics(planform.mask, component_projection)
    assembled = _metrics(planform.mask, assembled_projection)
    inside = int(np.logical_and(component_projection, base_projection).sum())
    beyond = int(np.logical_and(component_projection, ~base_projection).sum())
    component_pixels = int(component_projection.sum())
    exterior = np.logical_and(component_projection, ~planform.mask)
    return {
        **assembled,
        "authorityExteriorSpillFraction": round(
            float(exterior.sum()) / max(float(planform.mask.sum()), 1.0), 6
        ),
        "iouDecomposition": {
            "baseOnlyIoU": base["silhouetteIoU"],
            "componentsOnlyIoU": component["silhouetteIoU"],
            "assembledIoU": assembled["silhouetteIoU"],
            "assembledMinusBaseIoU": round(assembled["silhouetteIoU"] - base["silhouetteIoU"], 6),
            "componentProjectionPixelCount": component_pixels,
            "componentPixelsInsideBaseProjection": inside,
            "componentPixelsBeyondBaseProjection": beyond,
            "componentInsideBaseFraction": round(inside / max(component_pixels, 1), 6),
            "componentBeyondBaseFraction": round(beyond / max(component_pixels, 1), 6),
            "normalization": "component projection pixel count on the governed 384x384 work grid",
        },
    }


def semantic_height_bands(
    meshes: dict[str, trimesh.Trimesh], model: dict[str, object]
) -> dict[str, object]:
    peaks = {name: float(mesh.bounds[1, 2]) for name, mesh in meshes.items()}
    threshold = float(model["minimumSeparation"])
    ordered_peaks = sorted(peaks.items(), key=lambda item: (item[1], item[0]))
    clusters: list[list[tuple[str, float]]] = []
    for item in ordered_peaks:
        if not clusters or item[1] - clusters[-1][-1][1] >= threshold:
            clusters.append([item])
        else:
            clusters[-1].append(item)
    bands = [
        {
            "index": index,
            "members": [name for name, _ in cluster],
            "minimumPeak": round(cluster[0][1], 6),
            "maximumPeak": round(cluster[-1][1], 6),
        }
        for index, cluster in enumerate(clusters)
    ]
    group_peaks = {
        group: max(peaks[name] for name in members)
        for group, members in model["groups"].items()
    }
    group_order = ["shell", "body", "semanticPeak"]
    separations = [
        group_peaks[second] - group_peaks[first]
        for first, second in zip(group_order, group_order[1:])
    ]
    ordered = all(value >= threshold for value in separations)
    return {
        "measurementSource": "independently reloaded GLB geometry bounds in target XYZ",
        "minimumRequiredBandCount": int(model["minimumBandCount"]),
        "clusteringSeparationThreshold": threshold,
        "componentPeaks": {name: round(value, 6) for name, value in sorted(peaks.items())},
        "bands": bands,
        "bandCount": len(bands),
        "semanticGroups": {name: list(members) for name, members in model["groups"].items()},
        "semanticGroupPeaks": {name: round(value, 6) for name, value in group_peaks.items()},
        "minimumAdjacentSeparation": round(min(separations), 6),
        "ordered": ordered,
    }


def attachment_metrics(base_mesh: trimesh.Trimesh, component_mesh: trimesh.Trimesh) -> dict[str, object]:
    base = np.asarray(base_mesh.vertices, dtype=np.float64)
    vertices = np.asarray(component_mesh.vertices, dtype=np.float64)
    embedded: list[bool] = []
    exposed: list[bool] = []
    protrusions: list[float] = []
    nearest_3d = float("inf")
    neighbour_count = int(ATTACHMENT_THRESHOLDS["xyNeighbourCount"])
    tolerance = float(ATTACHMENT_THRESHOLDS["surfaceTolerance"])
    for vertex in vertices:
        xy_distance = np.square(base[:, 0] - vertex[0]) + np.square(base[:, 1] - vertex[1])
        count = min(neighbour_count, len(base))
        nearest = np.argpartition(xy_distance, count - 1)[:count]
        local_z = base[nearest, 2]
        lower, upper = float(local_z.min()), float(local_z.max())
        embedded.append(lower + tolerance < vertex[2] < upper - tolerance)
        distance_outside = max(vertex[2] - upper, lower - vertex[2], 0.0)
        exposed.append(distance_outside > tolerance)
        protrusions.append(distance_outside)
        nearest_3d = min(nearest_3d, float(np.sqrt(np.min(np.sum(np.square(base[nearest] - vertex), axis=1)))))
    embedded_fraction = float(np.mean(embedded))
    exposed_fraction = float(np.mean(exposed))
    entirely_buried = exposed_fraction < float(ATTACHMENT_THRESHOLDS["minimumExposedFraction"])
    entirely_detached = embedded_fraction < float(ATTACHMENT_THRESHOLDS["minimumEmbeddedFraction"])
    return {
        "measurementMethod": "component vertices against the local two-sided base-shell envelope",
        "thresholds": ATTACHMENT_THRESHOLDS,
        "embeddedVertexFraction": round(embedded_fraction, 6),
        "exposedVertexFraction": round(exposed_fraction, 6),
        "maximumProtrusion": round(max(protrusions), 7),
        "representativeProtrusion": round(float(np.mean([v for v in protrusions if v > 0]) if any(exposed) else 0.0), 7),
        "nearestShellVertexDistance": round(nearest_3d, 7),
        "entirelyBuriedOrContained": entirely_buried,
        "entirelyDetachedOrFloating": entirely_detached,
        "validEmbeddedAndExposedAttachment": not entirely_buried and not entirely_detached,
    }


def component_record(component: PlacedComponent, base_mesh: trimesh.Trimesh) -> dict[str, object]:
    mesh = component.mesh
    topology = topology_record(component.name, mesh)
    return {
        "name": component.name,
        "shape": component.shape,
        "transform": {
            "translationTargetXYZ": [round(value, 7) for value in component.centre],
            "rotationDegreesTargetXYZ": [0.0, 0.0, 0.0],
        },
        "dimensionsLengthWidthHeight": [round(value, 7) for value in component.dimensions],
        **{key: value for key, value in topology.items() if key not in {"name", "bounds"}},
        "volume": round(float(abs(mesh.volume)), 9),
        "declaredAttachmentPenetration": round(component.attachment_penetration, 7),
        "attachmentMeasurement": attachment_metrics(base_mesh, mesh),
        "minimumVolume": component.minimum_volume,
        "minimumTriangles": component.minimum_triangles,
        "underside": component.underside,
    }


def gate_results(
    recipe: dict,
    records: list[dict[str, object]],
    identity: dict[str, object],
    heights: dict[str, object],
    reload_audit: dict[str, object],
    legacy_gates_passed: bool,
) -> dict[str, object]:
    count = len(records) + 1
    decomposition = identity["iouDecomposition"]
    checks = {
        "componentCountRange": recipe["componentCount"]["minimum"] <= count <= recipe["componentCount"]["maximum"],
        "individualWatertight": all(record["watertight"] for record in records),
        "individualWindingConsistent": all(record["windingConsistent"] for record in records),
        "noBoundaryEdges": all(record["boundaryEdgeCount"] == 0 for record in records),
        "noNonManifoldEdges": all(record["nonManifoldEdgeCount"] == 0 for record in records),
        "minimumVolumes": all(record["volume"] >= record["minimumVolume"] for record in records),
        "minimumTriangles": all(record["triangleCount"] >= record["minimumTriangles"] for record in records),
        "measuredEmbeddedAndExposedAttachment": all(
            record["attachmentMeasurement"]["validEmbeddedAndExposedAttachment"] for record in records
        ),
        "noBuriedOrDetachedComponents": all(
            not record["attachmentMeasurement"]["entirelyBuriedOrContained"]
            and not record["attachmentMeasurement"]["entirelyDetachedOrFloating"]
            for record in records
        ),
        "glbReloadComponentCount": reload_audit["componentCountAfter"] == count,
        "glbReloadGeometryNames": bool(reload_audit["geometryNamesMatch"]),
        "glbReloadCoordinateBounds": reload_audit["coordinateBoundsDelta"] <= 1e-5,
        "glbReloadTopology": bool(reload_audit["topologyPassed"]),
        "assembledSilhouetteFloor": identity["silhouetteIoU"] >= 0.94,
        "silhouetteIoUDegradationBudget": decomposition["assembledMinusBaseIoU"] >= -0.005,
        "authorityExteriorSpill": identity["authorityExteriorSpillFraction"] <= recipe["allowedTopProjectionSpillFraction"],
        "widthProfileMAE": identity["widthProfileMAE"] <= ACCEPTANCE_GATES["widthProfileMAEMax"],
        "semanticHeightBands": bool(heights["ordered"])
        and int(heights["bandCount"]) >= int(heights["minimumRequiredBandCount"]),
        "baseShellOriginalGates": legacy_gates_passed,
    }
    return {"checks": checks, "passed": all(checks.values())}
