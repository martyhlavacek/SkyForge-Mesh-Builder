from __future__ import annotations

from pathlib import Path
from typing import Any


def select_eevee_engine(scene: Any) -> str:
    """Probe the running Blender enum instead of applying version heuristics."""
    failures: list[str] = []
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
        except (TypeError, ValueError) as exc:
            failures.append(f"{engine}: {exc}")
        else:
            return engine
    raise RuntimeError("No supported EEVEE render engine identifier is available. " + "; ".join(failures))


def select_view_look(scene: Any) -> str:
    failures: list[str] = []
    for look in ("AgX - Medium High Contrast", "Medium High Contrast", "None"):
        try:
            scene.view_settings.look = look
        except (TypeError, ValueError) as exc:
            failures.append(f"{look}: {exc}")
        else:
            return look
    raise RuntimeError("No supported QA view look is available. " + "; ".join(failures))


def require_render_output(name: str, path: Path, result: set[str]) -> None:
    if "FINISHED" not in result or len(result) != 1:
        raise RuntimeError(f"QA render {name} did not finish successfully: {sorted(str(item) for item in result)}")
    if not path.is_file():
        raise RuntimeError(f"QA render {name} reported success but output is absent: {path.resolve()}")
    if path.stat().st_size <= 0:
        raise RuntimeError(f"QA render {name} produced an empty output: {path.resolve()}")
