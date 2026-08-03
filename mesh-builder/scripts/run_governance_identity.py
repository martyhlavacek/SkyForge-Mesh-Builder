#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(output: Path) -> dict[str, object]:
    baseline = json.loads(
        (PACKAGE_ROOT / "docs/v0.7.1/GOVERNANCE_BASELINE_HASHES.json").read_text(encoding="utf-8")
    )
    files: list[dict[str, object]] = []
    for relative, expected in sorted(baseline["files"].items()):
        path = PACKAGE_ROOT / relative
        actual = sha256_file(path) if path.is_file() else None
        files.append(
            {
                "path": relative,
                "expectedBaselineSha256": expected,
                "candidateSha256": actual,
                "byteIdentical": actual == expected,
            }
        )
    report = {
        "schemaVersion": "skyforge.governance-byte-identity-evidence.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "baselineVersion": baseline["baselineVersion"],
        "files": files,
        "passed": all(bool(item["byteIdentical"]) for item in files),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not report["passed"]:
        raise RuntimeError("Protected governance files are not byte-identical to v0.6.0")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.output.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
