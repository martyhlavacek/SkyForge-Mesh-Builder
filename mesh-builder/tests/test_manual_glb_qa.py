from __future__ import annotations

import ast
import io
import json
import signal
import struct
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.manual_glb_import import (
    QA_DIMENSIONS,
    QA_FILES,
    ManualGlbImportError,
    _validate_qa_outputs,
    approve_manual_import,
    create_manual_import,
    load_manual_job,
    normalize_manual_import,
)
from blender.qa_render_support import require_render_output, select_eevee_engine, select_view_look


class RenderEnum:
    def __init__(self, accepted: set[str]):
        self.accepted = accepted
        self._engine = ""

    @property
    def engine(self) -> str:
        return self._engine

    @engine.setter
    def engine(self, value: str) -> None:
        if value not in self.accepted:
            raise TypeError(f"unsupported {value}")
        self._engine = value


class ViewLookEnum:
    def __init__(self, accepted: set[str]):
        self.accepted = accepted
        self._look = ""

    @property
    def look(self) -> str:
        return self._look

    @look.setter
    def look(self, value: str) -> None:
        if value not in self.accepted:
            raise TypeError(f"unsupported {value}")
        self._look = value


def _scene(*accepted: str) -> SimpleNamespace:
    return SimpleNamespace(render=RenderEnum(set(accepted)))


def _job(tmp_path: Path) -> Path:
    source = (Path(__file__).resolve().parents[1] / "samples/v053_field_gunship_baseline.glb").read_bytes()
    return create_manual_import(
        tmp_path, filename="synthetic.glb", stream=io.BytesIO(source), asset_id="synthetic.qa",
        asset_version="1.0.0", orientation_mapping="+Y,+Z",
    )


def _write_valid_outputs(root: Path) -> None:
    source = root / "source_quarantine/original.glb"
    (root / "output/normalized.glb").write_bytes(source.read_bytes())
    for name, dimensions in QA_DIMENSIONS.items():
        Image.new("RGBA", dimensions, (10, 20, 30, 255)).save(root / "output/qa" / name)


def _write_script_success(command: list[str]) -> None:
    diagnostics = Path(command[command.index("--diagnostics") + 1])
    diagnostics.mkdir(parents=True, exist_ok=True)
    (diagnostics / "blender_script.json").write_text(json.dumps({
        "selectedEeveeEngine": "BLENDER_EEVEE",
        "stageMarkers": [{"stage": "script_completed"}],
        "renders": [{"name": name, "operatorResult": ["FINISHED"]} for name in QA_FILES],
        "error": None,
    }))


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


def test_live_engine_selector_prefers_blender_5_identifier():
    scene = _scene("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT")
    assert select_eevee_engine(scene) == "BLENDER_EEVEE"


def test_production_manual_export_explicitly_preserves_tangents():
    script = Path(__file__).resolve().parents[1] / "blender/normalize_external_glb.py"
    tree = ast.parse(script.read_text(encoding="utf-8"))
    exports = [
        node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute) and node.func.attr == "gltf"
        and isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "export_scene"
    ]
    assert len(exports) == 1
    keywords = {item.arg: item.value for item in exports[0].keywords}
    assert isinstance(keywords.get("export_tangents"), ast.Constant)
    assert keywords["export_tangents"].value is True


def test_live_engine_selector_falls_back_to_eevee_next():
    scene = _scene("BLENDER_EEVEE_NEXT")
    assert select_eevee_engine(scene) == "BLENDER_EEVEE_NEXT"


def test_live_engine_selector_fails_when_neither_identifier_exists():
    with pytest.raises(RuntimeError, match="No supported EEVEE"):
        select_eevee_engine(_scene())


def test_live_view_look_selector_supports_blender_5_and_legacy_names():
    current = SimpleNamespace(view_settings=ViewLookEnum({"AgX - Medium High Contrast"}))
    legacy = SimpleNamespace(view_settings=ViewLookEnum({"Medium High Contrast"}))
    assert select_view_look(current) == "AgX - Medium High Contrast"
    assert select_view_look(legacy) == "Medium High Contrast"


def test_render_result_cancelled_missing_and_empty_fail(tmp_path: Path):
    output = tmp_path / "view.png"
    with pytest.raises(RuntimeError, match="did not finish"):
        require_render_output("view.png", output, {"CANCELLED"})
    with pytest.raises(RuntimeError, match="output is absent"):
        require_render_output("view.png", output, {"FINISHED"})
    output.touch()
    with pytest.raises(RuntimeError, match="empty output"):
        require_render_output("view.png", output, {"FINISHED"})


def test_png_dimensions_and_decode_are_enforced(tmp_path: Path):
    root = tmp_path / "job"
    (root / "output/qa").mkdir(parents=True)
    for name, dimensions in QA_DIMENSIONS.items():
        Image.new("RGBA", dimensions, (0, 0, 0, 0)).save(root / "output/qa" / name)
    _validate_qa_outputs(root)
    Image.new("RGBA", (10, 10)).save(root / "output/qa/front.png")
    with pytest.raises(ManualGlbImportError, match="wrong dimensions"):
        _validate_qa_outputs(root)
    (root / "output/qa/front.png").write_bytes(b"not png")
    with pytest.raises(ManualGlbImportError, match="not a decodable PNG"):
        _validate_qa_outputs(root)


def test_success_persists_diagnostics_and_reaches_qa_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _job(tmp_path)

    def successful(command, **_kwargs):
        _write_valid_outputs(root)
        _write_script_success(command)
        return subprocess.CompletedProcess(command, 0, "Blender 5.2 stdout", "")

    monkeypatch.setattr(subprocess, "run", successful)
    result = normalize_manual_import(root, Path("/Applications/Blender"), Path("normalize.py"))
    assert result["state"] == "qa_ready"
    assert sorted(path.name for path in (root / "output/qa").iterdir()) == sorted(QA_FILES)
    attempt = next((root / "diagnostics/blender").iterdir())
    execution = json.loads((attempt / "execution.json").read_text())
    assert execution["returnCode"] == 0
    assert (attempt / "stdout.txt").read_text() == "Blender 5.2 stdout"
    assert (attempt / "stderr.txt").read_text() == ""


def test_signal_failure_is_attributable_and_job_remains_retryable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _job(tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, -11, "out", "segfault"))
    with pytest.raises(ManualGlbImportError, match=r"signal 11 \(SIGSEGV\)"):
        normalize_manual_import(root, Path("/Applications/Blender"), Path("normalize.py"))
    assert load_manual_job(root)["state"] == "inspected"
    with pytest.raises(ManualGlbImportError, match="only QA-ready"):
        approve_manual_import(root, True)
    attempt = next((root / "diagnostics/blender").iterdir())
    execution = json.loads((attempt / "execution.json").read_text())
    assert execution["terminatedBySignal"] is True
    assert execution["signalNumber"] == 11
    assert execution["signalName"] == signal.Signals(11).name
    assert (attempt / "stdout.txt").read_text() == "out"
    assert (attempt / "stderr.txt").read_text() == "segfault"


def test_missing_qa_does_not_advance_state_and_retry_can_succeed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _job(tmp_path)
    attempts = 0

    def run(command, **_kwargs):
        nonlocal attempts
        attempts += 1
        (root / "output/normalized.glb").write_bytes((root / "source_quarantine/original.glb").read_bytes())
        if attempts == 2:
            _write_valid_outputs(root)
        _write_script_success(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ManualGlbImportError, match="required QA output"):
        normalize_manual_import(root, Path("/Applications/Blender"), Path("normalize.py"))
    assert load_manual_job(root)["state"] == "inspected"
    assert normalize_manual_import(root, Path("/Applications/Blender"), Path("normalize.py"))["state"] == "qa_ready"


def test_blender_false_zero_with_script_traceback_fails_retryably(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _job(tmp_path)

    def run(command, **_kwargs):
        diagnostics = Path(command[command.index("--diagnostics") + 1])
        diagnostics.mkdir(parents=True, exist_ok=True)
        (diagnostics / "blender_script.json").write_text(json.dumps({
            "stageMarkers": [{"stage": "script_failed"}],
            "renders": [],
            "error": "Traceback:\nTypeError: unsupported render setting",
        }))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ManualGlbImportError, match="TypeError: unsupported render setting"):
        normalize_manual_import(root, Path("/Applications/Blender"), Path("normalize.py"))
    assert load_manual_job(root)["state"] == "inspected"


def test_normalization_rejects_lost_texture_channel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _job(tmp_path)
    source = (root / "source_quarantine/original.glb").read_bytes()

    def run(command, **_kwargs):
        # A valid untextured GLB proves the preservation comparison is independent of byte identity.
        def remove(document):
            document["materials"] = []
            document["textures"] = []
            document["images"] = []
            document["meshes"][0]["primitives"][0].pop("material", None)

        (root / "output/normalized.glb").write_bytes(_mutate_glb(source, remove))
        for name, dimensions in QA_DIMENSIONS.items():
            Image.new("RGBA", dimensions).save(root / "output/qa" / name)
        _write_script_success(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ManualGlbImportError, match="texture channels|material count"):
        normalize_manual_import(root, Path("/Applications/Blender"), Path("normalize.py"))
    assert load_manual_job(root)["state"] == "inspected"
