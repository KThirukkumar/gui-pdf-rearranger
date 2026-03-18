#!/usr/bin/env bash
set -euo pipefail

# Build a Windows .exe for PDF Rearranger.
# Usage:
#  ./scripts/build_windows_exe.sh         # attempts to use Docker on macOS/Linux
#  ./scripts/build_windows_exe.sh --local # run locally on Windows (runs pyinstaller)

USE_DOCKER=1
if [[ "${1:-}" == "--local" ]]; then
  USE_DOCKER=0
fi

APP_NAME="PDF Rearranger"
DIST_DIR="dist"

if [[ "$USE_DOCKER" -eq 1 ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker not found. Install Docker or run this script on Windows with --local." >&2
    exit 2
  fi

  echo "Using Docker image cdrx/pyinstaller-windows to build a Windows exe..."
  mkdir -p "$DIST_DIR"
  # Run pyinstaller inside the container and copy artifacts back to host
  docker run --rm -v "$PWD":/src -w /src cdrx/pyinstaller-windows:py3 /bin/bash -lc \
    "pip install --no-cache-dir -r requirements.txt pyinstaller && \
     pyinstaller --noconfirm --windowed --name \"$APP_NAME\" main.py && \
     cp -r dist/ /src/"

  echo "If Docker build succeeded, check $DIST_DIR for the Windows executable (inside a dist/${APP_NAME} folder)."
  exit 0
else
  echo "Running local PyInstaller (assumes you're on Windows with Python and PyInstaller installed)."
  if ! command -v pyinstaller >/dev/null 2>&1; then
    echo "PyInstaller not found. Install it in your environment: pip install pyinstaller" >&2
    exit 2
  fi

  rm -rf "$DIST_DIR"
  pyinstaller --noconfirm --windowed --name "$APP_NAME" main.py
  echo "Local build complete — check $DIST_DIR for the Windows executable."
fi
