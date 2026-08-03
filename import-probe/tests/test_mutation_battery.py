from __future__ import annotations

import hashlib
import json
import struct
import zipfile
from pathlib import Path

import pytest

import probe.vmp_validator as validator
from probe.archive_reader import ArchiveLimits
from probe.canonical_digest import build_digest_payload
from probe.errors import ProbeReject
from probe.vmp_validator import import_vmp

ROOT = Path(__file__).resolve().parents[1]
VALID = ROOT / "tests/fixtures/valid_embedded.sfmeshpack"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


@pytest.fixture(autouse=True)
def canonicalizer(monkeypatch):
    monkeypatch.setattr(validator, "canonicalize", canonical)


def load_entries(path: Path = VALID):
    entries = {}
    modes = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            entries[info.filename] = archive.read(info)
            modes[info.filename] = (info.external_attr >> 16) & 0o177777
    return entries, modes


def write_archive(path: Path, entries: dict[str, bytes], modes=None, *, compression=zipfile.ZIP_STORED):
    modes = modes or {}
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.create_system = 3
            info.external_attr = (modes.get(name, 0o100644)) << 16
            info.compress_type = compression
            archive.writestr(info, data)
    return path


def refresh_checksums(entries: dict[str, bytes]):
    entries["SHA256SUMS.txt"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(entries.items()) if name != "SHA256SUMS.txt"
    ).encode()


def refresh_identity(entries: dict[str, bytes]):
    manifest = json.loads(entries["VMP_MANIFEST.json"])
    payload_names = sorted(set(entries) - {"VMP_MANIFEST.json", "SHA256SUMS.txt"})
    manifest["contentIndex"] = {
        name: {"sha256": hashlib.sha256(entries[name]).hexdigest(), "sizeBytes": len(entries[name])}
        for name in payload_names
    }
    digest = hashlib.sha256(canonical(build_digest_payload(manifest))).hexdigest()
    manifest["packageContentDigest"] = digest
    manifest["packageId"] = f"sfmeshpack:{digest}"
    entries["VMP_MANIFEST.json"] = canonical(manifest)
    refresh_checksums(entries)


def mutate_json(entries, path, mutator, *, refresh_package=True):
    document = json.loads(entries[path])
    mutator(document)
    entries[path] = canonical(document)
    if refresh_package:
        refresh_identity(entries)
    else:
        refresh_checksums(entries)


def assert_reject(path: Path, code: str, **kwargs):
    with pytest.raises(ProbeReject) as caught:
        import_vmp(path, created_at="2026-08-01T00:00:00Z", **kwargs)
    assert caught.value.code == code


def test_mutation_01_changed_byte(tmp_path: Path):
    entries, modes = load_entries()
    entries["previews/gameplay_scale_96.png"] += b"x"
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "checksum_mismatch")


def test_mutation_02_missing_required_file(tmp_path: Path):
    entries, modes = load_entries()
    entries.pop("asset.json")
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "required_file_missing")


def test_mutation_03_unlisted_added_file(tmp_path: Path):
    entries, modes = load_entries()
    entries["extra.json"] = b"{}"
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "checksum_file_set")


def test_mutation_03b_regular_file_parent_collision_is_rejected_with_rooted_diagnostic(tmp_path: Path):
    entries, modes = load_entries()
    entries["SHA256SUMS.txt/injected.txt"] = b"{}"
    with pytest.raises(ProbeReject) as caught:
        import_vmp(
            write_archive(tmp_path / "m.sfmeshpack", entries, modes),
            created_at="2026-08-01T00:00:00Z",
        )
    assert caught.value.code == "archive_path_collision"
    assert "SHA256SUMS.txt -> SHA256SUMS.txt/injected.txt" in caught.value.message


def test_mutation_04_unsupported_schema_major(tmp_path: Path):
    entries, modes = load_entries()
    mutate_json(entries, "asset.json", lambda d: d.__setitem__("schemaVersion", "skyforge.asset.v4"))
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "unsupported_schema_major")


def test_mutation_05_approval_false(tmp_path: Path):
    entries, modes = load_entries()
    manifest = json.loads(entries["VMP_MANIFEST.json"])
    manifest["approval"]["approvedForDistribution"] = False
    entries["VMP_MANIFEST.json"] = canonical(manifest)
    refresh_checksums(entries)
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "approval_not_granted")


def test_mutation_06_content_digest_mismatch(tmp_path: Path):
    entries, modes = load_entries()
    manifest = json.loads(entries["VMP_MANIFEST.json"])
    manifest["packageContentDigest"] = "0" * 64
    manifest["packageId"] = "sfmeshpack:" + "0" * 64
    entries["VMP_MANIFEST.json"] = canonical(manifest)
    refresh_checksums(entries)
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "package_digest_mismatch")


def test_mutation_07_coordinate_mismatch(tmp_path: Path):
    entries, modes = load_entries()
    mutate_json(entries, "mesh/bounds_and_scale.json", lambda d: d.__setitem__("coordinateContract", "wrong"))
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "coordinate_mismatch")


def test_mutation_08_frame_contract_mismatch(tmp_path: Path):
    entries, modes = load_entries()
    mutate_json(entries, "render/frame_contract.json", lambda d: d.__setitem__("heightToPlanformRatio", 0.9))
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "frame_contract_mismatch")


def external_glb() -> bytes:
    doc = {"asset": {"version": "2.0"}, "buffers": [{"uri": "evil.bin", "byteLength": 1}],
           "images": [{"uri": "evil.png"}], "meshes": []}
    chunk = canonical(doc)
    chunk += b" " * ((4 - len(chunk) % 4) % 4)
    return b"glTF" + struct.pack("<II", 2, 12 + 8 + len(chunk)) + struct.pack("<II", len(chunk), 0x4E4F534A) + chunk


def test_mutation_09_external_texture_reference(tmp_path: Path):
    entries, modes = load_entries()
    entries["mesh/normalized.glb"] = external_glb()
    refresh_identity(entries)
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "glb_external_reference")


def test_mutation_10_role_incompatibility(tmp_path: Path):
    entries, modes = load_entries()
    mutate_json(entries, "asset.json", lambda d: d.__setitem__("assetRole", "ground_static"))
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "role_incompatible")


def test_mutation_11_path_traversal(tmp_path: Path):
    entries, modes = load_entries()
    entries["../evil.png"] = entries.pop("previews/gameplay_scale_96.png")
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "archive_path_traversal")


def test_mutation_12_decompressed_payload_limit(tmp_path: Path):
    assert_reject(
        VALID,
        "archive_total_size_limit",
        limits=ArchiveLimits(max_member_uncompressed_bytes=100_000_000, max_total_uncompressed_bytes=100),
    )


def test_mutation_13_excessive_compression_ratio(tmp_path: Path):
    entries, modes = load_entries()
    entries["bomb.json"] = b"0" * 1_000_000
    archive = write_archive(tmp_path / "m.sfmeshpack", entries, modes, compression=zipfile.ZIP_DEFLATED)
    assert_reject(archive, "archive_compression_ratio")


def test_mutation_14_collision_hint_falsely_authoritative(tmp_path: Path):
    entries, modes = load_entries()
    def mutate(document):
        document["collisionHint"] = {
            "authoritative": True,
            "consumerMustIgnoreForRuntime": False,
            "sourceSchema": "skyforge.asset.sidecar.v3.0",
        }
    mutate_json(entries, "asset.json", mutate)
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "collision_hint_authoritative")


def test_mutation_15_unknown_permission_with_embedded_authority(tmp_path: Path):
    entries, modes = load_entries()
    mutate_json(
        entries,
        "authorities/authority_manifest.json",
        lambda d: d["authorities"][0].__setitem__("redistributionPermission", "unknown"),
    )
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "authority_embedding_terms")


def test_mutation_16_missing_calibration_envelope_while_extension_allowed(tmp_path: Path):
    entries, modes = load_entries()
    mutate_json(entries, "render/frame_contract.json", lambda d: d.pop("calibrationEnvelope"))
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "frame_calibration_envelope_missing")


def test_mutation_17_non_frozen_digest_field_set(tmp_path: Path):
    entries, modes = load_entries()
    manifest = json.loads(entries["VMP_MANIFEST.json"])
    wrong_payload = dict(build_digest_payload(manifest))
    wrong_payload["approval"] = manifest["approval"]
    wrong_digest = hashlib.sha256(canonical(wrong_payload)).hexdigest()
    manifest["packageContentDigest"] = wrong_digest
    manifest["packageId"] = f"sfmeshpack:{wrong_digest}"
    entries["VMP_MANIFEST.json"] = canonical(manifest)
    refresh_checksums(entries)
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "package_digest_mismatch")


def test_mutation_18_executable_mode(tmp_path: Path):
    entries, modes = load_entries()
    modes["asset.json"] = 0o100755
    assert_reject(write_archive(tmp_path / "m.sfmeshpack", entries, modes), "archive_executable_mode")
