from __future__ import annotations

import io
import json
import math
import struct
from pathlib import Path
from typing import Any

from PIL import Image

_COMPONENT_FORMAT = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
_COMPONENT_SIZE = {key: struct.calcsize("<" + value) for key, value in _COMPONENT_FORMAT.items()}
_TYPE_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


class MeshEquivalenceError(ValueError):
    """Raised when a GLB cannot be compared under the frozen WP2 contract."""


def compare_mesh_semantics(
    baseline_mesh: Path,
    adapter_mesh: Path,
    baseline_report: Path,
    adapter_report: Path,
    *,
    y_max_abs_limit: float = 1e-5,
    y_rms_limit: float = 1e-6,
) -> dict[str, Any]:
    baseline = _snapshot(baseline_mesh)
    adapter = _snapshot(adapter_mesh)
    baseline_report_data = _read_report(baseline_report)
    adapter_report_data = _read_report(adapter_report)

    shape_compatible = len(baseline["positions"]) == len(adapter["positions"])
    if shape_compatible:
        y_deltas = [
            abs(float(after[1]) - float(before[1]))
            for before, after in zip(baseline["positions"], adapter["positions"], strict=True)
        ]
    else:
        y_deltas = [float("inf")]
    y_max_abs = max(y_deltas, default=0.0)
    y_rms = math.sqrt(sum(delta * delta for delta in y_deltas) / len(y_deltas)) if y_deltas else 0.0

    checks = {
        "indicesExact": baseline["indices"] == adapter["indices"],
        "xFloat32Exact": _axis_bytes(baseline["positions"], 0) == _axis_bytes(adapter["positions"], 0),
        "zFloat32Exact": _axis_bytes(baseline["positions"], 2) == _axis_bytes(adapter["positions"], 2),
        "uvFloat32Exact": _vector_bytes(baseline["texcoords"], 2) == _vector_bytes(adapter["texcoords"], 2),
        "decodedTexturePixelsExact": baseline["textures"] == adapter["textures"],
        "topologyExact": baseline["primitiveTopology"] == adapter["primitiveTopology"],
        "countsExact": baseline["counts"] == adapter["counts"],
        "boundsExact": baseline["boundsFloat32"] == adapter["boundsFloat32"],
        "frameEvidenceExact": _frame_evidence(baseline_report_data) == _frame_evidence(adapter_report_data),
        "gateResultsExact": baseline_report_data.get("gateResults") == adapter_report_data.get("gateResults"),
        "gateResultsPassed": bool(adapter_report_data.get("gateResults", {}).get("passed")),
        "yMaxAbsWithinLimit": y_max_abs <= y_max_abs_limit,
        "yRmsWithinLimit": y_rms <= y_rms_limit,
    }
    return {
        "schemaVersion": "skyforge.mesh-semantic-equivalence.v1",
        "contract": {
            "indices": "exact",
            "xAndZFloat32": "exact",
            "uvFloat32": "exact",
            "decodedTexturePixels": "exact",
            "topologyCountsBoundsFrameAndGates": "exact",
            "yMaxAbsLimit": y_max_abs_limit,
            "yRmsLimit": y_rms_limit,
        },
        "metrics": {
            "yMaxAbsoluteDelta": y_max_abs,
            "yRmsDelta": y_rms,
            "baselineCounts": baseline["counts"],
            "adapterCounts": adapter["counts"],
        },
        "checks": checks,
        "passed": all(checks.values()),
    }


def _read_report(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MeshEquivalenceError(f"Invalid generation report: {path}") from exc
    if not isinstance(value, dict):
        raise MeshEquivalenceError(f"Generation report root is not an object: {path}")
    return value


def _frame_evidence(report: dict[str, Any]) -> dict[str, Any]:
    mesh = report.get("mesh")
    if not isinstance(mesh, dict):
        raise MeshEquivalenceError("Generation report lacks mesh evidence")
    coordinate = mesh.get("coordinateContract")
    if not isinstance(coordinate, dict):
        raise MeshEquivalenceError("Generation report lacks coordinate-contract evidence")
    return {
        "coordinateContract": coordinate,
        "identityMetricSource": report.get("identityMetricSource"),
        "blenderImportIdentityMetrics": report.get("blenderImportIdentityMetrics"),
    }


def _snapshot(path: Path) -> dict[str, Any]:
    document, binary = _parse_glb(path.read_bytes())
    positions: list[tuple[float | int, ...]] = []
    texcoords: list[tuple[float | int, ...]] = []
    indices: list[tuple[int, ...]] = []
    topology: list[dict[str, int]] = []
    textures: list[dict[str, Any]] = []

    meshes = document.get("meshes", [])
    if not isinstance(meshes, list) or not meshes:
        raise MeshEquivalenceError("GLB contains no meshes")
    for mesh in meshes:
        if not isinstance(mesh, dict):
            raise MeshEquivalenceError("GLB mesh entry is invalid")
        primitives = mesh.get("primitives", [])
        if not isinstance(primitives, list):
            raise MeshEquivalenceError("GLB primitive collection is invalid")
        for primitive in primitives:
            if not isinstance(primitive, dict) or primitive.get("mode", 4) != 4:
                raise MeshEquivalenceError("Only triangle primitives are supported")
            attributes = primitive.get("attributes")
            if not isinstance(attributes, dict):
                raise MeshEquivalenceError("Primitive attributes are invalid")
            if "POSITION" not in attributes or "TEXCOORD_0" not in attributes or "indices" not in primitive:
                raise MeshEquivalenceError("Primitive lacks POSITION, TEXCOORD_0, or indices")
            primitive_positions = _accessor_values(document, binary, int(attributes["POSITION"]))
            primitive_uvs = _accessor_values(document, binary, int(attributes["TEXCOORD_0"]))
            primitive_indices = _accessor_values(document, binary, int(primitive["indices"]))
            if len(primitive_positions) != len(primitive_uvs) or len(primitive_indices) % 3:
                raise MeshEquivalenceError("Primitive accessor cardinality is invalid")
            positions.extend(primitive_positions)
            texcoords.extend(primitive_uvs)
            flat_indices = tuple(int(item[0]) for item in primitive_indices)
            indices.append(flat_indices)
            topology.append(
                {
                    "vertexCount": len(primitive_positions),
                    "indexCount": len(flat_indices),
                    "triangleCount": len(flat_indices) // 3,
                }
            )
            textures.append(_primitive_texture(document, binary, primitive))

    if not positions:
        raise MeshEquivalenceError("GLB contains no positions")
    bounds = tuple(
        struct.pack("<f", float(value))
        for value in (
            min(float(item[0]) for item in positions),
            min(float(item[1]) for item in positions),
            min(float(item[2]) for item in positions),
            max(float(item[0]) for item in positions),
            max(float(item[1]) for item in positions),
            max(float(item[2]) for item in positions),
        )
    )
    return {
        "positions": tuple(positions),
        "texcoords": tuple(texcoords),
        "indices": tuple(indices),
        "primitiveTopology": tuple(tuple(sorted(item.items())) for item in topology),
        "textures": tuple(_freeze_texture(item) for item in textures),
        "boundsFloat32": bounds,
        "counts": {
            "meshCount": len(meshes),
            "primitiveCount": len(topology),
            "vertexCount": len(positions),
            "triangleCount": sum(item["triangleCount"] for item in topology),
            "materialCount": len(document.get("materials", [])),
            "imageCount": len(document.get("images", [])),
        },
    }


def _freeze_texture(texture: dict[str, Any]) -> tuple[Any, ...]:
    return (
        texture["size"],
        texture["mode"],
        texture["pixels"],
    )


def _primitive_texture(document: dict[str, Any], binary: bytes, primitive: dict[str, Any]) -> dict[str, Any]:
    materials = document.get("materials", [])
    textures = document.get("textures", [])
    images = document.get("images", [])
    material_index = primitive.get("material")
    if not isinstance(material_index, int) or material_index < 0 or material_index >= len(materials):
        raise MeshEquivalenceError("Primitive material is missing or invalid")
    material = materials[material_index]
    try:
        texture_index = int(material["pbrMetallicRoughness"]["baseColorTexture"]["index"])
        image_index = int(textures[texture_index]["source"])
        image = images[image_index]
        view_index = int(image["bufferView"])
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise MeshEquivalenceError("Primitive base-colour texture is invalid") from exc
    views = document.get("bufferViews", [])
    if view_index < 0 or view_index >= len(views):
        raise MeshEquivalenceError("Texture bufferView is invalid")
    view = views[view_index]
    start = int(view.get("byteOffset", 0))
    length = int(view.get("byteLength", -1))
    if start < 0 or length < 0 or start + length > len(binary):
        raise MeshEquivalenceError("Texture bufferView exceeds binary chunk")
    try:
        with Image.open(io.BytesIO(binary[start : start + length])) as opened:
            decoded = opened.convert("RGBA")
            return {"size": decoded.size, "mode": decoded.mode, "pixels": decoded.tobytes()}
    except OSError as exc:
        raise MeshEquivalenceError("Embedded texture cannot be decoded") from exc


def _parse_glb(data: bytes) -> tuple[dict[str, Any], bytes]:
    if len(data) < 20 or data[:4] != b"glTF":
        raise MeshEquivalenceError("Mesh is not GLB 2.0")
    version, declared = struct.unpack_from("<II", data, 4)
    if version != 2 or declared != len(data):
        raise MeshEquivalenceError("GLB version or declared length is invalid")
    offset = 12
    document: dict[str, Any] | None = None
    binary = b""
    while offset + 8 <= len(data):
        length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + length]
        offset += length
        if len(chunk) != length:
            raise MeshEquivalenceError("GLB chunk is truncated")
        if chunk_type == 0x4E4F534A:
            try:
                parsed = json.loads(chunk.rstrip(b" \t\r\n\x00"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise MeshEquivalenceError("GLB JSON chunk is invalid") from exc
            if not isinstance(parsed, dict):
                raise MeshEquivalenceError("GLB JSON root is invalid")
            document = parsed
        elif chunk_type == 0x004E4942:
            binary = chunk
    if offset != len(data) or document is None:
        raise MeshEquivalenceError("GLB is structurally incomplete")
    return document, binary


def _accessor_values(
    document: dict[str, Any], binary: bytes, accessor_index: int
) -> list[tuple[float | int, ...]]:
    accessors = document.get("accessors", [])
    views = document.get("bufferViews", [])
    if accessor_index < 0 or accessor_index >= len(accessors):
        raise MeshEquivalenceError("Accessor index is invalid")
    accessor = accessors[accessor_index]
    if not isinstance(accessor, dict) or "sparse" in accessor:
        raise MeshEquivalenceError("Sparse or invalid accessors are unsupported")
    view_index = accessor.get("bufferView")
    if not isinstance(view_index, int) or view_index < 0 or view_index >= len(views):
        raise MeshEquivalenceError("Accessor bufferView is invalid")
    view = views[view_index]
    component_type = int(accessor.get("componentType", 0))
    value_type = accessor.get("type")
    if component_type not in _COMPONENT_FORMAT or value_type not in _TYPE_WIDTH:
        raise MeshEquivalenceError("Accessor component or vector type is unsupported")
    count = int(accessor.get("count", -1))
    width = _TYPE_WIDTH[value_type]
    element_size = _COMPONENT_SIZE[component_type] * width
    stride = int(view.get("byteStride", element_size))
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    if count < 0 or stride < element_size:
        raise MeshEquivalenceError("Accessor count or stride is invalid")
    if count and start + (count - 1) * stride + element_size > len(binary):
        raise MeshEquivalenceError("Accessor exceeds binary chunk")
    fmt = "<" + _COMPONENT_FORMAT[component_type] * width
    return [struct.unpack_from(fmt, binary, start + index * stride) for index in range(count)]


def _axis_bytes(values: tuple[tuple[float | int, ...], ...], axis: int) -> bytes:
    return b"".join(struct.pack("<f", float(value[axis])) for value in values)


def _vector_bytes(values: tuple[tuple[float | int, ...], ...], width: int) -> bytes:
    return b"".join(struct.pack("<" + "f" * width, *(float(item) for item in value[:width])) for value in values)
