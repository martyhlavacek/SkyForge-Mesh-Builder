from __future__ import annotations

import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from probe.source_binding import write_binding  # noqa: E402


def main() -> None:
    print(json.dumps(write_binding(PACKAGE_ROOT), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
