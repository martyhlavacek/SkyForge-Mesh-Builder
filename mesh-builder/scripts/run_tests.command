#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv. Run 'Launch SkyForge Mesh Builder.command' once to install the exact dependency set."
  exit 1
fi
source .venv/bin/activate
python scripts/seal_release.py --preflight-only
