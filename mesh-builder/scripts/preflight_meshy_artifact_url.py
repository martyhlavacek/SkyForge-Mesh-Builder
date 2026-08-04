from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from app.reconstruction_v1.preflight import preflight_artifact_url  # noqa: E402
from app.reconstruction_v1.provider import DEFAULT_ARTIFACT_HOST_POLICY  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Meshy artifact URL without downloading artifact bytes.")
    parser.add_argument("url")
    args = parser.parse_args()
    report = preflight_artifact_url(args.url, policy=DEFAULT_ARTIFACT_HOST_POLICY)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["finalDecision"] == "ALLOW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
