#!/bin/bash
set -e
cd "$(dirname "$0")/.."
DEFAULT="/Applications/Blender.app/Contents/MacOS/Blender"
printf "Blender executable [%s]: " "$DEFAULT"
read -r BLENDER_PATH
BLENDER_PATH="${BLENDER_PATH:-$DEFAULT}"
if [ ! -x "$BLENDER_PATH" ]; then
  echo "Not an executable file: $BLENDER_PATH"
  exit 1
fi
python3 - "$BLENDER_PATH" <<'PY'
import json, sys
from pathlib import Path
path = Path('config.json')
if path.exists():
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        payload = {}
else:
    payload = {}
payload['blenderPath'] = sys.argv[1]
path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
PY
echo "Saved Blender path to config.json"
"$BLENDER_PATH" --version | head -n 1
