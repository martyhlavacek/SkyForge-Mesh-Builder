from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def verify_historical_probe_tree(repository_root: Path, baseline: str) -> None:
    repository_root = repository_root.resolve()
    subprocess.run(
        ["git", "cat-file", "-e", f"{baseline}^{{commit}}"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    changed = subprocess.run(
        ["git", "diff", "--exit-code", baseline, "--", "import-probe"],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if changed.returncode:
        detail = changed.stdout or changed.stderr or "git diff reported a change"
        raise RuntimeError(f"Import Probe differs from {baseline}:\n{detail}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that Import Probe is byte-identical to its historical accepted baseline"
    )
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--baseline", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    verify_historical_probe_tree(args.repository_root, args.baseline)
    print(f"Import Probe matches historical baseline {args.baseline}")


if __name__ == "__main__":
    main()
