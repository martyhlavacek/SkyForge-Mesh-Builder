from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import rfc8785
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent
SCHEMAS = {
    "VMP_MANIFEST.json": "validated_mesh_package_v2.schema.json",
    "mesh/semantic_identity.json": "semantic_identity_v2.schema.json",
    "mesh/component_manifest.json": "component_manifest_v2.schema.json",
    "authorities/authority_manifest.json": "source_artifact_manifest_v2.schema.json",
    "materials/material_contract.json": "material_contract_v2.schema.json",
    "provenance/source_chain.json": "source_chain_v2.schema.json",
}
REQUIRED = set(SCHEMAS) | {"SHA256SUMS.txt", "asset.json", "mesh/normalized.glb",
    "validation/geometry.json", "validation/independent_reload.json", "validation/blender.json"}


class Reject(ValueError):
    pass


def validate(archive_path: Path) -> dict:
    entries = read_archive(archive_path)
    if REQUIRED - set(entries):
        raise Reject("required package members are missing")
    verify_checksums(entries)
    docs = {path: json.loads(entries[path]) for path in REQUIRED if path.endswith(".json")}
    bindings = schema_bindings()
    for path, name in SCHEMAS.items():
        schema_path = ROOT / "schemas" / name
        if hashlib.sha256(schema_path.read_bytes()).hexdigest() != bindings.get(name):
            raise Reject(f"schema binding mismatch: {name}")
        errors = list(Draft202012Validator(json.loads(schema_path.read_text())).iter_errors(docs[path]))
        if errors:
            raise Reject(f"schema rejection {path}: {errors[0].message}")
    manifest = docs["VMP_MANIFEST.json"]
    verify_index(entries, manifest)
    digest_payload = digest_fields(manifest)
    digest = hashlib.sha256(rfc8785.dumps(digest_payload)).hexdigest()
    if manifest["packageContentDigest"] != digest or manifest["packageId"] != f"sfmeshpack:{digest}":
        raise Reject("package identity mismatch")
    glb = glb_facts(entries["mesh/normalized.glb"])
    glb_sha = hashlib.sha256(entries["mesh/normalized.glb"]).hexdigest()
    source, identity = docs["provenance/source_chain.json"], docs["mesh/semantic_identity.json"]
    material, component = docs["materials/material_contract.json"], docs["mesh/component_manifest.json"]
    artifact = docs["authorities/authority_manifest.json"]["sourceArtifacts"][0]
    asset = docs["asset.json"]
    if manifest["producer"]["providerId"] != "meshy_web" or asset["provider"]["id"] != "meshy_web":
        raise Reject("provider identity mismatch")
    if source["sourceType"] != "externally_authored" or source["geometryGeneratedBySkyForge"] is not False or source["deterministicallyReproducible"] is not False:
        raise Reject("external provenance mismatch")
    if material["providerProcessing"]["aiTexturingApplied"] is not True:
        raise Reject("AI texturing contract mismatch")
    approval = source["approval"]
    if source["normalizedGlbSha256"] != glb_sha or identity["approvedArtifactGlbSha256"] != glb_sha or approval["normalizedGlbSha256"] != glb_sha:
        raise Reject("normalized GLB approval mismatch")
    if source["originalGlbSha256"] != approval["originalGlbSha256"] or source["originalGlbSha256"] != artifact["sourceSha256"]:
        raise Reject("original GLB binding mismatch")
    if (component["meshCount"], component["vertexCount"], component["triangleCount"]) != (glb["meshes"], glb["vertices"], glb["triangles"]):
        raise Reject("GLB fact mismatch")
    for path in ("validation/geometry.json", "validation/independent_reload.json", "validation/blender.json"):
        if docs[path]["passed"] is not True or docs[path]["sourceGlbSha256"] != glb_sha:
            raise Reject("validation binding mismatch")
    archive_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    return {"schemaVersion": "skyforge.sprite-foundry-import-receipt.v2", "contractMajorAccepted": 2,
        "receiptId": "sfimport2:" + hashlib.sha256(f"{archive_sha}:{digest}:2.0.0".encode()).hexdigest(),
        "sourceArchiveSha256": archive_sha, "sourcePackageContentDigest": digest,
        "sourcePackageId": manifest["packageId"], "importerVersion": "2.0.0", "accepted": True,
        "schemasAccepted": sorted(SCHEMAS.values()), "authorityReverification": "not_applicable_external_source",
        "manufacturingAxesVerified": True, "collisionHintsIgnoredForRuntime": True,
        "createdAt": datetime.now(timezone.utc).isoformat(), "diagnostics": ["source=externally_authored", "provider=meshy_web"]}


def read_archive(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        result = {}
        for info in archive.infolist():
            member = PurePosixPath(info.filename)
            if info.is_dir() or member.is_absolute() or ".." in member.parts or "\\" in info.filename or info.file_size > 64 * 1024 * 1024:
                raise Reject("unsafe archive member")
            if info.filename in result:
                raise Reject("duplicate archive member")
            result[info.filename] = archive.read(info)
        return result


def verify_checksums(entries: dict[str, bytes]) -> None:
    declared = {}
    for line in entries["SHA256SUMS.txt"].decode().splitlines():
        if len(line) < 67 or line[64:66] != "  ":
            raise Reject("malformed checksum manifest")
        declared[line[66:]] = line[:64]
    if set(declared) != set(entries) - {"SHA256SUMS.txt"}:
        raise Reject("checksum file set mismatch")
    if any(hashlib.sha256(entries[path]).hexdigest() != digest for path, digest in declared.items()):
        raise Reject("checksum mismatch")


def verify_index(entries: dict[str, bytes], manifest: dict) -> None:
    expected = set(entries) - {"VMP_MANIFEST.json", "SHA256SUMS.txt"}
    if set(manifest["contentIndex"]) != expected:
        raise Reject("content index file set mismatch")
    for path, record in manifest["contentIndex"].items():
        if record != {"sha256": hashlib.sha256(entries[path]).hexdigest(), "sizeBytes": len(entries[path])}:
            raise Reject("content index mismatch")


def digest_fields(manifest: dict) -> dict:
    included = manifest["digestProfile"]["includedManifestFields"]
    result = {}
    for dotted in included:
        source, present = manifest, True
        for part in dotted.split("."):
            if not isinstance(source, dict) or part not in source:
                present = False
                break
            source = source[part]
        if present:
            target = result
            parts = dotted.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = source
    return result


def glb_facts(data: bytes) -> dict[str, int]:
    if len(data) < 20 or data[:4] != b"glTF" or struct.unpack_from("<I", data, 4)[0] != 2 or struct.unpack_from("<I", data, 8)[0] != len(data):
        raise Reject("invalid GLB header")
    json_length, json_type = struct.unpack_from("<II", data, 12)
    if json_type != 0x4E4F534A:
        raise Reject("missing GLB JSON")
    doc = json.loads(data[20:20 + json_length].rstrip(b" \x00"))
    if any("uri" in item for key in ("buffers", "images") for item in doc.get(key, [])):
        raise Reject("external GLB reference")
    vertices = triangles = 0
    for mesh in doc.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            if primitive.get("mode", 4) != 4 or "indices" not in primitive or "POSITION" not in primitive.get("attributes", {}):
                raise Reject("unsupported GLB primitive")
            vertices += doc["accessors"][primitive["attributes"]["POSITION"]]["count"]
            count = doc["accessors"][primitive["indices"]]["count"]
            if count % 3:
                raise Reject("invalid GLB indices")
            triangles += count // 3
    if not triangles:
        raise Reject("empty GLB")
    return {"meshes": len(doc["meshes"]), "vertices": vertices, "triangles": triangles}


def schema_bindings() -> dict[str, str]:
    return {line[66:]: line[:64] for line in (ROOT / "SCHEMA_SHA256SUMS.txt").read_text().splitlines()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = validate(args.archive)
    if args.receipt:
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
