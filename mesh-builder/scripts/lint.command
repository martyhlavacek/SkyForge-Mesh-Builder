#!/bin/bash
set -e
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then
  echo "Run scripts/setup.command first."
  exit 1
fi
. .venv/bin/activate
ruff check .
