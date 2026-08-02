from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from app.providers.meshy_test_mode import MeshyTestModeAdapter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the zero-credit Meshy transport diagnostic")
    parser.add_argument("authority", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--allow-network", action="store_true", help="Required explicit network gate")
    args = parser.parse_args()
    adapter = MeshyTestModeAdapter(requests.Session(), network_enabled=args.allow_network)
    result = adapter.run(authority_path=args.authority, output_dir=args.output_dir)
    print(
        json.dumps(
            {
                "taskId": result.task_id,
                "providerStatus": result.provider_status,
                "consumedCreditsInformational": result.consumed_credits_informational,
                "pep": str(result.pep_path),
                "vmpProduced": result.vmp_produced,
                "promotionPermitted": result.promotion_permitted,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
