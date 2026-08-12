from __future__ import annotations

import hashlib
import io
import json
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app.external_glb_vmp_export import export_manual_glb_vmp
from app.manual_glb_import import (
    QA_FILES,
    ManualGlbImportError,
    approve_manual_import,
    create_manual_import,
    load_manual_job,
    normalize_manual_import,
    reinspect_manual_import,
    require_current_approval,
    transition,
)
from common.glb_facts import GlbFactsError, parse_glb_facts


@pytest.fixture
def source_glb() -> bytes:
    return (Path(__file__).resolve().parents[1] / "samples/v053_field_gunship_baseline.glb").read_bytes()


def _create(tmp_path: Path, source_glb: bytes) -> Path:
    return create_manual_import(
        tmp_path, filename="../Meshy Ship.glb", stream=io.BytesIO(source_glb),
        asset_id="enemy.manual.01", asset_version="1.0.0", orientation_mapping="+Y,+Z",
    )


def _mutate_glb(data: bytes, change) -> bytes:
    json_length, json_type = struct.unpack_from("<II", data, 12)
    assert json_type == 0x4E4F534A
    document = json.loads(data[20 : 20 + json_length].rstrip(b" \x00"))
    change(document)
    encoded = json.dumps(document, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    tail = data[20 + json_length :]
    result = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(encoded) + len(tail))
    return result + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded + tail


def test_manual_import_preserves_source_and_records_truthful_provenance(tmp_path: Path, source_glb: bytes):
    root = _create(tmp_path, source_glb)
    original = root / "source_quarantine/original.glb"
    job = load_manual_job(root)
    assert original.read_bytes() == source_glb
    assert hashlib.sha256(original.read_bytes()).hexdigest() == job["source"]["sha256"]
    assert job["workflowId"] == "external_glb_import"
    assert job["source"]["provider"] == "meshy_web"
    assert job["source"]["type"] == "externally_authored"
    assert job["source"]["originalFilename"] == "Meshy Ship.glb"
    assert original.stat().st_mode & 0o222 == 0
    assert job["inspection"]["facts"]["triangle_count"] > 0
    report = json.loads((root / "inspection/glb_inspection.json").read_text())
    assert report["sourceGlbSha256"] == job["source"]["sha256"]
    assert report["sourceByteSize"] == len(source_glb)


@pytest.mark.parametrize("name", ["mesh.gltf", "mesh.obj", "mesh", "../mesh.GLB.exe"])
def test_manual_import_rejects_non_glb(tmp_path: Path, source_glb: bytes, name: str):
    with pytest.raises(ManualGlbImportError, match=".glb"):
        create_manual_import(tmp_path, filename=name, stream=io.BytesIO(source_glb), asset_id="a", asset_version="1.0.0", orientation_mapping="+Y,+Z")


def test_manual_import_rejects_empty_and_malformed_but_inspection_needs_no_orientation(tmp_path: Path, source_glb: bytes):
    for payload, orientation in ((b"", "+Y,+Z"), (b"bad", "+Y,+Z"), (b"bad", "")):
        with pytest.raises(ManualGlbImportError):
            create_manual_import(tmp_path, filename="mesh.glb", stream=io.BytesIO(payload), asset_id="a", asset_version="1.0.0", orientation_mapping=orientation)
    root = create_manual_import(tmp_path, filename="valid.glb", stream=io.BytesIO(source_glb), asset_id="inspect", asset_version="1.0.0")
    assert load_manual_job(root)["state"] == "inspected"


def test_source_mutation_blocks_reinspection_normalization_and_approval(tmp_path: Path, source_glb: bytes):
    root = _create(tmp_path, source_glb)
    original = root / "source_quarantine/original.glb"
    original.chmod(0o644)
    original.write_bytes(source_glb[:-1] + bytes([source_glb[-1] ^ 1]))
    with pytest.raises(ManualGlbImportError, match="changed after ingestion"):
        reinspect_manual_import(root)
    with pytest.raises(ManualGlbImportError, match="changed after ingestion"):
        normalize_manual_import(root, Path("/not/executed"), Path("/not/executed.py"))
    with pytest.raises(ManualGlbImportError, match="changed after ingestion"):
        approve_manual_import(root, True)


def test_normalization_requires_explicit_orientation_without_starting_blender(tmp_path: Path, source_glb: bytes):
    root = create_manual_import(tmp_path, filename="valid.glb", stream=io.BytesIO(source_glb), asset_id="inspect", asset_version="1.0.0")
    with pytest.raises(ManualGlbImportError, match="explicit source forward/up"):
        normalize_manual_import(root, Path("/not/executed"), Path("/not/executed.py"))


def test_approval_binds_hashes_and_invalidates_changed_normalized(tmp_path: Path, source_glb: bytes):
    root = _create(tmp_path, source_glb)
    normalized = root / "output/normalized.glb"
    normalized.write_bytes(source_glb)
    transition(root, "normalized", normalized={"sha256": hashlib.sha256(source_glb).hexdigest()})
    transition(root, "validated", validation={"passed": True})
    qa = root / "output/qa"
    for name in QA_FILES:
        Image.new("RGBA", (96, 96), (0, 0, 0, 0)).save(qa / name)
    transition(root, "qa_ready", qaOutputs=list(QA_FILES))
    approved = approve_manual_import(root, True)
    assert approved["approval"]["originalGlbSha256"] == hashlib.sha256(source_glb).hexdigest()
    assert approved["approval"]["normalizedGlbSha256"] == hashlib.sha256(source_glb).hexdigest()
    normalized.chmod(0o644)
    normalized.write_bytes(source_glb + b"changed")
    with pytest.raises(ManualGlbImportError, match="invalidated"):
        require_current_approval(root)
    assert load_manual_job(root)["approval"] is None


def test_export_refuses_source_changed_after_approval(tmp_path: Path, source_glb: bytes):
    root = _create(tmp_path, source_glb)
    normalized = root / "output/normalized.glb"
    normalized.write_bytes(source_glb)
    digest = hashlib.sha256(source_glb).hexdigest()
    transition(root, "normalized", normalized={"sha256": digest})
    transition(root, "validated", validation={"passed": True})
    for name in QA_FILES:
        Image.new("RGBA", (8, 8), (0, 0, 0, 0)).save(root / "output/qa" / name)
    transition(root, "qa_ready", qaOutputs=list(QA_FILES))
    approve_manual_import(root, True)
    original = root / "source_quarantine/original.glb"
    original.chmod(0o644)
    original.write_bytes(source_glb + b"x")
    with pytest.raises(ManualGlbImportError, match="changed after ingestion"):
        export_manual_glb_vmp(
            Path(__file__).resolve().parents[1], root, tmp_path / "refused.sfmeshpack",
            import_probe_command=("unused",), commercial_use_asserted=True, terms_basis="test",
        )


def test_manual_workflow_has_no_provider_or_credential_dependency():
    source = (Path(__file__).resolve().parents[1] / "app/manual_glb_import.py").read_text()
    assert "requests" not in source
    assert "meshy_client" not in source
    assert "keychain" not in source.lower()
    assert "resolve_provider" not in source


def test_extended_facts_report_material_texture_and_scene_information(source_glb: bytes):
    facts = parse_glb_facts(source_glb)
    assert facts.glb_version == 2
    assert facts.file_byte_length == len(source_glb)
    assert facts.primitive_count > 0
    assert facts.node_count > 0
    assert facts.scene_count > 0
    assert facts.texture_count >= 1
    assert facts.uv_primitive_count > 0
    assert facts.normal_primitive_count == 0  # fixture truthfully records normals as absent


def test_multi_mesh_multi_primitive_multi_material_inspection(source_glb: bytes):
    def expand(document):
        first = document["meshes"][0]["primitives"][0]
        document["materials"].append(dict(document["materials"][0]))
        second = dict(first)
        second["material"] = 1
        document["meshes"][0]["primitives"].append(second)
        document["meshes"].append({"primitives": [dict(first)]})

    facts = parse_glb_facts(_mutate_glb(source_glb, expand))
    assert (facts.mesh_count, facts.primitive_count, facts.material_count) == (2, 3, 2)


def test_inspector_rejects_external_uris_and_unsupported_geometry(source_glb: bytes):
    mutations = [
        (lambda doc: doc["images"][0].update(uri="texture.png"), "external image"),
        (lambda doc: doc["buffers"][0].update(uri="mesh.bin"), "external buffer"),
        (lambda doc: doc["meshes"][0]["primitives"][0].update(mode=1), "triangle"),
        (lambda doc: doc["accessors"][0].update(sparse={}), "sparse"),
        (lambda doc: doc["meshes"][0]["primitives"][0].pop("indices"), "positions or indices"),
        (lambda doc: doc.update(meshes=[]), "no mesh primitives"),
    ]
    for mutation, message in mutations:
        with pytest.raises(GlbFactsError, match=message):
            parse_glb_facts(_mutate_glb(source_glb, mutation))


def test_inspector_reports_no_material_or_texture_without_inventing_them(source_glb: bytes):
    def remove_materials(document):
        document["materials"] = []
        document["textures"] = []
        document["images"] = []
        document["meshes"][0]["primitives"][0].pop("material", None)

    facts = parse_glb_facts(_mutate_glb(source_glb, remove_materials))
    assert facts.material_count == 0
    assert facts.texture_count == 0
    assert facts.image_count == 0


def test_external_vmp_is_truthful_and_probe_gated(tmp_path: Path, source_glb: bytes, monkeypatch: pytest.MonkeyPatch):
    package_root = Path(__file__).resolve().parents[1]
    root = _create(tmp_path, source_glb)
    normalized = root / "output/normalized.glb"
    normalized.write_bytes(source_glb)
    digest = hashlib.sha256(source_glb).hexdigest()
    transition(root, "normalized", normalized={"sha256": digest})
    transition(root, "validated", validation={"passed": True})
    for name in QA_FILES:
        Image.new("RGBA", (96, 96), (20, 30, 40, 255)).save(root / "output/qa" / name)
    transition(root, "qa_ready", qaOutputs=list(QA_FILES))
    approve_manual_import(root, True)

    def fake_probe(_command, archive, receipt):
        with zipfile.ZipFile(archive) as bundle:
            manifest = json.loads(bundle.read("VMP_MANIFEST.json"))
            source_chain = json.loads(bundle.read("provenance/source_chain.json"))
            material = json.loads(bundle.read("materials/material_contract.json"))
        assert source_chain["sourceType"] == "externally_authored"
        assert source_chain["geometryGeneratedBySkyForge"] is False
        assert source_chain["deterministicallyReproducible"] is False
        assert "meshyTaskId" not in source_chain
        assert material["providerProcessing"]["aiTexturingApplied"] is True
        value = {"schemaVersion": "skyforge.sprite-foundry-import-receipt.v2", "contractMajorAccepted": 2, "accepted": True,
                 "sourcePackageContentDigest": manifest["packageContentDigest"],
                 "sourceArchiveSha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
        receipt.write_text(json.dumps(value), encoding="utf-8")
        return value

    monkeypatch.setattr("app.external_glb_vmp_export.run_import_probe", fake_probe)
    result = export_manual_glb_vmp(
        package_root, root, tmp_path / "external.sfmeshpack", import_probe_command=("probe",),
        commercial_use_asserted=True, terms_basis="user supplied Meshy web terms record",
    )
    assert result.build.manifest["schemaVersion"] == "skyforge.validated-mesh-package.v2"
    assert result.build.manifest["producer"]["providerId"] == "meshy_web"
    assert result.receipt["accepted"] is True
    probe_root = package_root.parent / "import-probe-v2"
    completed = subprocess.run(
        [sys.executable, str(probe_root / "run_import_probe_v2.py"), str(result.build.archive_path)],
        cwd=probe_root, text=True, capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["contractMajorAccepted"] == 2
    v1_root = package_root.parent / "import-probe"
    v1 = subprocess.run(
        [sys.executable, str(v1_root / "scripts/run_import_probe.py"), str(result.build.archive_path)],
        cwd=v1_root, text=True, capture_output=True, check=False,
    )
    assert v1.returncode != 0
    for member in ("mesh/normalized.glb", "provenance/source_chain.json"):
        tampered = tmp_path / f"tampered-{Path(member).name}.sfmeshpack"
        with zipfile.ZipFile(result.build.archive_path) as source, zipfile.ZipFile(tampered, "w") as target:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename == member:
                    data = data[:-1] + bytes([data[-1] ^ 1])
                target.writestr(info, data)
        rejected = subprocess.run(
            [sys.executable, str(probe_root / "run_import_probe_v2.py"), str(tampered)],
            cwd=probe_root, text=True, capture_output=True, check=False,
        )
        assert rejected.returncode != 0


def test_independent_v2_probe_does_not_import_producer_helpers():
    root = Path(__file__).resolve().parents[2] / "import-probe-v2/run_import_probe_v2.py"
    source = root.read_text()
    assert "mesh-builder" not in source
    assert "common.glb_facts" not in source
    assert "app.vmp_builder" not in source
