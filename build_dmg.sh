#!/usr/bin/env bash
set -euo pipefail

APP_NAME="PDF Rearranger"
DIST_DIR="dist"
STAGING_DIR="dmg_staging"

echo "Building macOS app bundle with PyInstaller..."
if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "PyInstaller not found — installing into current env..."
  pip install pyinstaller
fi

rm -rf "$DIST_DIR" "$STAGING_DIR"
pyinstaller --noconfirm --windowed --name "$APP_NAME" main.py

echo "Preparing DMG staging area..."
mkdir -p "$STAGING_DIR"
cp -R "$DIST_DIR/$APP_NAME.app" "$STAGING_DIR/"
# If an icon.png exists in project root, create an .icns and inject into the app bundle
ICON_PNG="icon.png"
ICNS_NAME="app.icns"
if [[ -f "$ICON_PNG" ]]; then
  echo "Found $ICON_PNG — creating $ICNS_NAME and injecting into app bundle"
  mkdir -p "$STAGING_DIR/$APP_NAME.app/Contents/Resources"
  ./scripts/create_icns.sh "$ICON_PNG" "$STAGING_DIR/$APP_NAME.app/Contents/Resources/$ICNS_NAME"
  # update Info.plist to reference the icon
  PLIST="$STAGING_DIR/$APP_NAME.app/Contents/Info.plist"
  if [[ -f "$PLIST" ]]; then
    /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string $ICNS_NAME" "$PLIST" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile $ICNS_NAME" "$PLIST" || true
  fi
fi

ln -s /Applications "$STAGING_DIR/Applications"

DMG_PATH="$DIST_DIR/${APP_NAME}.dmg"
echo "Creating DMG at $DMG_PATH..."
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGING_DIR" -ov -format UDZO "$DMG_PATH"

echo "DMG created: $DMG_PATH"
echo "You can distribute this DMG to macOS users." 

echo "Note: You may need to codesign the .app and notarize with Apple for Gatekeeper if distributing broadly."
