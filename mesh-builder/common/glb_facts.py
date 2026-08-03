from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from typing import Any

_COMPONENT_FORMAT = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
_COMPONENT_SIZE = {key: struct.calcsize("<" + value) for key, value in _COMPONENT_FORMAT.items()}
_TYPE_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


class GlbFactsError(ValueError):
    """Raised when a GLB cannot satisfy the producer-side VMP inspection contract."""


@dataclass(frozen=True)
class GlbFacts:
    vertex_count: int
    triangle_count: int
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    material_count: int
    image_count: int
    mesh_count: int


def parse_glb_facts(data: bytes) -> GlbFacts:
    if len(data) < 20 or data[:4] != b"glTF":
        raise GlbFactsError("normalized mesh is not GLB 2.0")
    version, declared = struct.unpack_from("<II", data, 4)
    if version != 2 or declared != len(data):
        raise GlbFactsError("GLB version or declared length is invalid")
    offset = 12
    document: dict[str, Any] | None = None
    binary = b""
    while offset + 8 <= len(data):
        length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + length]
        offset += length
        if len(chunk) != length:
            raise GlbFactsError("GLB chunk is truncated")
        if chunk_type == 0x4E4F534A:
            try:
                parsed = json.loads(chunk.rstrip(b" \t\r\n\x00"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise GlbFactsError("GLB JSON chunk is invalid") from exc
            if not isinstance(parsed, dict):
                raise GlbFactsError("GLB JSON root is not an object")
            document = parsed
        elif chunk_type == 0x004E4942:
            binary = chunk
    if offset != len(data) or document is None:
        raise GlbFactsError("GLB is structurally incomplete")
    for collection in ("buffers", "images"):
        for item in document.get(collection, []):
            if isinstance(item, dict) and "uri" in item:
                raise GlbFactsError(f"external {collection[:-1]} URI is prohibited")
    buffers = document.get("buffers", [])
    if len(buffers) != 1 or int(buffers[0].get("byteLength", -1)) > len(binary):
        raise GlbFactsError("GLB binary buffer declaration is invalid")

    primitives: list[dict[str, Any]] = []
    for mesh in document.get("meshes", []):
        if isinstance(mesh, dict):
            primitives.extend(item for item in mesh.get("primitives", []) if isinstance(item, dict))
    if not primitives:
        raise GlbFactsError("GLB contains no mesh primitives")

    total_vertices = 0
    total_triangles = 0
    bounds_min = [float("inf")] * 3
    bounds_max = [float("-inf")] * 3
    for primitive in primitives:
        if primitive.get("mode", 4) != 4:
            raise GlbFactsError("only triangle primitives are supported")
        attributes = primitive.get("attributes")
        if not isinstance(attributes, dict) or "POSITION" not in attributes or "indices" not in primitive:
            raise GlbFactsError("primitive lacks positions or indices")
        positions = _accessor_values(document, binary, int(attributes["POSITION"]))
        indices = _accessor_values(document, binary, int(primitive["indices"]))
        if not positions or not indices or len(indices) % 3:
            raise GlbFactsError("primitive accessor is empty or index count is invalid")
        if max(int(value[0]) for value in indices) >= len(positions):
            raise GlbFactsError("index references a missing vertex")
        total_vertices += len(positions)
        total_triangles += len(indices) // 3
        for vector in positions:
            if len(vector) != 3:
                raise GlbFactsError("position accessor is not VEC3")
            for axis in range(3):
                bounds_min[axis] = min(bounds_min[axis], float(vector[axis]))
                bounds_max[axis] = max(bounds_max[axis], float(vector[axis]))
    return GlbFacts(
        vertex_count=total_vertices,
        triangle_count=total_triangles,
        bounds_min=tuple(bounds_min),
        bounds_max=tuple(bounds_max),
        material_count=len(document.get("materials", [])),
        image_count=len(document.get("images", [])),
        mesh_count=len(document.get("meshes", [])),
    )


def _accessor_values(
    document: dict[str, Any], binary: bytes, accessor_index: int
) -> list[tuple[float | int, ...]]:
    accessors = document.get("accessors", [])
    views = document.get("bufferViews", [])
    if accessor_index < 0 or accessor_index >= len(accessors):
        raise GlbFactsError("accessor index is invalid")
    accessor = accessors[accessor_index]
    if not isinstance(accessor, dict) or "sparse" in accessor:
        raise GlbFactsError("sparse or invalid accessors are unsupported")
    view_index = accessor.get("bufferView")
    if not isinstance(view_index, int) or view_index < 0 or view_index >= len(views):
        raise GlbFactsError("accessor bufferView is invalid")
    view = views[view_index]
    if not isinstance(view, dict):
        raise GlbFactsError("bufferView is invalid")
    component_type = int(accessor.get("componentType", 0))
    value_type = accessor.get("type")
    if component_type not in _COMPONENT_FORMAT or value_type not in _TYPE_WIDTH:
        raise GlbFactsError("accessor component or vector type is unsupported")
    count = int(accessor.get("count", -1))
    if count < 0:
        raise GlbFactsError("accessor count is invalid")
    width = _TYPE_WIDTH[value_type]
    element_size = _COMPONENT_SIZE[component_type] * width
    stride = int(view.get("byteStride", element_size))
    if stride < element_size:
        raise GlbFactsError("accessor byteStride is invalid")
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    if count:
        end = start + (count - 1) * stride + element_size
        if start < 0 or end > len(binary):
            raise GlbFactsError("accessor exceeds binary chunk")
    fmt = "<" + _COMPONENT_FORMAT[component_type] * width
    return [struct.unpack_from(fmt, binary, start + index * stride) for index in range(count)]
