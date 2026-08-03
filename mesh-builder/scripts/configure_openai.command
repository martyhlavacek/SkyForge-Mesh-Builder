#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -x .venv/bin/python ]; then
  PYTHON=.venv/bin/python
else
  PYTHON=python3
fi

"$PYTHON" -c '
from getpass import getpass
from app.settings_store import save_keychain_key

key = getpass("OpenAI API key: ").strip()
if not key:
    raise SystemExit("API key cannot be empty")
save_keychain_key(key)
print("Saved API key to macOS Keychain using native Security.framework calls.")
'

"$PYTHON" -m app.bootstrap
printf '%s\n' "Open the application Settings panel to review governed stage models, quality, sizes, counts, and budgets."
