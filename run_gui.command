#!/bin/zsh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

if [[ -x "$HERE/.venv/bin/python" ]]; then
  exec "$HERE/.venv/bin/python" "$HERE/launcher.py"
fi

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$HERE/launcher.py"
fi

if command -v python >/dev/null 2>&1; then
  exec python "$HERE/launcher.py"
fi

echo "No Python executable was found. See docs/INSTALLATION.md"
read -k 1 "?Press any key to close..."
