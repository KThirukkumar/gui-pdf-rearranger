#!/usr/bin/env bash
set -euo pipefail

ICON_SRC="$1"
OUT_ICNS="$2"

if [[ -z "$ICON_SRC" || -z "$OUT_ICNS" ]]; then
  echo "Usage: $0 path/to/icon.png output.icns"
  exit 2
fi

TMPDIR=$(mktemp -d)
ICONSET="$TMPDIR/icon.iconset"
mkdir -p "$ICONSET"

# create sizes recommended for macOS (.icns)
sizes=(16 32 64 128 256 512 1024)
for s in "${sizes[@]}"; do
  s2=$s
  s3=$((s*2))
  sips -z $s $s "$ICON_SRC" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $s2 $s2 "$ICON_SRC" --out "$ICONSET/icon_${s2}x${s2}.png" >/dev/null || true
done

iconutil -c icns "$ICONSET" -o "$OUT_ICNS"
rm -rf "$TMPDIR"
echo "Created $OUT_ICNS"
