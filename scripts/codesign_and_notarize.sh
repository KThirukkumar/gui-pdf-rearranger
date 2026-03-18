#!/usr/bin/env bash
set -euo pipefail

# Usage: codesign_and_notarize.sh path/to/App.app
# Environment variables required (examples):
# SIGNING_ID="Developer ID Application: Your Name (TEAMID)"
# BUNDLE_ID="com.example.pdfrearranger"
# APPLE_ID and APP_PASSWORD (app-specific password) for notarization
# If you need to import a signing certificate (.p12), set P12_PATH and P12_PASSWORD

APP_PATH="$1"

if [[ ! -d "$APP_PATH" ]]; then
  echo "App bundle not found: $APP_PATH"
  exit 2
fi

if [[ -n "${P12_PATH:-}" ]]; then
  echo "Importing certificate $P12_PATH into login keychain"
  security import "$P12_PATH" -k ~/Library/Keychains/login.keychain -P "$P12_PASSWORD" -T /usr/bin/codesign || true
fi

if [[ -z "${SIGNING_ID:-}" ]]; then
  echo "SIGNING_ID not set; skipping codesign"
else
  echo "Codesigning $APP_PATH with $SIGNING_ID"
  codesign --deep --force --options runtime --sign "$SIGNING_ID" "$APP_PATH"
fi

DMG_PATH="${APP_PATH%/.app}.dmg"
if [[ -f "$DMG_PATH" ]]; then
  echo "Found DMG $DMG_PATH; attempting notarization"
  if command -v xcrun >/dev/null 2>&1 && xcrun notarytool --help >/dev/null 2>&1; then
    if [[ -z "${APPLE_ID:-}" || -z "${APPLE_PASSWORD:-}" ]]; then
      echo "APPLE_ID or APPLE_PASSWORD not set; cannot notarize with notarytool"
    else
      echo "Submitting $DMG_PATH for notarization (notarytool)"
      xcrun notarytool submit "$DMG_PATH" --apple-id "$APPLE_ID" --password "$APPLE_PASSWORD" --team-id "${TEAM_ID:-}" --wait
      echo "Stapling notarization ticket"
      xcrun stapler staple "$DMG_PATH"
    fi
  else
    echo "notarytool unavailable; trying altool (deprecated)"
    if [[ -z "${APPLE_ID:-}" || -z "${APPLE_PASSWORD:-}" ]]; then
      echo "APPLE_ID or APPLE_PASSWORD not set; cannot notarize"
    else
      xcrun altool --notarize-app -f "$DMG_PATH" --primary-bundle-id "${BUNDLE_ID:-com.example.pdfrearranger}" -u "$APPLE_ID" -p "$APPLE_PASSWORD"
      echo "Submitted for notarization. Use Apple's altool/notary status APIs to check." 
    fi
  fi
else
  echo "No DMG found at $DMG_PATH; skipping notarization"
fi

echo "codesign_and_notarize.sh finished"
