from __future__ import annotations

import hashlib
import json
import struct
import zipfile
from pathlib import Path

import pytest

import app.vmp_builder as builder
from app.vmp_builder import VmpBuildError, build_digest_payload, build_vmp
from common.schema_validation import validate_document
from tests.vmp_fixtures import json_bytes, metadata, payload

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def simple_canonicalize(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@pytest.fixture(autouse=True)
def canonicalizer(monkeypatch):
    monkeypatch.setattr(builder, "canonicalize", simple_canonicalize)


def test_two_independent_vmp_builds_are_byte_identical(tmp_path: Path):
    files, authority_set = payload(PACKAGE_ROOT)
    first = build_vmp(files, metadata(authority_set), tmp_path / "first.sfmeshpack")
    second = build_vmp(files, metadata(authority_set), tmp_path / "second.sfmeshpack")
    assert first.archive_path.read_bytes() == second.archive_path.read_bytes()
    assert first.package_content_digest == second.package_content_digest
    assert first.package_id == f"sfmeshpack:{first.package_content_digest}"
    validate_document("validated_mesh_package.schema.json", first.manifest)
    with zipfile.ZipFile(first.archive_path) as archive:
        assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())
        assert all((item.external_attr >> 16) & 0o777 == 0o644 for item in archive.infolist())
        assert "VMP_MANIFEST.json" not in first.content_index
        assert "SHA256SUMS.txt" not in first.content_index


def test_changed_content_changes_semantic_and_transport_identity(tmp_path: Path):
    files, authority_set = payload(PACKAGE_ROOT)
    first = build_vmp(files, metadata(authority_set), tmp_path / "first.sfmeshpack")
    limitations = json.loads(files["known_limitations.json"])
    limitations["limitations"][0]["description"] += " Changed."
    files["known_limitations.json"] = json_bytes(limitations)
    second = build_vmp(files, metadata(authority_set), tmp_path / "second.sfmeshpack")
    assert first.package_content_digest != second.package_content_digest
    assert first.archive_sha256 != second.archive_sha256


def test_sidecar_version_change_requires_new_identity_and_can_record_supersession(tmp_path: Path):
    files, authority_set = payload(PACKAGE_ROOT)
    first = build_vmp(files, metadata(authority_set, sidecar_version="0.7.0"), tmp_path / "first.sfmeshpack")
    next_metadata = metadata(authority_set, sidecar_version="0.7.1")
    next_metadata = builder.VmpBuildMetadata(
        **{**next_metadata.__dict__,
           "supersedes_package_content_digest": first.package_content_digest,
           "supersession_reason_code": "producer_version_rebuild"}
    )
    second = build_vmp(files, next_metadata, tmp_path / "second.sfmeshpack")
    assert second.package_content_digest != first.package_content_digest
    assert second.manifest["supersession"]["reasonCode"] == "producer_version_rebuild"


def test_hash_only_authority_builds_without_embedded_png(tmp_path: Path):
    files, authority_set = payload(PACKAGE_ROOT, embedded_authority=False)
    result = build_vmp(files, metadata(authority_set), tmp_path / "hash-only.sfmeshpack")
    with zipfile.ZipFile(result.archive_path) as archive:
        assert "authorities/silhouette_authority.png" not in archive.namelist()


def test_authority_embedding_and_licensing_fail_closed(tmp_path: Path):
    files, authority_set = payload(PACKAGE_ROOT)
    licensing = json.loads(files["licensing_and_terms.json"])
    licensing["authorityRedistribution"]["permitted"] = "unknown"
    files["licensing_and_terms.json"] = json_bytes(licensing)
    with pytest.raises(VmpBuildError, match="contradicts"):
        build_vmp(files, metadata(authority_set), tmp_path / "bad.sfmeshpack")


def test_prohibited_files_unsafe_paths_and_caller_manifest_are_rejected(tmp_path: Path):
    files, authority_set = payload(PACKAGE_ROOT)
    for name in ("mesh/source.blend", "../escape.png", "VMP_MANIFEST.json"):
        mutated = dict(files)
        mutated[name] = b"x"
        with pytest.raises(VmpBuildError):
            build_vmp(mutated, metadata(authority_set), tmp_path / (hashlib.sha256(name.encode()).hexdigest() + ".zip"))


def test_external_glb_uri_is_rejected(tmp_path: Path):
    files, authority_set = payload(PACKAGE_ROOT)
    gltf = json.dumps({"asset": {"version": "2.0"}, "buffers": [{"uri": "evil.bin", "byteLength": 1}]}, separators=(",", ":")).encode()
    gltf += b" " * ((4 - len(gltf) % 4) % 4)
    glb = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(gltf)) + struct.pack("<II", len(gltf), 0x4E4F534A) + gltf
    files["mesh/normalized.glb"] = glb
    with pytest.raises(VmpBuildError, match="external buffer"):
        build_vmp(files, metadata(authority_set), tmp_path / "bad.sfmeshpack")


def test_digest_payload_omits_absent_optionals_and_rejects_null():
    manifest = {
        "schemaVersion": "skyforge.validated-mesh-package.v1", "packageVersion": "1.0.0",
        "assetId": "a", "assetVersion": "1.0.0", "craftProfileId": "c",
        "producer": {"foundry": "mesh_foundry", "sidecarVersion": "0.7.1",
            "providerId": "local", "providerModel": "model", "identityModel": "deterministic_reproducibility"},
        "contracts": {"coordinateContract": "x", "assetRoleContract": "y", "frameContract": "z",
            "materialContract": "m", "minimumSpriteFoundryImporter": "1.0.0"},
        "source": {"authoritySetSha256": "1" * 64}, "contentIndex": {"a": {"sha256": "2" * 64, "sizeBytes": 1}},
    }
    digest = build_digest_payload(manifest)
    assert "supersession" not in digest
    assert "providerEvidencePackageSha256" not in digest["source"]
    manifest["source"]["providerEvidencePackageSha256"] = None
    with pytest.raises(VmpBuildError, match="may not be null"):
        build_digest_payload(manifest)
