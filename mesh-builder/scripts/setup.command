#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
shasum -a 256 requirements.txt | awk '{print $1}' > .venv/.skyforge-requirements-sha256
chmod +x scripts/*.command "Launch SkyForge Mesh Builder.command" "Seal v0.7.1 for Claude.command"
echo "Setup complete with the exact pinned dependency set."
