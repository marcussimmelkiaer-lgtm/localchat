#!/usr/bin/env bash
# Build the macOS LocalChat.app + a .dmg (Apple Silicon only).
#
# Run on an arm64 Mac (or your macos-14 CI runner), from the repo root, inside
# the project venv with PyInstaller installed:
#
#     ./packaging/macos/build_mac.sh
#
# Steps:
#   1. Build the frozen LocalChat.app via PyInstaller (packaging/localchat.spec).
#   2. Package the .app into a compressed .dmg — ONE file (~100 MB).
#
# NO models are bundled: the app downloads its default model (Qwen3-4B, ~2.5 GB)
# into the NobodyWho cache on first launch, with progress in the UI (see
# backend/bootstrap.py). Same behavior as the Windows installer.
#
# ARM64 ONLY: nobodywho ships only an arm64 macOS wheel (no x86_64, no sdist), so
# there is no Intel build possible. The venv's Python must be arm64.
#
# SIGNING (deferred): the codesign/notarize block near the bottom is stubbed. Once
# the NobodyWho "Developer ID Application" cert + notarytool profile exist, set
# the env vars and it signs + notarizes; until then it ships unsigned (users
# right-click > Open, or `xattr -dr com.apple.quarantine LocalChat.app`).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

APP_NAME="LocalChat"
DIST="$ROOT/dist"
APP="$DIST/$APP_NAME.app"
DMG="$DIST/$APP_NAME-arm64.dmg"

# --- 0. sanity: arm64 interpreter -------------------------------------------
PY="${PYTHON:-python3}"
ARCH="$("$PY" -c 'import platform; print(platform.machine())')"
if [[ "$ARCH" != "arm64" ]]; then
  echo "ERROR: need an arm64 Python (got '$ARCH'). nobodywho has no Intel wheel." >&2
  echo "       Use an Apple-Silicon Python, or: arch -arm64 $0" >&2
  exit 1
fi
# The frozen .app bundles THIS interpreter; config.py/fetch_model.py import the
# stdlib tomllib, which only exists on 3.11+.
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "ERROR: need Python 3.11+ (tomllib). Got: $("$PY" --version 2>&1)" >&2
  exit 1
fi

# --- 1. freeze --------------------------------------------------------------
echo "==> PyInstaller freeze"
rm -rf "$DIST/$APP_NAME.app" "$DIST/$APP_NAME" build/pyi
"$PY" -m PyInstaller packaging/localchat.spec --noconfirm --distpath "$DIST" --workpath build/pyi

[[ -d "$APP" ]] || { echo "ERROR: $APP not produced" >&2; exit 1; }

# --- 2. sign (deferred) -----------------------------------------------------
# Fill these in once the NobodyWho signing assets exist, then uncomment.
#   DEV_ID="Developer ID Application: NobodyWho ApS (TEAMID)"
#   codesign --deep --force --options runtime --timestamp --sign "$DEV_ID" "$APP"
#   xcrun notarytool submit "$DMG" --keychain-profile "nobodywho-notary" --wait
#   xcrun stapler staple "$APP"
echo "==> (signing/notarization skipped — deferred until certs are available)"

# --- 3. dmg -----------------------------------------------------------------
echo "==> building dmg"
rm -f "$DMG"
if command -v create-dmg >/dev/null 2>&1; then
  create-dmg --volname "$APP_NAME" --app-drop-link 480 170 \
    --icon "$APP_NAME.app" 160 170 --window-size 640 360 \
    "$DMG" "$APP"
else
  # Fallback: plain hdiutil (no fancy layout, but a working drag-install dmg).
  STAGE="$(mktemp -d)"
  cp -R "$APP" "$STAGE/"
  ln -s /Applications "$STAGE/Applications"
  hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
  rm -rf "$STAGE"
fi

echo "==> done: $DMG"
