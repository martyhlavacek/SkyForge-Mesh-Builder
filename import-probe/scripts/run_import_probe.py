from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROBE_ROOT = Path(__file__).resolve().parents[1]
if str(PROBE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROBE_ROOT))

from probe.receipt_writer import write_receipt  # noqa: E402
from probe.source_binding import verify_binding  # noqa: E402
from probe.vmp_validator import import_vmp  # noqa: E402


def main() -> int:
    verify_binding(PROBE_ROOT)
    parser = argparse.ArgumentParser(description="Independently validate a SkyForge VMP v1 package")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = import_vmp(args.archive)
    if args.receipt:
        write_receipt(receipt, args.receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
