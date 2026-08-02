from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

BINDING_SCHEMA = "skyforge.sprite-foundry-import-probe-binding.v1"
BINDING_FILENAME = "IMPORT_PROBE_SOURCE_BINDING.json"
IGNORED_PARTS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "workspace",
    }
)
IGNORED_SUFFIXES = frozenset({".pyc", ".pyo"})


class ProbeBindingError(RuntimeError):
    """Raised when the independent probe binding is invalid."""


@dataclass(frozen=True)
class ProbeBindingScope:
    schema_version: str = BINDING_SCHEMA
    binding_filename: str = BINDING_FILENAME
    requirements_filename: str = "requirements.txt"


SCOPE = ProbeBindingScope()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_records(root: Path, scope: ProbeBindingScope = SCOPE) -> dict[str, str]:
    records: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.as_posix() == scope.binding_filename:
            continue
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        if path.suffix in IGNORED_SUFFIXES:
            continue
        records[relative.as_posix()] = sha256_file(path)
    return records


def tree_digest(records: dict[str, str]) -> str:
    payload = "".join(f"{records[path]}  {path}\n" for path in sorted(records))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def exact_pins(lines: Iterable[str]) -> list[str]:
    pins: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.count("==") != 1:
            raise ProbeBindingError(f"Probe dependency is not exactly pinned: {line}")
        name, version = line.split("==", 1)
        if not name or not version or any(token in version for token in (";", " ", "\t")):
            raise ProbeBindingError(f"Probe dependency is not a simple exact pin: {line}")
        pins.append(line)
    if len(pins) != len(set(pins)):
        raise ProbeBindingError("Probe dependency contract contains duplicate pins")
    return pins


def dependency_contract(root: Path, scope: ProbeBindingScope = SCOPE) -> dict[str, object]:
    requirements = root / scope.requirements_filename
    if not requirements.is_file():
        raise ProbeBindingError("Missing independent probe requirements.txt")
    pins = exact_pins(requirements.read_text(encoding="utf-8").splitlines())
    return {
        "requirementsFile": scope.requirements_filename,
        "requirementsSha256": sha256_file(requirements),
        "exactPins": pins,
        "exactPinCount": len(pins),
    }


def build_binding(root: Path, scope: ProbeBindingScope = SCOPE) -> dict[str, object]:
    files = source_records(root, scope)
    return {
        "schemaVersion": scope.schema_version,
        "bindingScope": "independent_import_probe_source_and_declared_dependencies",
        "bindingFile": scope.binding_filename,
        "producerSourceIncluded": False,
        "fileCount": len(files),
        "treeManifestSha256": tree_digest(files),
        "dependencyContract": dependency_contract(root, scope),
        "files": files,
    }


def write_binding(root: Path, scope: ProbeBindingScope = SCOPE) -> dict[str, object]:
    binding = build_binding(root, scope)
    (root / scope.binding_filename).write_text(
        json.dumps(binding, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return binding


def verify_binding(root: Path, scope: ProbeBindingScope = SCOPE) -> dict[str, object]:
    path = root / scope.binding_filename
    if not path.is_file():
        raise ProbeBindingError(f"Missing probe binding: {scope.binding_filename}")
    expected = json.loads(path.read_text(encoding="utf-8"))
    if expected.get("schemaVersion") != scope.schema_version:
        raise ProbeBindingError("Unsupported probe-binding schema")
    if expected.get("producerSourceIncluded") is not False:
        raise ProbeBindingError("Probe binding does not assert producer independence")
    actual = build_binding(root, scope)
    expected_files = expected.get("files")
    if not isinstance(expected_files, dict):
        raise ProbeBindingError("Malformed probe-binding file map")
    expected_paths = set(expected_files)
    actual_paths = set(actual["files"])
    changed = sorted(
        path
        for path in expected_paths & actual_paths
        if expected_files[path] != actual["files"][path]
    )
    added = sorted(actual_paths - expected_paths)
    removed = sorted(expected_paths - actual_paths)
    failures: list[str] = []
    if changed:
        failures.append(f"changed={changed}")
    if added:
        failures.append(f"added={added}")
    if removed:
        failures.append(f"removed={removed}")
    for field in ("fileCount", "treeManifestSha256", "dependencyContract"):
        if expected.get(field) != actual.get(field):
            failures.append(f"{field} mismatch")
    if failures:
        raise ProbeBindingError("Independent probe binding failed: " + "; ".join(failures))
    return {
        "verified": True,
        "bindingFile": scope.binding_filename,
        "fileCount": actual["fileCount"],
        "treeManifestSha256": actual["treeManifestSha256"],
        "dependencyContract": actual["dependencyContract"],
        "producerSourceIncluded": False,
    }
