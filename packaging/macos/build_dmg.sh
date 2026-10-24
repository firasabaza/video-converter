#!/usr/bin/env bash
# Construit « Video Converter.app » (Python + FFmpeg intégrés) et l'image disque .dmg.
# Prérequis : macOS, Homebrew (brew install ffmpeg), uv, outils Xcode en ligne de commande.
set -euo pipefail
cd "$(dirname "$0")/../.."
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

NAME="Video Converter"
VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)
ARCH=$(uname -m)
BUILD=build/macos
APP="dist/$NAME.app"
DMG="dist/Video-Converter-$VERSION-macOS-$ARCH.dmg"

rm -rf "$BUILD" "dist/$NAME" "$APP" "$DMG"
mkdir -p "$BUILD"

echo "==> Icône"
swift packaging/macos/make_icon.swift "$BUILD/icon.png"
ICONSET="$BUILD/AppIcon.iconset"
mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$BUILD/icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s * 2)) $((s * 2)) "$BUILD/icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$BUILD/AppIcon.icns"

echo "==> Application (PyInstaller)"
uv sync --group macapp --quiet
uv run --group macapp pyinstaller --noconfirm --clean --windowed \
  --name "$NAME" \
  --osx-bundle-identifier com.firasabaza.videoconverter \
  --icon "$PWD/$BUILD/AppIcon.icns" \
  --paths "$PWD/src" \
  --collect-submodules uvicorn \
  --add-data "$PWD/src/video_converter/static:video_converter/static" \
  --workpath "$BUILD/pyinstaller" --specpath "$BUILD" \
  packaging/macos/app_main.py

echo "==> FFmpeg intégré"
python3 packaging/macos/bundle_ffmpeg.py "$APP/Contents/Resources/ffmpeg"

PLIST="$APP/Contents/Info.plist"
plutil -replace LSUIElement -bool true "$PLIST"
plutil -replace CFBundleShortVersionString -string "$VERSION" "$PLIST"
plutil -replace CFBundleVersion -string "$VERSION" "$PLIST"
plutil -replace CFBundleDisplayName -string "$NAME" "$PLIST"
plutil -replace LSMinimumSystemVersion -string "$(sw_vers -productVersion | cut -d. -f1).0" "$PLIST"
codesign --force --sign - "$APP"
codesign --verify "$APP"

echo "==> Image disque"
STAGE="$BUILD/dmg"
rm -rf "$STAGE" && mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "$NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "dist/$NAME"

echo "==> Terminé : $DMG ($(du -h "$DMG" | cut -f1))"
