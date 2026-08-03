from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageOps

from .model import AuthorityPlanform, PlacedComponent
from .placement import WORLD_SPAN

DIAGNOSTIC_COLOURS = {
    "base_shell": (90, 105, 120, 255),
    "fuselage": (225, 160, 70, 255),
    "cockpit": (70, 180, 230, 255),
    "cockpit_left": (70, 180, 230, 255),
    "cockpit_right": (55, 145, 215, 255),
    "engine_left": (210, 80, 95, 255),
    "engine_right": (185, 60, 80, 255),
    "weapon_left": (235, 220, 90, 255),
    "weapon_right": (220, 195, 70, 255),
    "belly": (125, 90, 175, 255),
    "keel": (125, 90, 175, 255),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _project(vertices: np.ndarray, view: str) -> tuple[np.ndarray, np.ndarray]:
    if view == "top":
        screen = vertices[:, [0, 1]]
        depth = vertices[:, 2]
    elif view == "front":
        screen = vertices[:, [0, 2]]
        depth = vertices[:, 1]
    elif view == "side":
        screen = vertices[:, [1, 2]]
        depth = vertices[:, 0]
    else:
        angle = np.deg2rad(-28 if view == "bank_left" else 28)
        tilted = vertices.copy()
        tilted[:, 0] = vertices[:, 0] * np.cos(angle) - vertices[:, 2] * np.sin(angle)
        tilted[:, 2] = vertices[:, 0] * np.sin(angle) + vertices[:, 2] * np.cos(angle)
        screen = tilted[:, [0, 1]]
        depth = tilted[:, 2]
    return screen, depth


def render_components(meshes: dict[str, trimesh.Trimesh], output_path: Path, view: str, size: int = 512) -> None:
    projected: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    all_points: list[np.ndarray] = []
    for name, mesh in meshes.items():
        points, depth = _project(np.asarray(mesh.vertices, dtype=np.float64), view)
        projected[name] = (points, depth)
        all_points.append(points)
    bounds_points = np.vstack(all_points)
    minimum = bounds_points.min(axis=0)
    maximum = bounds_points.max(axis=0)
    span = np.maximum(maximum - minimum, 1e-6)
    scale = min((size - 48) / span[0], (size - 48) / span[1])
    canvas = Image.new("RGBA", (size, size), (20, 24, 30, 255))
    draw = ImageDraw.Draw(canvas, "RGBA")
    faces_to_draw: list[tuple[float, str, list[tuple[float, float]]]] = []
    for name, mesh in meshes.items():
        points, depth = projected[name]
        pixels = (points - (minimum + maximum) * 0.5) * scale + size * 0.5
        pixels[:, 1] = size - pixels[:, 1]
        for face in np.asarray(mesh.faces, dtype=np.int64):
            polygon = [(float(pixels[index, 0]), float(pixels[index, 1])) for index in face]
            faces_to_draw.append((float(np.mean(depth[face])), name, polygon))
    for _, name, polygon in sorted(faces_to_draw, key=lambda item: item[0]):
        colour = DIAGNOSTIC_COLOURS.get(name, (170, 170, 170, 255))
        draw.polygon(polygon, fill=colour, outline=(15, 18, 22, 90))
    canvas.save(output_path)


def render_overlay(planform: AuthorityPlanform, components: list[PlacedComponent], output_path: Path) -> None:
    base = Image.fromarray(np.where(planform.mask, 70, 20).astype(np.uint8), "L").convert("RGBA")
    base = base.resize((512, 512), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(base, "RGBA")
    scale = 512 / 384
    for component in components:
        vertices = np.asarray(component.mesh.vertices, dtype=np.float64)
        x = (vertices[:, 0] / WORLD_SPAN * 384 + 192) * scale
        y = (192 - vertices[:, 1] / WORLD_SPAN * 384) * scale
        colour = DIAGNOSTIC_COLOURS.get(component.name, (255, 255, 255, 255))
        for face in np.asarray(component.mesh.faces, dtype=np.int64):
            draw.line([(float(x[index]), float(y[index])) for index in (*face, face[0])], fill=colour, width=1)
    base.save(output_path)


def render_cross_sections(components: list[PlacedComponent], output_path: Path) -> None:
    sheet = Image.new("RGBA", (960, 320), (20, 24, 30, 255))
    draw = ImageDraw.Draw(sheet, "RGBA")
    anchors = ((0.25, "NOSE / COCKPIT"), (0.52, "MID-BODY / ENGINES"), (0.72, "AFT BODY"))
    y_values = [component.centre[1] for component in components]
    y_min, y_max = min(y_values), max(y_values)
    for panel, (fraction, label) in enumerate(anchors):
        section_y = y_max - fraction * (y_max - y_min)
        left = panel * 320
        draw.text((left + 10, 10), label, fill=(240, 244, 248, 255))
        draw.line((left + 20, 270, left + 300, 270), fill=(120, 130, 140, 255), width=1)
        for component in components:
            length, width, height = component.dimensions
            if abs(component.centre[1] - section_y) > length * 0.6:
                continue
            cx = left + 160 + component.centre[0] * 48
            cy = 245 - component.centre[2] * 105
            colour = DIAGNOSTIC_COLOURS.get(component.name, (180, 180, 180, 255))
            draw.ellipse((cx - width * 24, cy - height * 52, cx + width * 24, cy + height * 52), fill=colour)
    sheet.save(output_path)


def comparison_sheet(authority_path: Path, legacy_top_path: Path, alpha_top_path: Path, output_path: Path) -> None:
    sheet = Image.new("RGBA", (768, 284), (20, 24, 30, 255))
    draw = ImageDraw.Draw(sheet)
    sources = (authority_path, legacy_top_path, alpha_top_path)
    labels = ("AUTHORITY", "UNCHANGED V0.7.1", "ALPHA 1")
    for index, (source, label) in enumerate(zip(sources, labels, strict=True)):
        with Image.open(source) as image:
            fitted = ImageOps.contain(image.convert("RGBA"), (240, 240), Image.Resampling.LANCZOS)
        x = index * 256 + (256 - fitted.width) // 2
        y = 36 + (240 - fitted.height) // 2
        sheet.alpha_composite(fitted, (x, y))
        draw.text((index * 256 + 8, 9), label, fill=(240, 244, 248, 255))
    sheet.save(output_path)


def write_manifest(root: Path, manifest_path: Path) -> dict[str, str]:
    records = {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != manifest_path
    }
    manifest_path.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return records


def verify_manifest(root: Path, manifest_path: Path) -> bool:
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    return expected == {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != manifest_path
    }
