#!/bin/bash
set -e
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then
  echo "Run scripts/setup.command first."
  exit 1
fi
. .venv/bin/activate
python -m app.server &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT
sleep 1
open http://127.0.0.1:5179 || true
wait $PID
