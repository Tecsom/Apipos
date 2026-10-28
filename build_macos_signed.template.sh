#!/usr/bin/env bash
#
# Build + FIRMA + NOTARIZA el instalador de macOS (.app + .dmg) para Apipos.
#
# >>> VERSIÓN "SEGURA DE SUBIR" <<<
# Igual que build_macos_signed.sh pero SIN credenciales hardcodeadas.
# Las solicita en un pequeño formulario interactivo (o las toma de variables
# de entorno). Así este archivo se puede commitear/compartir sin filtrar tu
# certificado, Team ID ni Apple ID.
#
# Usage:
#   ./build_macos_signed.template.sh                 # pregunta arch + credenciales
#   ./build_macos_signed.template.sh arm64           # Apple Silicon
#   ./build_macos_signed.template.sh x86_64          # Intel
#   ./build_macos_signed.template.sh universal2      # Universal (Intel + Apple Silicon)
#
# También puedes evitar el formulario exportando variables de entorno
# (útil en CI o para no teclear cada vez):
#   export CERT="Developer ID Application: Tu Nombre (XXXXXXXXXX)"
#   export TEAM_ID="XXXXXXXXXX"
#   export APPLE_ID="tu-apple-id@example.com"
#   export NOTARY_PROFILE="notary-profile"
#   ./build_macos_signed.template.sh arm64
#
# Requisitos (una sola vez):
#   1. Un certificado "Developer ID Application" en el Keychain.
#      Verifícalo con: security find-identity -v -p codesigning
#   2. Un perfil de notarización guardado con un App-Specific Password:
#      xcrun notarytool store-credentials "$NOTARY_PROFILE" \
#        --apple-id "$APPLE_ID" --team-id "$TEAM_ID" \
#        --password "TU_APP_SPECIFIC_PASSWORD"
#   3. create-dmg (se instala vía brew si falta).
#
# Notas:
#   - Compilar para una arquitectura distinta a la del host (o universal2)
#     requiere un Python universal2 y wheels universal2 para cada dependencia.
#   - El resultado es dist/Apipos.app y Apipos-<version>-<arch>.dmg firmados,
#     notarizados y con el ticket stapleado.

set -euo pipefail

cd "$(dirname "$0")"

# ===========================================================================
# CONFIG NO SENSIBLE (puedes editar libremente, no contiene secretos)
# ===========================================================================
# Layout/estética del DMG (create-dmg)
APP_ICON_IN_DMG_X=200
APP_ICON_IN_DMG_Y=190
DROP_LINK_X=600
DROP_LINK_Y=185
VOLICON_PATH="app-icon.icns"                   # opcional; se ignora si no existe

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
die() { echo "❌ $*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || die "Falta comando: $1"; }

# Pregunta un valor mostrando (entre corchetes) el default actual si existe.
# Uso: ask VARNAME "Etiqueta" ["default"]
ask() {
  local __var="$1" __label="$2" __default="${3:-}" __input
  local __current="${!__var:-$__default}"
  if [[ -n "$__current" ]]; then
    read -r -p "  $__label [$__current]: " __input
    printf -v "$__var" '%s' "${__input:-$__current}"
  else
    while [[ -z "${__input:-}" ]]; do
      read -r -p "  $__label: " __input
      [[ -z "$__input" ]] && echo "    (requerido)"
    done
    printf -v "$__var" '%s' "$__input"
  fi
}

# ===========================================================================
# FORMULARIO — FIRMA / NOTARIZACIÓN
# ===========================================================================
# Toma defaults de variables de entorno si existen; si no, pide al usuario.
echo "==> Configuración de firma y notarización"
echo "    (Enter para aceptar el valor entre corchetes; deja vacío para teclear)"
echo ""
echo "    💡 Para listar tus certificados disponibles, en otra terminal:"
echo "       security find-identity -v -p codesigning"
echo ""

ask CERT          "Nombre del CERT (identity exacto de 'Developer ID Application')"
ask TEAM_ID       "TEAM_ID (10 caracteres)"
ask APPLE_ID      "APPLE_ID (correo del Apple Developer)"
ask NOTARY_PROFILE "NOTARY_PROFILE (perfil guardado en Keychain)" "notary-profile"

echo ""
echo "==> Usando:"
echo "    CERT           = $CERT"
echo "    TEAM_ID        = $TEAM_ID"
echo "    APPLE_ID       = $APPLE_ID"
echo "    NOTARY_PROFILE = $NOTARY_PROFILE"
echo ""

# Validación mínima
[[ -n "$CERT" ]]    || die "CERT vacío."
[[ -n "$TEAM_ID" ]] || die "TEAM_ID vacío."
[[ -n "$APPLE_ID" ]] || die "APPLE_ID vacío."

# ---------------------------------------------------------------------------
# App metadata (single source of truth)
# ---------------------------------------------------------------------------
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

echo "==> ${APP_NAME} v${APP_VERSION} (${APP_PUBLISHER})"

echo "==> Verificando herramientas..."
need_cmd python3
need_cmd xcrun
need_cmd codesign
need_cmd spctl
need_cmd ditto
need_cmd xattr
need_cmd hdiutil

if ! command -v create-dmg >/dev/null 2>&1; then
  echo "⚠️  create-dmg no encontrado. Instalando con Homebrew..."
  need_cmd brew
  brew install create-dmg
fi

# ---------------------------------------------------------------------------
# 1. Choose the target architecture
# ---------------------------------------------------------------------------
ARCH="${1:-}"
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
# 2. Validar el perfil de notarización ANTES de compilar (falla rápido)
# ---------------------------------------------------------------------------
echo "==> Verificando perfil de notarización en Keychain..."
if ! xcrun notarytool history --keychain-profile "$NOTARY_PROFILE" >/dev/null 2>&1; then
  cat >&2 <<EOF
❌ No existe el perfil '$NOTARY_PROFILE' en Keychain.

Créalo UNA sola vez con un App-Specific Password (NO tu password normal):
  xcrun notarytool store-credentials "$NOTARY_PROFILE" \\
    --apple-id "$APPLE_ID" \\
    --team-id "$TEAM_ID" \\
    --password "TU_APP_SPECIFIC_PASSWORD"

Luego vuelve a correr este script.
EOF
  exit 1
fi

# ---------------------------------------------------------------------------
# 3. Virtual environment + dependencies
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
# What the app imports at startup: if something is missing the bundle builds
# fine but closes as soon as it is opened (TASK-008).
python -c "import flask, flask_cors, PIL, wx, fitz, fontTools" \
  || { echo "ERROR: faltan dependencias en $VENV aunque pip terminó; bórralo y vuelve a correr." >&2; exit 1; }

# ---------------------------------------------------------------------------
# 4. Clean previous artifacts
# ---------------------------------------------------------------------------
DMG="dist/${APP_NAME}-${APP_VERSION}-${ARCH}.dmg"

echo "==> Limpiando build/ y dist/"
rm -rf build dist "${APP_NAME}.app" "$DMG"

# ---------------------------------------------------------------------------
# 5. Build the .app with PyInstaller
# ---------------------------------------------------------------------------
echo "==> Empaquetando con PyInstaller"
if [[ "$ARCH" == "$HOST_ARCH" ]]; then
  APIPOS_TARGET_ARCH="" pyinstaller --noconfirm "$SPEC"
else
  APIPOS_TARGET_ARCH="$ARCH" pyinstaller --noconfirm "$SPEC"
fi

APP_PATH="dist/${APP_NAME}.app"
[[ -d "$APP_PATH" ]] || die "no se generó $APP_PATH"

# ---------------------------------------------------------------------------
# 6. Limpiar atributos de cuarentena (por si el build los arrastra)
# ---------------------------------------------------------------------------
echo "==> Limpiando atributos com.apple.quarantine..."
xattr -dr com.apple.quarantine "$APP_PATH" || true

# ---------------------------------------------------------------------------
# 7. Firmar el .app (Hardened Runtime)
# ---------------------------------------------------------------------------
echo "==> 🔐 Firmando .app (codesign + hardened runtime)..."
codesign --deep --force --verify --verbose \
  --options runtime \
  --timestamp \
  --sign "$CERT" \
  "$APP_PATH"

echo "==> 🔎 Verificando firma..."
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

# ---------------------------------------------------------------------------
# 8. Notarizar el .app (vía ZIP) y staplear el ticket
# ---------------------------------------------------------------------------
ZIP_PATH="dist/${APP_NAME}.zip"
echo "==> 📦 Creando ZIP para notarización..."
rm -f "$ZIP_PATH"
ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"

echo "==> 🛂 Enviando .app a notarización (espera a que termine)..."
xcrun notarytool submit "$ZIP_PATH" \
  --keychain-profile "$NOTARY_PROFILE" \
  --wait

echo "==> 📌 Stapleando ticket al .app..."
xcrun stapler staple "$APP_PATH"

echo "==> ✅ Verificación Gatekeeper (.app)..."
spctl -a -vvv "$APP_PATH" || die "Gatekeeper rechazó la app. Revisa el output de arriba."

rm -f "$ZIP_PATH"

# ---------------------------------------------------------------------------
# 9. Crear el DMG (instalador con drag-to-Applications)
# ---------------------------------------------------------------------------
echo "==> 💿 Creando $DMG..."
rm -f "$DMG"

VOLICON_ARGS=()
if [[ -f "$VOLICON_PATH" ]]; then
  VOLICON_ARGS=(--volicon "$VOLICON_PATH")
else
  echo "    (sin --volicon: $VOLICON_PATH no existe)"
fi

create-dmg \
  --volname "$APP_NAME" \
  "${VOLICON_ARGS[@]}" \
  --window-pos 200 120 \
  --window-size 800 450 \
  --icon-size 100 \
  --icon "${APP_NAME}.app" "$APP_ICON_IN_DMG_X" "$APP_ICON_IN_DMG_Y" \
  --hide-extension "${APP_NAME}.app" \
  --app-drop-link "$DROP_LINK_X" "$DROP_LINK_Y" \
  --skip-jenkins \
  "$DMG" \
  "$APP_PATH"

# ---------------------------------------------------------------------------
# 10. Firmar, notarizar y staplear el DMG
# ---------------------------------------------------------------------------
echo "==> 🔐 Firmando DMG..."
codesign --force --timestamp --sign "$CERT" "$DMG"

echo "==> 🛂 Enviando DMG a notarización (espera a que termine)..."
xcrun notarytool submit "$DMG" \
  --keychain-profile "$NOTARY_PROFILE" \
  --wait

echo "==> 📌 Stapleando ticket al DMG..."
xcrun stapler staple "$DMG"

echo "==> ✅ Verificación Gatekeeper (DMG como instalador)..."
spctl -a -vvv -t install "$DMG" || die "Gatekeeper rechazó el DMG. Revisa el output de arriba."

echo "==> ✅ Validación de stapler (DMG)..."
xcrun stapler validate "$DMG" || die "Stapler validate falló para el DMG."

# ---------------------------------------------------------------------------
# 11. Listo
# ---------------------------------------------------------------------------
echo ""
echo "🎉 LISTO — Release firmado y notarizado para distribución"
echo "   App: $APP_PATH"
echo "   DMG: $DMG"
echo ""
echo "📦 Comparte este archivo: $DMG"
echo ""
