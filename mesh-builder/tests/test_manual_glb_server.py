from pathlib import Path

from app.manual_glb_server import create_manual_glb_app


def test_manual_ui_is_localhost_only_and_provider_isolation_is_static():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/manual_glb_server.py").read_text()
    assert 'host="127.0.0.1"' in source
    assert "0.0.0.0" not in source
    for prohibited in ("MeshyMultiImageProvider", "requests.Session", "keychain", "resolve_provider"):
        assert prohibited not in source
    app = create_manual_glb_app(root)
    assert app.config["MAX_CONTENT_LENGTH"] == 250 * 1024 * 1024
