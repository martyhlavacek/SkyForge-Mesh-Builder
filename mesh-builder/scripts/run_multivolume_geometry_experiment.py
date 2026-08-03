from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from app.geometry_v2 import generate_multivolume_experiment  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the offline, recipe-driven SkyForge multivolume geometry experiment",
        epilog=(
            "Authority pixels constrain silhouette extents and occupied row spans only. "
            "Recipes supply semantic identities and approximate normalized positions; this script "
            "does not detect semantic landmarks from pixels."
        ),
    )
    parser.add_argument("--authority", required=True, type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = generate_multivolume_experiment(args.authority, args.profile, args.output_dir)
    print(json.dumps({"report": str(result.report_path), "gateResults": result.report["gateResults"]}, indent=2))


if __name__ == "__main__":
    main()
