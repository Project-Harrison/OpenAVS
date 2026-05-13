#!/bin/bash
set -e
echo "==> OpenAVS macOS build"

# ── 1. PyInstaller ────────────────────────────────────────────────────────────
echo "==> Installing PyInstaller..."
uv add --dev pyinstaller

# ── 2. App icon PNG → ICNS ───────────────────────────────────────────────────
echo "==> Building icon..."
ICONSET="OpenAVS.iconset"
SRC="assets/images/thumbnail.png"
ICNS="assets/images/OpenAVS.icns"

mkdir -p "$ICONSET"
sips -z 16   16   "$SRC" --out "$ICONSET/icon_16x16.png"      > /dev/null
sips -z 32   32   "$SRC" --out "$ICONSET/icon_16x16@2x.png"   > /dev/null
sips -z 32   32   "$SRC" --out "$ICONSET/icon_32x32.png"      > /dev/null
sips -z 64   64   "$SRC" --out "$ICONSET/icon_32x32@2x.png"   > /dev/null
sips -z 128  128  "$SRC" --out "$ICONSET/icon_128x128.png"    > /dev/null
sips -z 256  256  "$SRC" --out "$ICONSET/icon_128x128@2x.png" > /dev/null
sips -z 256  256  "$SRC" --out "$ICONSET/icon_256x256.png"    > /dev/null
sips -z 512  512  "$SRC" --out "$ICONSET/icon_256x256@2x.png" > /dev/null
sips -z 512  512  "$SRC" --out "$ICONSET/icon_512x512.png"    > /dev/null
sips -z 1024 1024 "$SRC" --out "$ICONSET/icon_512x512@2x.png" > /dev/null
iconutil -c icns "$ICONSET" -o "$ICNS"
rm -rf "$ICONSET"
echo "    icon → $ICNS"

# ── 3. PyInstaller build ─────────────────────────────────────────────────────
echo "==> Building OpenAVS.app..."
uv run pyinstaller OpenAVS.spec --clean --noconfirm

# ── 4. DMG ───────────────────────────────────────────────────────────────────
echo "==> Creating DMG..."
rm -f dist/OpenAVS.dmg
hdiutil create \
    -volname  "OpenAVS" \
    -srcfolder dist/OpenAVS.app \
    -ov \
    -format   UDZO \
    dist/OpenAVS.dmg

echo ""
echo "==> Done."
echo "    App : dist/OpenAVS.app"
echo "    DMG : dist/OpenAVS.dmg"
echo ""
echo "    NOTE: First launch on another Mac requires right-click → Open"
echo "    (Gatekeeper warning — no code signing applied)"
echo ""
echo "    To enable AIS, place a config.json in:"
echo "    ~/Library/Application Support/OpenAVS/config.json"
echo "    Contents: { \"SAURAHBN_AIS\": \"your_key_here\" }"
