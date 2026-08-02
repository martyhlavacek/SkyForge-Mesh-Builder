from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from probe.source_binding import SCOPE, ProbeBindingError, verify_binding, write_binding


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "probe"
    (root / "probe").mkdir(parents=True)
    (root / "probe" / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "requirements.txt").write_text("example==1.0.0\n", encoding="utf-8")
    write_binding(root)
    return root


def test_probe_binding_accepts_unchanged_tree(tmp_path: Path):
    root = _tree(tmp_path)
    result = verify_binding(root)
    assert result["verified"] is True
    assert result["producerSourceIncluded"] is False


@pytest.mark.parametrize("mutation", ["changed", "added", "removed"])
def test_probe_binding_rejects_changed_added_and_removed_files(tmp_path: Path, mutation: str):
    root = _tree(tmp_path)
    source = root / "probe" / "sample.py"
    if mutation == "changed":
        source.write_text("VALUE = 2\n", encoding="utf-8")
    elif mutation == "added":
        (root / "probe" / "added.py").write_text("ADDED = True\n", encoding="utf-8")
    else:
        source.unlink()
    with pytest.raises(ProbeBindingError, match=mutation):
        verify_binding(root)


def test_probe_binding_copy_rejects_replaced_source(tmp_path: Path):
    root = _tree(tmp_path)
    copied = tmp_path / "copied"
    shutil.copytree(root, copied)
    (copied / "probe" / "sample.py").write_text("VALUE = 3\n", encoding="utf-8")
    with pytest.raises(ProbeBindingError, match="changed"):
        verify_binding(copied)


def test_probe_dependency_contract_is_its_own_exact_pin_set(tmp_path: Path):
    root = _tree(tmp_path)
    binding = write_binding(root, SCOPE)
    assert binding["dependencyContract"]["exactPins"] == ["example==1.0.0"]
    (root / "requirements.txt").write_text("example>=1.0\n", encoding="utf-8")
    with pytest.raises(ProbeBindingError, match="not exactly pinned"):
        write_binding(root, SCOPE)
