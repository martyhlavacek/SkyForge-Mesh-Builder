#!/bin/zsh
set -euo pipefail
SCRIPT_DIR=${0:A:h}
exec "$SCRIPT_DIR/../.venv/bin/python" -m app.manual_glb_server
