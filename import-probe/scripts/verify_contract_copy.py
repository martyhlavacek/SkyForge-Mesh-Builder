from __future__ import annotations

import hashlib
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PACKAGE_ROOT / "CONTRACTS_SHA256SUMS.txt"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    failures: list[str] = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        path = PACKAGE_ROOT / relative
        if not path.is_file():
            failures.append(f"missing:{relative}")
        elif sha256(path) != expected:
            failures.append(f"changed:{relative}")
    if failures:
        raise SystemExit("Contract copy verification failed: " + ", ".join(failures))
    print("Independent frozen contract copy verified")


if __name__ == "__main__":
    main()
