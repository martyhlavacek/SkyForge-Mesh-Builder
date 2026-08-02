from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from common.source_binding import (
    BindingScope,
    SourceBindingError,
    build_binding,
    verify_binding,
    write_binding,
)


def _fixture_tree(tmp_path: Path, *, schema: str, filename: str) -> tuple[Path, BindingScope]:
    root = tmp_path / "package"
    (root / "app").mkdir(parents=True)
    (root / "app" / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "requirements.txt").write_text("example-dependency==1.2.3\n", encoding="utf-8")
    scope = BindingScope(schema_version=schema, binding_filename=filename)
    write_binding(root, scope)
    return root, scope


@pytest.mark.parametrize(
    ("schema", "filename"),
    [
        ("skyforge.producer-source-binding.v1", "PRODUCER_SOURCE_BINDING.json"),
        ("skyforge.sprite-foundry-import-probe-binding.v1", "IMPORT_PROBE_SOURCE_BINDING.json"),
    ],
)
def test_source_binding_accepts_unchanged_tree(tmp_path: Path, schema: str, filename: str):
    root, scope = _fixture_tree(tmp_path, schema=schema, filename=filename)
    verified = verify_binding(root, scope)
    assert verified["verified"] is True
    assert verified["fileCount"] == 2


@pytest.mark.parametrize("mutation", ["changed", "added", "removed"])
def test_producer_binding_rejects_changed_added_and_removed_files(tmp_path: Path, mutation: str):
    root, scope = _fixture_tree(
        tmp_path,
        schema="skyforge.producer-source-binding.v1",
        filename="PRODUCER_SOURCE_BINDING.json",
    )
    source = root / "app" / "sample.py"
    if mutation == "changed":
        source.write_text("VALUE = 2\n", encoding="utf-8")
    elif mutation == "added":
        (root / "app" / "added.py").write_text("ADDED = True\n", encoding="utf-8")
    else:
        source.unlink()
    with pytest.raises(SourceBindingError, match=mutation):
        verify_binding(root, scope)


@pytest.mark.parametrize("mutation", ["changed", "added", "removed"])
def test_probe_binding_rejects_changed_added_and_removed_files(tmp_path: Path, mutation: str):
    root, scope = _fixture_tree(
        tmp_path,
        schema="skyforge.sprite-foundry-import-probe-binding.v1",
        filename="IMPORT_PROBE_SOURCE_BINDING.json",
    )
    source = root / "app" / "sample.py"
    if mutation == "changed":
        source.write_text("VALUE = 2\n", encoding="utf-8")
    elif mutation == "added":
        (root / "app" / "added.py").write_text("ADDED = True\n", encoding="utf-8")
    else:
        source.unlink()
    with pytest.raises(SourceBindingError, match=mutation):
        verify_binding(root, scope)


def test_dependency_contract_is_bound_and_exactly_pinned(tmp_path: Path):
    root, scope = _fixture_tree(
        tmp_path,
        schema="skyforge.producer-source-binding.v1",
        filename="PRODUCER_SOURCE_BINDING.json",
    )
    binding = build_binding(root, scope)
    assert binding["dependencyContract"]["exactPins"] == ["example-dependency==1.2.3"]
    (root / "requirements.txt").write_text("example-dependency>=1.2\n", encoding="utf-8")
    with pytest.raises(SourceBindingError, match="not exactly pinned"):
        build_binding(root, scope)


def test_binding_is_independent_of_ignored_runtime_residue(tmp_path: Path):
    root, scope = _fixture_tree(
        tmp_path,
        schema="skyforge.producer-source-binding.v1",
        filename="PRODUCER_SOURCE_BINDING.json",
    )
    before = build_binding(root, scope)
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "sample.pyc").write_bytes(b"runtime")
    (root / ".pytest_cache").mkdir()
    (root / ".pytest_cache" / "state").write_text("state", encoding="utf-8")
    after = build_binding(root, scope)
    assert before == after


def test_binding_copy_fails_after_source_tree_is_replaced(tmp_path: Path):
    root, scope = _fixture_tree(
        tmp_path,
        schema="skyforge.producer-source-binding.v1",
        filename="PRODUCER_SOURCE_BINDING.json",
    )
    copied = tmp_path / "copied"
    shutil.copytree(root, copied)
    (copied / "app" / "sample.py").write_text("VALUE = 9\n", encoding="utf-8")
    with pytest.raises(SourceBindingError, match="changed"):
        verify_binding(copied, scope)
