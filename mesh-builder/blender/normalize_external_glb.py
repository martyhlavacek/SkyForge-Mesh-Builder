from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qa_render_support import require_render_output, select_eevee_engine, select_view_look  # noqa: E402

TARGET_PLANFORM_SPAN = 5.5


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-root", required=True)
    parser.add_argument("--orientation", required=True)
    parser.add_argument("--diagnostics", required=True)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def axis(value: str) -> Vector:
    sign = -1 if value.startswith("-") else 1
    result = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}[value[-1]]
    return result * sign


def bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    lo = Vector((math.inf, math.inf, math.inf))
    hi = Vector((-math.inf, -math.inf, -math.inf))
    for obj in objects:
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            for i in range(3):
                lo[i], hi[i] = min(lo[i], point[i]), max(hi[i], point[i])
    if not all(math.isfinite(v) for v in (*lo, *hi)):
        raise RuntimeError("imported mesh has non-finite bounds")
    return lo, hi


def add_camera(name: str, location: tuple[float, float, float], ortho: float) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new(name)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = ortho
    camera = bpy.data.objects.new(name, camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = location
    direction = -camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return camera


def write_diagnostics(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def mark(summary: dict, path: Path, stage: str) -> None:
    summary["stageMarkers"].append({"stage": stage, "recordedAt": datetime.now(timezone.utc).isoformat()})
    write_diagnostics(path, summary)


def render(
    path: Path, location: tuple[float, float, float], ortho: float, size: int,
    engine: str, summary: dict, diagnostics_path: Path,
) -> None:
    camera = add_camera("qa_camera", location, ortho)
    record = {"name": path.name, "engine": engine, "expectedPath": str(path.resolve()), "operatorResult": None,
              "outputExists": False, "outputByteSize": 0}
    summary["renders"].append(record)
    write_diagnostics(diagnostics_path, summary)
    try:
        bpy.context.scene.camera = camera
        scene = bpy.context.scene
        scene.render.film_transparent = True
        scene.render.resolution_x = scene.render.resolution_y = size
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(path.resolve())
        result = bpy.ops.render.render(write_still=True)
        record["operatorResult"] = sorted(str(item) for item in result)
        record["outputExists"] = path.is_file()
        record["outputByteSize"] = path.stat().st_size if path.is_file() else 0
        write_diagnostics(diagnostics_path, summary)
        require_render_output(path.name, path, result)
    finally:
        bpy.data.objects.remove(camera, do_unlink=True)


def main() -> None:
    config = args()
    root = Path(config.job_root).resolve()
    diagnostics_path = Path(config.diagnostics).resolve() / "blender_script.json"
    summary = {
        "schemaVersion": "skyforge.blender-normalization-diagnostics.v1",
        "blenderVersion": bpy.app.version_string,
        "blenderBuildHash": bpy.app.build_hash.decode("utf-8", "replace"),
        "selectedEeveeEngine": None,
        "selectedViewLook": None,
        "stageMarkers": [],
        "renders": [],
        "error": None,
    }
    mark(summary, diagnostics_path, "script_started")
    source = root / "source_quarantine/original.glb"
    output = root / "output"
    qa = output / "qa"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    mark(summary, diagnostics_path, "source_imported")
    imported = list(bpy.context.scene.objects)
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("imported GLB contains no mesh objects")
    forward_name, up_name = config.orientation.split(",")
    forward, up = axis(forward_name), axis(up_name)
    if abs(forward.dot(up)) > 1e-6:
        raise RuntimeError("orientation axes must be orthogonal")
    right = forward.cross(up)
    orientation = Matrix((right, forward, up)).transposed().to_4x4().inverted()
    root_obj = bpy.data.objects.new("skyforge_asset_root", None)
    bpy.context.collection.objects.link(root_obj)
    imported_set = set(imported)
    for obj in imported:
        if obj.parent not in imported_set:
            world = obj.matrix_world.copy()
            obj.parent = root_obj
            obj.matrix_world = world
    root_obj.matrix_world = orientation
    bpy.context.view_layer.update()
    lo, hi = bounds(meshes)
    center = (lo + hi) / 2
    span = max(hi.x - lo.x, hi.y - lo.y)
    if span <= 1e-8:
        raise RuntimeError("imported GLB has zero planform extent")
    root_obj.matrix_world = Matrix.Scale(TARGET_PLANFORM_SPAN / span, 4) @ Matrix.Translation(-center) @ orientation
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action="DESELECT")
    for obj in imported + [root_obj]:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = root_obj
    bpy.ops.export_scene.gltf(
        filepath=str(output / "normalized.glb"), export_format="GLB", use_selection=True,
        export_materials="EXPORT", export_image_format="AUTO", export_animations=True,
    )
    mark(summary, diagnostics_path, "normalized_glb_exported")
    qa.mkdir(parents=True, exist_ok=True)
    engine = select_eevee_engine(bpy.context.scene)
    view_look = select_view_look(bpy.context.scene)
    summary["selectedEeveeEngine"] = engine
    summary["selectedViewLook"] = view_look
    mark(summary, diagnostics_path, "render_engine_selected")
    views = {
        "gameplay_neutral.png": ((0, -8, 14), 7.0, 384),
        "bank_left.png": ((-5, -8, 13), 7.0, 384),
        "bank_right.png": ((5, -8, 13), 7.0, 384),
        "top_ortho.png": ((0, 0, 16), 7.0, 384),
        "front.png": ((0, 16, 0), 7.0, 384),
        "side.png": ((16, 0, 0), 7.0, 384),
        "gameplay_scale_96.png": ((0, -8, 14), 7.0, 96),
    }
    for name, (location, ortho, size) in views.items():
        mark(summary, diagnostics_path, f"render_started:{name}")
        render(qa / name, location, ortho, size, engine, summary, diagnostics_path)
        mark(summary, diagnostics_path, f"render_completed:{name}")
    mark(summary, diagnostics_path, "script_completed")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        try:
            config = args()
            path = Path(config.diagnostics).resolve() / "blender_script.json"
            if path.is_file():
                value = json.loads(path.read_text(encoding="utf-8"))
            else:
                value = {"schemaVersion": "skyforge.blender-normalization-diagnostics.v1", "stageMarkers": [], "renders": []}
            value["error"] = traceback.format_exc()
            value["stageMarkers"].append({"stage": "script_failed", "recordedAt": datetime.now(timezone.utc).isoformat()})
            write_diagnostics(path, value)
        finally:
            raise
