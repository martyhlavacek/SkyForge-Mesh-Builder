#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h}"
PARENT="${ROOT:h}"
PROBE_ROOT="${SKYFORGE_IMPORT_PROBE_ROOT:-$PARENT/SkyForge_Sprite_Foundry_Import_Probe_v0.1.1}"
PROBE_PYTHON="${SKYFORGE_IMPORT_PROBE_PYTHON:-$PROBE_ROOT/.venv/bin/python}"
cd "$ROOT"
if [[ ! -x .venv/bin/python ]]; then
  echo "The exact producer environment is missing. Run scripts/setup.command first."
  read -k 1 "?Press any key to close..."
  exit 1
fi
if [[ ! -x "$PROBE_PYTHON" || ! -f "$PROBE_ROOT/scripts/run_import_probe.py" ]]; then
  echo "The separately installed Import Probe environment is missing:"
  echo "$PROBE_ROOT"
  echo "$PROBE_PYTHON"
  read -k 1 "?Press any key to close..."
  exit 1
fi
OUT="$PARENT/SkyForge_v0.7.1_LIVE_BLENDER_PREFLIGHT.zip"
env -u PYTHONPATH PYTHONNOUSERSITE=1 .venv/bin/python scripts/run_live_blender_preflight.py \
  --output "$OUT" --probe-root "$PROBE_ROOT" --probe-python "$PROBE_PYTHON"
open -R "$OUT"
echo "Live Blender preflight completed for all three cleared fixtures."
read -k 1 "?Press any key to close..."
