#!/usr/bin/env bash
#
# Build the Linux installer (.tar.gz with install.sh) for Apipos.
#
# Usage:
#   ./build-linux.sh           # asks for the version
#   ./build-linux.sh 1.0.5     # uses that version (no prompts)
#
# Notes:
#   - The version is written back to app-meta.env before building.
#   - wxPython has no Linux wheels on PyPI; they are taken from
#     extras.wxpython.org for this distro (e.g. ubuntu-22.04). If there is no
#     wheel for it, pip compiles wxPython from source (slow, needs GTK headers).
#   - The bundle links against the build machine's glibc: build on the oldest
#     distro you want to support (CI uses Ubuntu 22.04).
#   - The result is dist/Apipos-<version>-linux-<arch>.tar.gz.

set -euo pipefail

cd "$(dirname "$0")"

# --- App metadata (single source of truth) --------------------------------
read_meta() { grep -E "^$1=" app-meta.env | head -n1 | cut -d= -f2-; }
APP_NAME="$(read_meta APP_NAME)"
APP_VERSION="$(read_meta APP_VERSION)"
APP_PUBLISHER="$(read_meta APP_PUBLISHER)"
APP_BUNDLE_ID="$(read_meta APP_BUNDLE_ID)"
# Exported so apipos-linux.spec can read them.
export APP_NAME APP_VERSION APP_PUBLISHER APP_BUNDLE_ID

SPEC="apipos-linux.spec"
VENV=".venv"
HOST_ARCH="$(uname -m)"  # x86_64 | aarch64

# ---------------------------------------------------------------------------
# 0. Choose the version and write it back to app-meta.env
# ---------------------------------------------------------------------------
NEW_VERSION="${1:-}"
if [[ -z "$NEW_VERSION" ]]; then
  echo "Versión actual: ${APP_VERSION}"
  # `|| true` para no abortar por `set -e` si no hay terminal interactiva.
  read -r -p "Versión a compilar [${APP_VERSION}]: " NEW_VERSION || true
fi
NEW_VERSION="${NEW_VERSION:-$APP_VERSION}"
NEW_VERSION="$(printf '%s' "$NEW_VERSION" | tr -d '[:space:]')"

if [[ ! "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)*$ ]]; then
  echo "ERROR: versión inválida \"$NEW_VERSION\". Usa el formato 1.0.5" >&2
  exit 1
fi

if [[ "$NEW_VERSION" != "$APP_VERSION" ]]; then
  echo "==> Actualizando app-meta.env: ${APP_VERSION} -> ${NEW_VERSION}"
  sed -E "s|^APP_VERSION=.*|APP_VERSION=${NEW_VERSION}|" app-meta.env > app-meta.env.tmp
  mv app-meta.env.tmp app-meta.env
  APP_VERSION="$(read_meta APP_VERSION)"
  export APP_VERSION
  if [[ "$APP_VERSION" != "$NEW_VERSION" ]]; then
    echo "ERROR: no se pudo actualizar APP_VERSION en app-meta.env" >&2
    exit 1
  fi
fi

echo "==> ${APP_NAME} v${APP_VERSION} (${APP_PUBLISHER}) — linux-${HOST_ARCH}"

# ---------------------------------------------------------------------------
# 1. Virtual environment + dependencies
# ---------------------------------------------------------------------------
if [[ ! -d "$VENV" ]]; then
  echo "==> Creando entorno virtual en $VENV"
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# Wheels de wxPython para esta distro (ej. .../gtk3/ubuntu-22.04).
WX_WHEELS=""
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  WX_WHEELS="https://extras.wxpython.org/wxPython4/extras/linux/gtk3/${ID}-${VERSION_ID}"
fi

echo "==> Instalando dependencias (requirements-macos.txt + pyinstaller)"
pip install --upgrade pip >/dev/null
if [[ -n "$WX_WHEELS" ]]; then
  echo "    wxPython desde $WX_WHEELS"
  pip install -f "$WX_WHEELS" -r requirements-macos.txt >/dev/null
else
  pip install -r requirements-macos.txt >/dev/null
fi
pip install pyinstaller >/dev/null

# ---------------------------------------------------------------------------
# 2. Clean previous artifacts
# ---------------------------------------------------------------------------
echo "==> Limpiando build/ y dist/"
rm -rf build dist

# ---------------------------------------------------------------------------
# 3. Build the bundle with PyInstaller
# ---------------------------------------------------------------------------
echo "==> Empaquetando con PyInstaller"
pyinstaller --noconfirm "$SPEC"

BUNDLE="dist/${APP_NAME}"
if [[ ! -x "${BUNDLE}/${APP_NAME}" ]]; then
  echo "ERROR: no se generó ${BUNDLE}/${APP_NAME}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 4. Package into a .tar.gz with the install script
# ---------------------------------------------------------------------------
PKG_NAME="${APP_NAME}-${APP_VERSION}-linux-${HOST_ARCH}"
STAGE="dist/${PKG_NAME}"
TARBALL="dist/${PKG_NAME}.tar.gz"

echo "==> Creando $TARBALL"
mkdir -p "$STAGE"
mv "$BUNDLE" "$STAGE/${APP_NAME}"
cp assets/app-icon.png "$STAGE/app-icon.png"
sed -e "s|@APP_NAME@|${APP_NAME}|g" -e "s|@APP_BUNDLE_ID@|${APP_BUNDLE_ID}|g" \
  installer-linux.sh > "$STAGE/install.sh"
chmod +x "$STAGE/install.sh"
tar -C dist -czf "$TARBALL" "$PKG_NAME"

echo ""
echo "✅ Listo:"
echo "   Bundle:  $STAGE/${APP_NAME}/${APP_NAME}"
echo "   Tarball: $TARBALL"
echo ""
echo "Para instalar: tar xzf ${PKG_NAME}.tar.gz && ./${PKG_NAME}/install.sh"
