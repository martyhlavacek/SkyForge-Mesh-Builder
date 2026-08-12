from __future__ import annotations

import hashlib
import io
import json
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

from common.canonical_json import canonicalize
from common.schema_validation import ContractValidationError, load_json, validate_document

PACKAGE_VERSION = "1.0.0"
PACKAGE_SCHEMA = "skyforge.validated-mesh-package.v1"
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ALLOWED_SUFFIXES = {".json", ".glb", ".png"}
PROHIBITED_SUFFIXES = {".blend", ".command", ".sh", ".py", ".exe", ".bat", ".cmd", ".app"}

REQUIRED_PAYLOAD_PATHS = frozenset(
    {
        "asset.json",
        "mesh/normalized.glb",
        "mesh/semantic_identity.json",
        "mesh/component_manifest.json",
        "mesh/bounds_and_scale.json",
        "authorities/authority_manifest.json",
        "role/asset_role.json",
        "role/manufacturing_axes.json",
        "role/pivot_contract.json",
        "render/frame_contract.json",
        "materials/material_contract.json",
        "provenance/source_chain.json",
        "licensing_and_terms.json",
        "validation/geometry.json",
        "validation/independent_reload.json",
        "validation/blender.json",
        "previews/gameplay_scale_96.png",
        "previews/silhouette_comparison.png",
        "known_limitations.json",
    }
)

SCHEMA_BY_PATH = {
    "asset.json": "asset_v3.schema.json",
    "mesh/semantic_identity.json": "semantic_identity.schema.json",
    "mesh/component_manifest.json": "component_manifest.schema.json",
    "mesh/bounds_and_scale.json": "bounds_and_scale.schema.json",
    "authorities/authority_manifest.json": "authority_manifest.schema.json",
    "role/asset_role.json": "asset_role.schema.json",
    "role/manufacturing_axes.json": "manufacturing_axes.schema.json",
    "role/pivot_contract.json": "pivot_contract.schema.json",
    "render/frame_contract.json": "frame_contract.schema.json",
    "materials/material_contract.json": "material_contract.schema.json",
    "provenance/source_chain.json": "source_chain.schema.json",
    "licensing_and_terms.json": "licensing_and_terms.schema.json",
    "validation/geometry.json": "validation_report.schema.json",
    "validation/independent_reload.json": "validation_report.schema.json",
    "validation/blender.json": "validation_report.schema.json",
    "known_limitations.json": "known_limitations.schema.json",
}


class VmpBuildError(ValueError):
    """Raised when a package cannot be built without violating VMP v1."""


@dataclass(frozen=True)
class VmpBuildMetadata:
    asset_id: str
    asset_version: str
    craft_profile_id: str
    sidecar_version: str
    provider_id: str
    provider_model: str
    identity_model: str
    authority_set_sha256: str
    minimum_importer_version: str = "1.0.0"
    provider_evidence_package_sha256: str | None = None
    supersedes_package_content_digest: str | None = None
    supersession_reason_code: str | None = None
    material_contract: str = "skyforge.mesh-material.v1"
    package_schema: str = PACKAGE_SCHEMA
    package_version: str = PACKAGE_VERSION


@dataclass(frozen=True)
class VmpBuildResult:
    archive_path: Path
    package_id: str
    package_content_digest: str
    archive_sha256: str
    manifest: dict[str, Any]
    content_index: dict[str, dict[str, Any]]


def build_vmp(payload: Mapping[str, bytes], metadata: VmpBuildMetadata, archive_path: Path) -> VmpBuildResult:
    normalized = _normalize_and_validate_payload(payload)
    _validate_cross_file_contracts(normalized, metadata)
    content_index = {
        path: {"sha256": _sha256(data), "sizeBytes": len(data)}
        for path, data in sorted(normalized.items())
    }
    manifest = _manifest_without_identity(metadata, content_index)
    digest_payload = build_digest_payload(manifest)
    package_digest = _sha256(canonicalize(digest_payload))
    manifest["packageContentDigest"] = package_digest
    manifest["packageId"] = f"sfmeshpack:{package_digest}"
    try:
        _validate_contract_document(
            "validated_mesh_package_v2.schema.json" if metadata.package_schema.endswith(".v2")
            else "validated_mesh_package.schema.json",
            manifest,
        )
    except ContractValidationError as exc:
        raise VmpBuildError(str(exc)) from exc

    manifest_bytes = canonicalize(manifest)
    checksummed = dict(normalized)
    checksummed["VMP_MANIFEST.json"] = manifest_bytes
    sums = "".join(f"{_sha256(data)}  {path}\n" for path, data in sorted(checksummed.items())).encode("utf-8")
    archive_entries = dict(checksummed)
    archive_entries["SHA256SUMS.txt"] = sums
    _write_deterministic_zip(archive_path, archive_entries)
    return VmpBuildResult(
        archive_path=archive_path,
        package_id=manifest["packageId"],
        package_content_digest=package_digest,
        archive_sha256=_sha256(archive_path.read_bytes()),
        manifest=manifest,
        content_index=content_index,
    )


def build_digest_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Select exactly the MBS-135 frozen manifest field set, omitting absent optionals."""
    profile_schema = load_json(
        Path(__file__).resolve().parents[1] / "contracts/vmp/v1/schemas/vmp_content_digest_profile.schema.json"
    )
    included = profile_schema["properties"]["includedManifestFields"]["const"]
    result: dict[str, Any] = {}
    for dotted in included:
        value, present = _get_dotted(manifest, dotted)
        if not present:
            continue
        if value is None:
            raise VmpBuildError(f"Digest-participating optional field may not be null: {dotted}")
        _set_dotted(result, dotted, value)
    return result


def _manifest_without_identity(metadata: VmpBuildMetadata, content_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if (metadata.supersedes_package_content_digest is None) != (metadata.supersession_reason_code is None):
        raise VmpBuildError("Supersession digest and reason must be provided together")
    manifest: dict[str, Any] = {
        "schemaVersion": metadata.package_schema,
        "packageId": "sfmeshpack:" + "0" * 64,
        "packageContentDigest": "0" * 64,
        "packageVersion": metadata.package_version,
        "assetId": metadata.asset_id,
        "assetVersion": metadata.asset_version,
        "craftProfileId": metadata.craft_profile_id,
        "producer": {
            "foundry": "mesh_foundry",
            "sidecarVersion": metadata.sidecar_version,
            "providerId": metadata.provider_id,
            "providerModel": metadata.provider_model,
            "identityModel": metadata.identity_model,
        },
        "approval": {
            "state": "approved",
            "approvedForDistribution": True,
            "distributionTarget": "sprite_foundry",
        },
        "contracts": {
            "coordinateContract": "skyforge.mesh-coordinate.v1",
            "assetRoleContract": "skyforge.asset-role.v1",
            "frameContract": "skyforge.render-frame-contract.v1",
            "materialContract": metadata.material_contract,
            "minimumSpriteFoundryImporter": metadata.minimum_importer_version,
        },
        "source": {"authoritySetSha256": metadata.authority_set_sha256},
        "contentIndex": content_index,
        "digestProfile": _digest_profile(),
    }
    if metadata.provider_evidence_package_sha256 is not None:
        manifest["source"]["providerEvidencePackageSha256"] = metadata.provider_evidence_package_sha256
    if metadata.supersedes_package_content_digest is not None:
        manifest["supersession"] = {
            "supersedesPackageContentDigest": metadata.supersedes_package_content_digest,
            "reasonCode": metadata.supersession_reason_code,
        }
    return manifest


def _digest_profile() -> dict[str, Any]:
    schema = load_json(
        Path(__file__).resolve().parents[1] / "contracts/vmp/v1/schemas/vmp_content_digest_profile.schema.json"
    )
    properties = schema["properties"]
    return {
        "profileVersion": properties["profileVersion"]["const"],
        "canonicalization": properties["canonicalization"]["const"],
        "hashAlgorithm": properties["hashAlgorithm"]["const"],
        "includedManifestFields": properties["includedManifestFields"]["const"],
        "unknownFieldPolicy": properties["unknownFieldPolicy"]["const"],
        "optionalFieldEncoding": {
            "absent": properties["optionalFieldEncoding"]["properties"]["absent"]["const"],
            "explicitNull": properties["optionalFieldEncoding"]["properties"]["explicitNull"]["const"],
        },
    }


def _normalize_and_validate_payload(payload: Mapping[str, bytes]) -> dict[str, bytes]:
    paths = set(payload)
    missing = sorted(REQUIRED_PAYLOAD_PATHS - paths)
    if missing:
        raise VmpBuildError("VMP payload is incomplete: " + ", ".join(missing))
    normalized: dict[str, bytes] = {}
    for raw_path, raw_data in sorted(payload.items()):
        path = _validate_member_path(raw_path)
        if path in {"VMP_MANIFEST.json", "SHA256SUMS.txt"}:
            raise VmpBuildError(f"Caller may not supply generated package file: {path}")
        suffix = PurePosixPath(path).suffix.lower()
        if suffix in PROHIBITED_SUFFIXES or suffix not in ALLOWED_SUFFIXES:
            raise VmpBuildError(f"Unsupported or executable VMP file type: {path}")
        if not isinstance(raw_data, bytes) or not raw_data:
            raise VmpBuildError(f"VMP payload file must contain bytes: {path}")
        if suffix == ".json":
            try:
                document = json.loads(raw_data)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise VmpBuildError(f"Invalid JSON payload: {path}") from exc
            schema = _schema_for_document(path, document)
            if schema:
                try:
                    _validate_contract_document(schema, document)
                except ContractValidationError as exc:
                    raise VmpBuildError(f"{path}: {exc}") from exc
            raw_data = canonicalize(document)
        elif suffix == ".glb":
            _reject_external_glb_references(raw_data)
        normalized[path] = raw_data
    return normalized


def _schema_for_document(path: str, document: Any) -> str | None:
    if isinstance(document, dict):
        versioned = {
            ("authorities/authority_manifest.json", "skyforge.source-artifact-manifest.v2"): "source_artifact_manifest_v2.schema.json",
            ("materials/material_contract.json", "skyforge.mesh-material.v2"): "material_contract_v2.schema.json",
            ("provenance/source_chain.json", "skyforge.source-chain.v2"): "source_chain_v2.schema.json",
            ("mesh/semantic_identity.json", "skyforge.mesh-semantic-identity.v2"): "semantic_identity_v2.schema.json",
            ("mesh/component_manifest.json", "skyforge.mesh-components.v2"): "component_manifest_v2.schema.json",
        }
        selected = versioned.get((path, document.get("schemaVersion")))
        if selected:
            return selected
    return SCHEMA_BY_PATH.get(path)


def _validate_contract_document(schema_name: str, document: Any) -> None:
    if not schema_name.endswith("_v2.schema.json"):
        validate_document(schema_name, document)
        return
    path = Path(__file__).resolve().parents[1] / "contracts/vmp/v2/schemas" / schema_name
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"Unknown external-source schema: {schema_name}") from exc
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = "/".join(str(item) for item in error.absolute_path) or "<root>"
        raise ContractValidationError(f"{schema_name} rejected {location}: {error.message}")


def _validate_cross_file_contracts(payload: Mapping[str, bytes], metadata: VmpBuildMetadata) -> None:
    asset = json.loads(payload["asset.json"])
    authority = json.loads(payload["authorities/authority_manifest.json"])
    licensing = json.loads(payload["licensing_and_terms.json"])
    if asset["assetId"] != metadata.asset_id or asset["assetVersion"] != metadata.asset_version:
        raise VmpBuildError("Asset metadata does not match package metadata")
    if asset["craftProfileId"] != metadata.craft_profile_id:
        raise VmpBuildError("Craft profile does not match package metadata")
    if asset["provider"]["id"] != metadata.provider_id:
        raise VmpBuildError("Provider identity does not match package metadata")
    if asset["provider"]["identityModel"] != metadata.identity_model:
        raise VmpBuildError("Provider identity model does not match package metadata")
    if authority["authoritySetSha256"] != metadata.authority_set_sha256:
        raise VmpBuildError("Authority set identity does not match package metadata")
    permission = licensing["authorityRedistribution"]["permitted"]
    for record in authority.get("authorities", []):
        if record["embedded"]:
            embedded_path = record["embeddedPath"]
            if embedded_path not in payload:
                raise VmpBuildError(f"Embedded authority is absent: {embedded_path}")
            if _sha256(payload[embedded_path]) != record["sourceSha256"]:
                raise VmpBuildError("Embedded authority hash does not match authority manifest")
            if permission is not True:
                raise VmpBuildError("Authority embedding contradicts licensing_and_terms.json")
        elif "embeddedPath" in record:
            raise VmpBuildError("Hash-only authority may not declare an embedded path")


def _reject_external_glb_references(data: bytes) -> None:
    if len(data) < 20 or data[:4] != b"glTF":
        raise VmpBuildError("mesh/normalized.glb is not a valid GLB container")
    version, declared_length = struct.unpack_from("<II", data, 4)
    if version != 2 or declared_length != len(data):
        raise VmpBuildError("mesh/normalized.glb has an invalid header")
    offset = 12
    json_document: dict[str, Any] | None = None
    while offset + 8 <= len(data):
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + chunk_length]
        offset += chunk_length
        if len(chunk) != chunk_length:
            raise VmpBuildError("mesh/normalized.glb contains a truncated chunk")
        if chunk_type == 0x4E4F534A:
            try:
                json_document = json.loads(chunk.rstrip(b" \t\r\n\x00"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise VmpBuildError("mesh/normalized.glb contains invalid JSON") from exc
    if offset != len(data) or json_document is None:
        raise VmpBuildError("mesh/normalized.glb is structurally incomplete")
    for collection in ("buffers", "images"):
        for record in json_document.get(collection, []):
            if isinstance(record, dict) and "uri" in record:
                raise VmpBuildError(f"mesh/normalized.glb contains an external {collection[:-1]} reference")


def _validate_member_path(raw_path: str) -> str:
    if not isinstance(raw_path, str) or not raw_path:
        raise VmpBuildError("VMP member path must be a non-empty string")
    if "\\" in raw_path or raw_path.startswith("/"):
        raise VmpBuildError(f"Unsafe VMP member path: {raw_path!r}")
    path = PurePosixPath(raw_path)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise VmpBuildError(f"Unsafe VMP member path: {raw_path!r}")
    return path.as_posix()


def _write_deterministic_zip(path: Path, entries: Mapping[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED, strict_timestamps=True) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, FIXED_ZIP_TIMESTAMP)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, data)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(buffer.getvalue())
    temporary.replace(path)


def _get_dotted(document: Mapping[str, Any], dotted: str) -> tuple[Any, bool]:
    value: Any = document
    for part in dotted.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None, False
        value = value[part]
    return value, True


def _set_dotted(document: dict[str, Any], dotted: str, value: Any) -> None:
    current = document
    parts = dotted.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
