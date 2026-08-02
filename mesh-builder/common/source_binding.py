from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PRODUCER_BINDING_SCHEMA = "skyforge.producer-source-binding.v1"
PRODUCER_BINDING_FILENAME = "PRODUCER_SOURCE_BINDING.json"
DEFAULT_IGNORED_PARTS = frozenset(
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
DEFAULT_IGNORED_SUFFIXES = frozenset({".pyc", ".pyo"})


class SourceBindingError(RuntimeError):
    """Raised when a source/dependency binding does not match the current tree."""


@dataclass(frozen=True)
class BindingScope:
    schema_version: str
    binding_filename: str
    requirements_filename: str = "requirements.txt"
    ignored_parts: frozenset[str] = DEFAULT_IGNORED_PARTS
    ignored_suffixes: frozenset[str] = DEFAULT_IGNORED_SUFFIXES


PRODUCER_SCOPE = BindingScope(
    schema_version=PRODUCER_BINDING_SCHEMA,
    binding_filename=PRODUCER_BINDING_FILENAME,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_source_records(root: Path, scope: BindingScope) -> dict[str, str]:
    records: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        relative_posix = relative.as_posix()
        if relative_posix == scope.binding_filename:
            continue
        if any(part in scope.ignored_parts for part in relative.parts):
            continue
        if path.suffix in scope.ignored_suffixes:
            continue
        records[relative_posix] = sha256_file(path)
    return records


def tree_manifest_sha256(records: dict[str, str]) -> str:
    payload = "".join(f"{records[path]}  {path}\n" for path in sorted(records))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_exact_pins(lines: Iterable[str]) -> list[str]:
    pins: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line or line.count("==") != 1:
            raise SourceBindingError(f"Dependency is not exactly pinned: {line}")
        name, version = line.split("==", 1)
        if not name or not version or any(token in version for token in (";", " ", "\t")):
            raise SourceBindingError(f"Dependency is not a simple exact pin: {line}")
        pins.append(line)
    if len(pins) != len(set(pins)):
        raise SourceBindingError("Dependency contract contains duplicate exact pins")
    return pins


def dependency_contract(root: Path, scope: BindingScope) -> dict[str, object]:
    requirements = root / scope.requirements_filename
    if not requirements.is_file():
        raise SourceBindingError(f"Missing dependency contract: {scope.requirements_filename}")
    pins = parse_exact_pins(requirements.read_text(encoding="utf-8").splitlines())
    return {
        "requirementsFile": scope.requirements_filename,
        "requirementsSha256": sha256_file(requirements),
        "exactPins": pins,
        "exactPinCount": len(pins),
    }


def build_binding(root: Path, scope: BindingScope) -> dict[str, object]:
    records = collect_source_records(root, scope)
    return {
        "schemaVersion": scope.schema_version,
        "bindingScope": "producer_source_and_declared_dependencies",
        "bindingFile": scope.binding_filename,
        "fileCount": len(records),
        "treeManifestSha256": tree_manifest_sha256(records),
        "dependencyContract": dependency_contract(root, scope),
        "files": records,
    }


def write_binding(root: Path, scope: BindingScope) -> dict[str, object]:
    binding = build_binding(root, scope)
    target = root / scope.binding_filename
    target.write_text(
        json.dumps(binding, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return binding


def verify_binding(root: Path, scope: BindingScope) -> dict[str, object]:
    target = root / scope.binding_filename
    if not target.is_file():
        raise SourceBindingError(f"Missing exact-source binding: {scope.binding_filename}")
    expected = json.loads(target.read_text(encoding="utf-8"))
    if expected.get("schemaVersion") != scope.schema_version:
        raise SourceBindingError("Unsupported source-binding schema")
    actual = build_binding(root, scope)
    failures: list[str] = []
    expected_files = expected.get("files")
    if not isinstance(expected_files, dict):
        raise SourceBindingError("Malformed source-binding file map")
    expected_paths = set(expected_files)
    actual_paths = set(actual["files"])
    changed = sorted(
        path
        for path in expected_paths & actual_paths
        if expected_files[path] != actual["files"][path]
    )
    added = sorted(actual_paths - expected_paths)
    removed = sorted(expected_paths - actual_paths)
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
        raise SourceBindingError("Exact reviewed source binding failed: " + "; ".join(failures))
    return {
        "verified": True,
        "bindingFile": scope.binding_filename,
        "fileCount": actual["fileCount"],
        "treeManifestSha256": actual["treeManifestSha256"],
        "dependencyContract": actual["dependencyContract"],
    }
