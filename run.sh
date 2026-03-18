#!/usr/bin/env bash
set -euo pipefail
# Lightweight helper to activate the project's .venv and run the GUI
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT_DIR/.venv"

if [ -f "$VENV/bin/activate" ]; then
  # shellcheck source=/dev/null
  . "$VENV/bin/activate"
  python "$ROOT_DIR/main.py" "$@"
else
  echo "No virtualenv found at $VENV. Create it with:" >&2
  echo "  python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi
