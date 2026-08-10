#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
PACKAGE_ROOT="${SCRIPT_DIR:h}"
PORT=5180
LOG_DIR="$PACKAGE_ROOT/workspace/pilot_ui/logs"
LOG_FILE="$LOG_DIR/pilot-ui.log"

cd "$PACKAGE_ROOT"
mkdir -p "$LOG_DIR"

if /usr/bin/nc -z 127.0.0.1 "$PORT" >/dev/null 2>&1; then
  echo "SkyForge pilot UI cannot start: localhost port $PORT is already occupied."
  exit 1
fi

if [[ ! -x ".venv/bin/python" ]]; then
  echo "SkyForge pilot UI requires the existing .venv. Run the documented no-spend setup first."
  exit 1
fi

echo "Starting SkyForge v0.8.1 Multiview Meshy Pilot only."
echo "URL: http://127.0.0.1:$PORT"
echo "Log: $LOG_FILE"
echo "No API key is read and no provider network operation occurs at startup."

export PYTHONNOUSERSITE=1
export SKYFORGE_PROVIDER_NETWORK_DISABLED=1
exec .venv/bin/python -m app.pilot_server >>"$LOG_FILE" 2>&1
