#!/bin/zsh
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  print -u2 "SkyForge manual GLB launcher: virtualenv Python is missing or not executable: $PYTHON"
  exit 1
fi

cd -- "$PROJECT_ROOT"
exec "$PYTHON" -m app.manual_glb_server
