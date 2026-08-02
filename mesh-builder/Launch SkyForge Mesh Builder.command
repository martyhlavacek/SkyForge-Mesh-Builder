#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PORT="${PORT:-5179}"
URL="http://127.0.0.1:${PORT}"

if curl -fsS "$URL/api/health" >/dev/null 2>&1; then
  open "$URL"
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install Python 3.11 or newer, then launch again."
  read -r -p "Press Return to close..." _
  exit 1
fi

REQ_HASH="$(shasum -a 256 requirements.txt | awk '{print $1}')"
MARKER=".venv/.skyforge-requirements-sha256"
INSTALLED_HASH=""
if [ -f "$MARKER" ]; then
  INSTALLED_HASH="$(cat "$MARKER")"
fi

if [ ! -x .venv/bin/python ] || [ "$REQ_HASH" != "$INSTALLED_HASH" ]; then
  echo "Preparing SkyForge Mesh Builder. This is automatic on first launch or after an update..."
  rm -rf .venv
  python3 -m venv .venv
  . .venv/bin/activate
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  printf '%s' "$REQ_HASH" > "$MARKER"
else
  . .venv/bin/activate
fi

python -m app.bootstrap

(
  ATTEMPT=0
  while [ "$ATTEMPT" -lt 60 ]; do
    if curl -fsS "$URL/api/health" >/dev/null 2>&1; then
      open "$URL"
      exit 0
    fi
    ATTEMPT=$((ATTEMPT + 1))
    sleep 0.25
  done
) &

printf '\nSkyForge Mesh Builder is starting at %s\n' "$URL"
printf 'Use the Settings button in the app to configure OpenAI and Blender.\n'
printf 'Leave this window open while using the sidecar. Press Control-C to stop it.\n\n'
exec python -m app.server
