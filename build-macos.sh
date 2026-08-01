#!/usr/bin/env bash
#
# Build the macOS installer (.app + .dmg) for Apipos.
#
# Usage:
#   ./build-macos.sh                 # asks for the version and architecture
#   ./build-macos.sh arm64           # Apple Silicon
#   ./build-macos.sh x86_64          # Intel
#   ./build-macos.sh universal2      # Universal (Intel + Apple Silicon)
#   ./build-macos.sh arm64 1.0.5     # arch + version (no prompts)
#
# Notes:
#   - The version is written back to app-meta.env before building.
#   - Building for an architecture other than the host (or universal2) requires
#     a universal2 Python and universal2 wheels for every dependency. If the
#     build fails for a non-native arch, build natively on the matching Mac.
#   - The result is dist/Apipos.app and Apipos-<arch>.dmg in the project root.

set -euo pipefail

cd "$(dirname "$0")"

# --- App metadata (single source of truth) --------------------------------
read_meta() { grep -E "^$1=" app-meta.env | head -n1 | cut -d= -f2-; }
APP_NAME="$(read_meta APP_NAME)"
APP_VERSION="$(read_meta APP_VERSION)"
APP_PUBLISHER="$(read_meta APP_PUBLISHER)"
APP_BUNDLE_ID="$(read_meta APP_BUNDLE_ID)"
# Exported so apipos-macos.spec can read them.
export APP_NAME APP_VERSION APP_PUBLISHER APP_BUNDLE_ID

SPEC="apipos-macos.spec"
VENV=".venv"
HOST_ARCH="$(uname -m)"  # arm64 on Apple Silicon, x86_64 on Intel

# ---------------------------------------------------------------------------
# 0. Choose the version and write it back to app-meta.env
# ---------------------------------------------------------------------------
ARG_ARCH="${1:-}"
NEW_VERSION="${2:-}"

# Comodidad: si el primer argumento parece una versión (./build-macos.sh 1.0.5),
# tratarlo como tal en vez de como arquitectura.
if [[ -z "$NEW_VERSION" && "$ARG_ARCH" =~ ^[0-9]+\.[0-9]+ ]]; then
  NEW_VERSION="$ARG_ARCH"
  ARG_ARCH=""
fi

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

echo "==> ${APP_NAME} v${APP_VERSION} (${APP_PUBLISHER})"

# ---------------------------------------------------------------------------
# 1. Choose the target architecture
# ---------------------------------------------------------------------------
ARCH="$ARG_ARCH"
if [[ -z "$ARCH" ]]; then
  echo "Selecciona la arquitectura del instalador:"
  echo "  1) Apple Silicon (arm64)"
  echo "  2) Intel (x86_64)"
  echo "  3) Universal (arm64 + x86_64)"
  echo "  4) Nativa de esta Mac ($HOST_ARCH)"
  read -r -p "Opción [4]: " choice
  case "${choice:-4}" in
    1) ARCH="arm64" ;;
    2) ARCH="x86_64" ;;
    3) ARCH="universal2" ;;
    4|"") ARCH="$HOST_ARCH" ;;
    *) echo "Opción inválida"; exit 1 ;;
  esac
fi

echo "==> Arquitectura objetivo: $ARCH (host: $HOST_ARCH)"

# ---------------------------------------------------------------------------
# 2. Virtual environment + dependencies
# ---------------------------------------------------------------------------
if [[ ! -d "$VENV" ]]; then
  echo "==> Creando entorno virtual en $VENV"
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "==> Instalando dependencias (requirements-macos.txt + pyinstaller)"
pip install --upgrade pip >/dev/null
pip install -r requirements-macos.txt >/dev/null
pip install pyinstaller >/dev/null

# ---------------------------------------------------------------------------
# 3. Clean previous artifacts
# ---------------------------------------------------------------------------
DMG="${APP_NAME}-${APP_VERSION}-${ARCH}.dmg"

echo "==> Limpiando build/ y dist/"
rm -rf build dist "${APP_NAME}.app" "$DMG"

# ---------------------------------------------------------------------------
# 4. Build the .app with PyInstaller
# ---------------------------------------------------------------------------
echo "==> Empaquetando con PyInstaller"
if [[ "$ARCH" == "$HOST_ARCH" ]]; then
  APIPOS_TARGET_ARCH="" pyinstaller --noconfirm "$SPEC"
else
  APIPOS_TARGET_ARCH="$ARCH" pyinstaller --noconfirm "$SPEC"
fi

APP_PATH="dist/${APP_NAME}.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "ERROR: no se generó $APP_PATH"
  exit 1
fi

# ---------------------------------------------------------------------------
# 5. Package into a .dmg
# ---------------------------------------------------------------------------
echo "==> Creando $DMG"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$APP_PATH" \
  -ov -format UDZO \
  "$DMG"

echo ""
echo "✅ Listo:"
echo "   App: $APP_PATH"
echo "   DMG: $DMG"
echo ""
echo "Nota: para distribuir fuera de tu equipo, firma y notariza la app"
echo "      (codesign + notarytool) o macOS Gatekeeper la bloqueará."
