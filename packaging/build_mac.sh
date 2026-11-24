#!/bin/bash
# Build dist/Bao.app and dist/Bao-<version>-<arch>.dmg.
#   packaging/build_mac.sh            # uses the active venv (needs: pip install -e ".[app]")
#   packaging/build_mac.sh --no-dmg   # app only
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python}"
VERSION="$("$PY" -c 'import tomllib;print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])' 2>/dev/null \
  || sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)"
ARCH="$(uname -m)"

"$PY" -m PyInstaller --version >/dev/null 2>&1 || { echo "PyInstaller missing: pip install -e '.[app]'"; exit 1; }

echo "==> icon"
"$PY" tools/gen_icon.py

echo "==> Bao.app ($VERSION, $ARCH)"
rm -rf build/pyinstaller dist/Bao dist/Bao.app
"$PY" -m PyInstaller --noconfirm --clean --log-level WARN \
  --workpath build/pyinstaller --distpath dist packaging/bao.spec
rm -rf dist/Bao  # the bare COLLECT folder; the .app holds the same files

echo "==> smoke test"
BIN="dist/Bao.app/Contents/MacOS/bao-hook"
"$BIN" -I -c "import bao.hook"
echo '{}' | BAO_NO_LAUNCH=1 "$BIN" -I -m bao.hook
test -d dist/Bao.app/Contents/Resources/bao/characters/panda || test -d dist/Bao.app/Contents/Frameworks/bao/characters/panda

if [[ "${1:-}" != "--no-dmg" ]]; then
  echo "==> dmg"
  DMG="dist/Bao-$VERSION-$ARCH.dmg"
  STAGE="$(mktemp -d)"
  cp -R dist/Bao.app "$STAGE/"
  ln -s /Applications "$STAGE/Applications"
  rm -f "$DMG"
  hdiutil create -quiet -volname "Bao" -srcfolder "$STAGE" -fs HFS+ -format UDZO "$DMG"
  rm -rf "$STAGE"
  echo "built $DMG"
fi
echo "built dist/Bao.app"
