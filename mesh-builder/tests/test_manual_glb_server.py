import os
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

from app.manual_glb_import import ORIENTATION_MAPPING_OPTIONS, ORIENTATION_MAPPINGS
from app.manual_glb_server import create_manual_glb_app


class _OrientationOptions(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_orientation = False
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "select" and values.get("id") == "orientation":
            self.in_orientation = True
        elif tag == "option" and self.in_orientation:
            self.values.append(values.get("value") or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "select" and self.in_orientation:
            self.in_orientation = False


def test_manual_ui_is_localhost_only_and_provider_isolation_is_static():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/manual_glb_server.py").read_text()
    assert 'host="127.0.0.1"' in source
    assert "0.0.0.0" not in source
    for prohibited in ("MeshyMultiImageProvider", "requests.Session", "keychain", "resolve_provider"):
        assert prohibited not in source
    app = create_manual_glb_app(root)
    assert app.config["MAX_CONTENT_LENGTH"] == 250 * 1024 * 1024


def test_orientation_dropdown_exactly_matches_ordered_backend_contract():
    root = Path(__file__).resolve().parents[1]
    app = create_manual_glb_app(root)
    with app.test_client() as client:
        response = client.get("/")
        repeated = client.get("/")
    assert response.status_code == 200
    assert "Inspect first; choose before Normalize…" in response.get_data(as_text=True)
    parser = _OrientationOptions()
    parser.feed(response.get_data(as_text=True))
    assert parser.values[0] == ""
    rendered = parser.values[1:]
    assert rendered == list(ORIENTATION_MAPPING_OPTIONS)
    repeated_parser = _OrientationOptions()
    repeated_parser.feed(repeated.get_data(as_text=True))
    assert repeated_parser.values[1:] == rendered
    assert set(rendered) == ORIENTATION_MAPPINGS
    assert all(value in ORIENTATION_MAPPINGS for value in rendered)
    assert len(rendered) == len(ORIENTATION_MAPPINGS) == 24
    assert "+X,+Y" in rendered
    assert "+X,-X" not in rendered


def test_launcher_resolves_project_root_independent_of_caller_cwd(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    project = tmp_path / "Project With Spaces"
    scripts = project / "scripts"
    python_dir = project / ".venv/bin"
    scripts.mkdir(parents=True)
    python_dir.mkdir(parents=True)
    launcher = scripts / "run_manual_glb_ui.command"
    shutil.copy2(root / "scripts/run_manual_glb_ui.command", launcher)
    marker = tmp_path / "launcher-result.txt"
    fake_python = python_dir / "python"
    fake_python.write_text(
        "#!/bin/zsh\nprint -r -- \"$PWD|$*\" > \"$SKYFORGE_LAUNCHER_TEST_MARKER\"\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    environment = {**os.environ, "SKYFORGE_LAUNCHER_TEST_MARKER": str(marker)}
    completed = subprocess.run(["/bin/zsh", str(launcher)], cwd=tmp_path, env=environment, check=False)
    assert completed.returncode == 0
    assert marker.read_text().strip() == f"{project}|-m app.manual_glb_server"
