#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OUTPUT_DIR="${1:-dist-macos}"

ICONSET=".build-macos/AppIcon.iconset"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
for SIZE in 16 32 128 256 512; do
  sips -z "$SIZE" "$SIZE" app_icon.png --out "$ICONSET/icon_${SIZE}x${SIZE}.png" >/dev/null
  DOUBLE=$((SIZE * 2))
  sips -z "$DOUBLE" "$DOUBLE" app_icon.png --out "$ICONSET/icon_${SIZE}x${SIZE}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o .build-macos/app.icns

"$PYTHON_BIN" -m pytest -q
"$PYTHON_BIN" -m PyInstaller \
  --noconfirm --clean --windowed --onedir \
  --name "轻图图片压缩" \
  --osx-bundle-identifier "com.lightimage.compressor" \
  --icon .build-macos/app.icns \
  --add-data "app.ico:." --add-data "app_icon.png:." \
  --collect-all tkinterdnd2 \
  --collect-all pillow_heif \
  --exclude-module numpy --exclude-module pandas --exclude-module matplotlib \
  --exclude-module scipy --exclude-module IPython \
  --distpath "$OUTPUT_DIR" --workpath .build-macos app.py

APP="$OUTPUT_DIR/轻图图片压缩.app"
codesign --deep --force --sign - "$APP"
ARCH=$(uname -m)
ditto -c -k --keepParent --sequesterRsrc "$APP" "$OUTPUT_DIR/轻图图片压缩-macOS-$ARCH.zip"
echo "Built $APP ($ARCH)"
