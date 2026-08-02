from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .errors import ProbeReject

ALLOWED_SUFFIXES = {".json", ".glb", ".png", ".txt"}
EXECUTABLE_SUFFIXES = {".command", ".sh", ".py", ".exe", ".bat", ".cmd", ".app"}


@dataclass(frozen=True)
class ArchiveLimits:
    max_members: int = 128
    max_member_uncompressed_bytes: int = 64 * 1024 * 1024
    max_total_uncompressed_bytes: int = 256 * 1024 * 1024
    max_compression_ratio: float = 100.0


@dataclass(frozen=True)
class ArchiveSnapshot:
    path: Path
    entries: dict[str, bytes]
    modes: dict[str, int]


def read_archive(path: Path, limits: ArchiveLimits | None = None) -> ArchiveSnapshot:
    limits = limits or ArchiveLimits()
    if not path.is_file():
        raise ProbeReject("archive_missing", "VMP archive does not exist")
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ProbeReject("archive_invalid", "VMP is not a readable ZIP archive") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_members:
            raise ProbeReject("archive_member_limit", "archive contains too many members")
        names: set[str] = set()
        total = 0
        modes: dict[str, int] = {}
        for info in infos:
            if info.is_dir():
                raise ProbeReject("archive_directory_entry", "directory entries are prohibited")
            name = _safe_path(info.filename)
            if name in names:
                raise ProbeReject("archive_duplicate_member", f"duplicate member: {name}")
            names.add(name)
            suffix = PurePosixPath(name).suffix.lower()
            if suffix in EXECUTABLE_SUFFIXES or suffix not in ALLOWED_SUFFIXES:
                raise ProbeReject("archive_executable_type", f"unsupported or executable member: {name}")
            unix_mode = (info.external_attr >> 16) & 0o177777
            modes[name] = unix_mode
            if unix_mode & 0o111:
                raise ProbeReject("archive_executable_mode", f"executable mode is prohibited: {name}")
            if unix_mode & 0o170000 == 0o120000:
                raise ProbeReject("archive_symlink", f"symbolic link is prohibited: {name}")
            if info.file_size > limits.max_member_uncompressed_bytes:
                raise ProbeReject("archive_member_size_limit", f"member exceeds decompressed limit: {name}")
            total += info.file_size
            if total > limits.max_total_uncompressed_bytes:
                raise ProbeReject("archive_total_size_limit", "archive exceeds total decompressed limit")
            ratio = info.file_size / max(1, info.compress_size)
            if ratio > limits.max_compression_ratio:
                raise ProbeReject("archive_compression_ratio", f"member compression ratio is excessive: {name}")
        for name in sorted(names):
            parts = PurePosixPath(name).parts
            for depth in range(1, len(parts)):
                parent = PurePosixPath(*parts[:depth]).as_posix()
                if parent in names:
                    raise ProbeReject(
                        "archive_path_collision",
                        f"package-root member is both a file and a parent: {parent} -> {name}",
                    )
        entries: dict[str, bytes] = {}
        for info in infos:
            name = _safe_path(info.filename)
            try:
                entries[name] = archive.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise ProbeReject("archive_decode_failure", f"failed to read member: {name}") from exc
    return ArchiveSnapshot(path=path, entries=entries, modes=modes)


def _safe_path(raw: str) -> str:
    if not raw or raw.startswith("/") or "\\" in raw:
        raise ProbeReject("archive_path_traversal", f"unsafe archive member path: {raw!r}")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ProbeReject("archive_path_traversal", f"unsafe archive member path: {raw!r}")
    return path.as_posix()
