from __future__ import annotations

import hashlib
import json
import math
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
    file_byte_length: int = 0
    glb_version: int = 2
    primitive_count: int = 0
    texture_count: int = 0
    uv_primitive_count: int = 0
    normal_primitive_count: int = 0
    tangent_primitive_count: int = 0
    animation_count: int = 0
    skin_count: int = 0
    node_count: int = 0
    scene_count: int = 0
    alpha_modes: tuple[str, ...] = ()
    image_mime_types: tuple[str, ...] = ()
    image_dimensions: tuple[tuple[int, int] | None, ...] = ()
    image_sha256: tuple[str | None, ...] = ()
    material_texture_channels: tuple[dict[str, int], ...] = ()
    extensions_used: tuple[str, ...] = ()
    suspicious_extensions: tuple[str, ...] = ()
    sparse_accessor_count: int = 0
    external_uris: tuple[str, ...] = ()


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
    external_uris: list[str] = []
    for collection in ("buffers", "images"):
        for item in document.get(collection, []):
            if isinstance(item, dict) and "uri" in item:
                external_uris.append(str(item["uri"]))
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
    uv_count = normal_count = tangent_count = 0
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
        uv_count += int("TEXCOORD_0" in attributes)
        normal_count += int("NORMAL" in attributes)
        tangent_count += int("TANGENT" in attributes)
        for vector in positions:
            if len(vector) != 3:
                raise GlbFactsError("position accessor is not VEC3")
            for axis in range(3):
                value = float(vector[axis])
                if not math.isfinite(value):
                    raise GlbFactsError("position accessor contains non-finite geometry")
                bounds_min[axis] = min(bounds_min[axis], value)
                bounds_max[axis] = max(bounds_max[axis], value)
    extensions = tuple(sorted(str(value) for value in document.get("extensionsUsed", []) if isinstance(value, str)))
    supported_extensions = {"KHR_materials_unlit", "KHR_materials_emissive_strength", "KHR_texture_transform"}
    image_mimes: list[str] = []
    image_dimensions: list[tuple[int, int] | None] = []
    image_hashes: list[str | None] = []
    for image in document.get("images", []):
        if not isinstance(image, dict):
            raise GlbFactsError("image record is invalid")
        mime = str(image.get("mimeType") or "")
        image_mimes.append(mime)
        payload = _embedded_image_payload(document, binary, image)
        image_dimensions.append(_image_dimensions(payload))
        image_hashes.append(hashlib.sha256(payload).hexdigest() if payload is not None else None)
    channels: list[dict[str, int]] = []
    for material in document.get("materials", []):
        if not isinstance(material, dict):
            raise GlbFactsError("material record is invalid")
        refs: dict[str, int] = {}
        pbr = material.get("pbrMetallicRoughness", {})
        if isinstance(pbr, dict):
            _texture_ref(refs, "baseColor", pbr.get("baseColorTexture"), document)
            _texture_ref(refs, "metallicRoughness", pbr.get("metallicRoughnessTexture"), document)
        for key, field in (("normal", "normalTexture"), ("emissive", "emissiveTexture"), ("occlusion", "occlusionTexture")):
            _texture_ref(refs, key, material.get(field), document)
        channels.append(refs)
    return GlbFacts(
        vertex_count=total_vertices,
        triangle_count=total_triangles,
        bounds_min=tuple(bounds_min),
        bounds_max=tuple(bounds_max),
        material_count=len(document.get("materials", [])),
        image_count=len(document.get("images", [])),
        mesh_count=len(document.get("meshes", [])),
        file_byte_length=len(data),
        primitive_count=len(primitives),
        texture_count=len(document.get("textures", [])),
        uv_primitive_count=uv_count,
        normal_primitive_count=normal_count,
        tangent_primitive_count=tangent_count,
        animation_count=len(document.get("animations", [])),
        skin_count=len(document.get("skins", [])),
        node_count=len(document.get("nodes", [])),
        scene_count=len(document.get("scenes", [])),
        alpha_modes=tuple(sorted({str(item.get("alphaMode", "OPAQUE")) for item in document.get("materials", []) if isinstance(item, dict)})),
        image_mime_types=tuple(image_mimes),
        image_dimensions=tuple(image_dimensions),
        image_sha256=tuple(image_hashes),
        material_texture_channels=tuple(channels),
        extensions_used=extensions,
        suspicious_extensions=tuple(value for value in extensions if value not in supported_extensions),
        sparse_accessor_count=sum(int(isinstance(item, dict) and "sparse" in item) for item in document.get("accessors", [])),
        external_uris=tuple(external_uris),
    )


def _texture_ref(result: dict[str, int], channel: str, record: Any, document: dict[str, Any]) -> None:
    if record is None:
        return
    if not isinstance(record, dict) or not isinstance(record.get("index"), int):
        raise GlbFactsError(f"material {channel} texture reference is invalid")
    index = int(record["index"])
    if index < 0 or index >= len(document.get("textures", [])):
        raise GlbFactsError(f"material {channel} texture index is invalid")
    result[channel] = index


def _embedded_image_payload(
    document: dict[str, Any], binary: bytes, image: dict[str, Any]
) -> bytes | None:
    view_index = image.get("bufferView")
    if not isinstance(view_index, int):
        return None
    views = document.get("bufferViews", [])
    if view_index < 0 or view_index >= len(views) or not isinstance(views[view_index], dict):
        raise GlbFactsError("image bufferView is invalid")
    view = views[view_index]
    start = int(view.get("byteOffset", 0))
    length = int(view.get("byteLength", -1))
    if start < 0 or length < 0 or start + length > len(binary):
        raise GlbFactsError("embedded image exceeds binary chunk")
    return binary[start : start + length]


def _image_dimensions(payload: bytes | None) -> tuple[int, int] | None:
    if payload is None:
        return None
    if payload.startswith(b"\x89PNG\r\n\x1a\n") and len(payload) >= 24:
        return struct.unpack_from(">II", payload, 16)
    if payload.startswith(b"\xff\xd8"):
        offset = 2
        while offset + 9 <= len(payload):
            if payload[offset] != 0xFF:
                offset += 1
                continue
            marker = payload[offset + 1]
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                height, width = struct.unpack_from(">HH", payload, offset + 5)
                return width, height
            if marker in {0xD8, 0xD9}:
                offset += 2
            else:
                segment = struct.unpack_from(">H", payload, offset + 2)[0]
                if segment < 2:
                    raise GlbFactsError("embedded JPEG is malformed")
                offset += 2 + segment
    return None


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
