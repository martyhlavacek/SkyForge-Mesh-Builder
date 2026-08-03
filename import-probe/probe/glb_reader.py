from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from typing import Any

from .errors import ProbeReject

COMPONENT_FORMAT = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
COMPONENT_SIZE = {key: struct.calcsize("<" + value) for key, value in COMPONENT_FORMAT.items()}
TYPE_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


@dataclass(frozen=True)
class GlbFacts:
    vertex_count: int
    triangle_count: int
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    material_count: int
    image_count: int
    mesh_count: int
    json_document: dict[str, Any]
    binary_chunk: bytes


def parse_glb(data: bytes) -> GlbFacts:
    if len(data) < 20 or data[:4] != b"glTF":
        raise ProbeReject("glb_header", "normalized mesh is not GLB 2.0")
    version, declared = struct.unpack_from("<II", data, 4)
    if version != 2 or declared != len(data):
        raise ProbeReject("glb_header", "GLB version or declared length is invalid")
    offset = 12
    document = None
    binary = b""
    while offset + 8 <= len(data):
        length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + length]
        offset += length
        if len(chunk) != length:
            raise ProbeReject("glb_truncated", "GLB chunk is truncated")
        if chunk_type == 0x4E4F534A:
            try:
                document = json.loads(chunk.rstrip(b" \t\r\n\x00"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProbeReject("glb_json", "GLB JSON chunk is invalid") from exc
        elif chunk_type == 0x004E4942:
            binary = chunk
    if offset != len(data) or not isinstance(document, dict):
        raise ProbeReject("glb_structure", "GLB is structurally incomplete")
    for collection in ("buffers", "images"):
        for item in document.get(collection, []):
            if isinstance(item, dict) and "uri" in item:
                raise ProbeReject("glb_external_reference", f"external {collection[:-1]} URI is prohibited")
    buffers = document.get("buffers", [])
    if len(buffers) != 1 or int(buffers[0].get("byteLength", -1)) > len(binary):
        raise ProbeReject("glb_buffer", "GLB binary buffer declaration is invalid")

    total_vertices = 0
    total_triangles = 0
    bounds_min = [float("inf")] * 3
    bounds_max = [float("-inf")] * 3
    primitives = []
    for mesh in document.get("meshes", []):
        primitives.extend(mesh.get("primitives", []))
    if not primitives:
        raise ProbeReject("glb_mesh_missing", "GLB contains no mesh primitives")
    for primitive in primitives:
        if primitive.get("mode", 4) != 4:
            raise ProbeReject("glb_topology_mode", "only triangle primitives are supported")
        attributes = primitive.get("attributes", {})
        if "POSITION" not in attributes or "indices" not in primitive:
            raise ProbeReject("glb_accessor_missing", "primitive lacks positions or indices")
        positions = _accessor_values(document, binary, int(attributes["POSITION"]))
        indices = _accessor_values(document, binary, int(primitive["indices"]))
        if not positions or not indices:
            raise ProbeReject("glb_accessor_empty", "primitive accessor is empty")
        if len(indices) % 3:
            raise ProbeReject("glb_index_count", "index count is not divisible by three")
        if max(int(value[0]) for value in indices) >= len(positions):
            raise ProbeReject("glb_index_range", "index references a missing vertex")
        total_vertices += len(positions)
        total_triangles += len(indices) // 3
        for vector in positions:
            if len(vector) != 3:
                raise ProbeReject("glb_position_width", "position accessor is not VEC3")
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
        json_document=document,
        binary_chunk=binary,
    )


def embedded_images(facts: GlbFacts) -> list[tuple[str, bytes]]:
    values: list[tuple[str, bytes]] = []
    views = facts.json_document.get("bufferViews", [])
    for image in facts.json_document.get("images", []):
        if "bufferView" not in image:
            raise ProbeReject("glb_external_reference", "image is not embedded in GLB buffer")
        index = int(image["bufferView"])
        if index < 0 or index >= len(views):
            raise ProbeReject("glb_image_view", "image bufferView is invalid")
        view = views[index]
        start = int(view.get("byteOffset", 0))
        end = start + int(view.get("byteLength", 0))
        if start < 0 or end > len(facts.binary_chunk):
            raise ProbeReject("glb_image_view", "image bufferView exceeds binary chunk")
        values.append((str(image.get("mimeType", "")), facts.binary_chunk[start:end]))
    return values


def _accessor_values(document: dict[str, Any], binary: bytes, accessor_index: int) -> list[tuple[float | int, ...]]:
    accessors = document.get("accessors", [])
    views = document.get("bufferViews", [])
    if accessor_index < 0 or accessor_index >= len(accessors):
        raise ProbeReject("glb_accessor_index", "accessor index is invalid")
    accessor = accessors[accessor_index]
    if "sparse" in accessor:
        raise ProbeReject("glb_sparse_accessor", "sparse accessors are unsupported by VMP v1 probe")
    view_index = accessor.get("bufferView")
    if not isinstance(view_index, int) or view_index < 0 or view_index >= len(views):
        raise ProbeReject("glb_accessor_view", "accessor bufferView is invalid")
    view = views[view_index]
    component_type = int(accessor.get("componentType", 0))
    value_type = accessor.get("type")
    if component_type not in COMPONENT_FORMAT or value_type not in TYPE_WIDTH:
        raise ProbeReject("glb_accessor_type", "accessor component or vector type is unsupported")
    count = int(accessor.get("count", -1))
    if count < 0:
        raise ProbeReject("glb_accessor_count", "accessor count is invalid")
    width = TYPE_WIDTH[value_type]
    element_size = COMPONENT_SIZE[component_type] * width
    stride = int(view.get("byteStride", element_size))
    if stride < element_size:
        raise ProbeReject("glb_accessor_stride", "accessor byteStride is invalid")
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    if count:
        end = start + (count - 1) * stride + element_size
        if start < 0 or end > len(binary):
            raise ProbeReject("glb_accessor_bounds", "accessor exceeds binary chunk")
    fmt = "<" + COMPONENT_FORMAT[component_type] * width
    return [struct.unpack_from(fmt, binary, start + index * stride) for index in range(count)]
