#!/bin/zsh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Install Python 3.11+ first, then rerun this setup."
  read -k 1 "?Press any key to close..."
  exit 1
fi

python3 -m venv .venv
"$HERE/.venv/bin/python" -m pip install --upgrade pip
"$HERE/.venv/bin/python" -m pip install -r requirements-gui.txt

echo
 echo "macOS GUI environment is ready. You can now double-click run_gui.command."
read -k 1 "?Press any key to close..."
