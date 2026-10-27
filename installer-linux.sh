#!/usr/bin/env bash
#
# Instalador de @APP_NAME@ para Linux (por usuario, no necesita sudo).
# build-linux.sh lo copia como install.sh dentro del .tar.gz.
#
# Usage (desde la carpeta descomprimida):
#   ./install.sh               # instala o actualiza, y deja la app corriendo
#   ./install.sh --uninstall   # desinstala
#
# Instala en ~/.local/share/@APP_NAME@, agrega el lanzador al menú de apps y
# el inicio automático al iniciar sesión (~/.config/autostart).

set -euo pipefail

APP_NAME="@APP_NAME@"
DESKTOP_FILE="@APP_BUNDLE_ID@.desktop"

HERE="$(cd "$(dirname "$0")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
DEST="${DATA_HOME}/${APP_NAME}"
APPS_DIR="${DATA_HOME}/applications"
AUTOSTART_DIR="${CONFIG_HOME}/autostart"
EXE="${DEST}/${APP_NAME}"

stop_running() {
  if pkill -x "$APP_NAME" 2>/dev/null; then
    echo "==> Deteniendo ${APP_NAME} en ejecución"
    sleep 1
  fi
}

if [[ "${1:-}" == "--uninstall" ]]; then
  stop_running
  rm -rf "$DEST"
  rm -f "${APPS_DIR}/${DESKTOP_FILE}" "${AUTOSTART_DIR}/${DESKTOP_FILE}"
  echo "✅ ${APP_NAME} desinstalado."
  exit 0
fi

if [[ ! -x "${HERE}/${APP_NAME}/${APP_NAME}" ]]; then
  echo "ERROR: no se encontró ${HERE}/${APP_NAME}/${APP_NAME}" >&2
  echo "       Corre este script desde la carpeta descomprimida del .tar.gz." >&2
  exit 1
fi

stop_running

echo "==> Instalando en ${DEST}"
rm -rf "$DEST"
mkdir -p "$DEST" "$APPS_DIR" "$AUTOSTART_DIR"
cp -a "${HERE}/${APP_NAME}/." "$DEST/"
cp "${HERE}/app-icon.png" "${DEST}/app-icon.png"

desktop_entry() {
  cat <<EOF
[Desktop Entry]
Type=Application
Name=${APP_NAME}
Comment=Servicio local de impresión para el punto de venta
Exec="${EXE}"
Icon=${DEST}/app-icon.png
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
EOF
}

desktop_entry > "${APPS_DIR}/${DESKTOP_FILE}"
desktop_entry > "${AUTOSTART_DIR}/${DESKTOP_FILE}"

echo "==> Iniciando ${APP_NAME}"
nohup "$EXE" >/dev/null 2>&1 &

echo ""
echo "✅ ${APP_NAME} instalado. Arranca solo al iniciar sesión."
echo "   Para desinstalar: ./install.sh --uninstall"
echo ""
echo "Nota: en GNOME el ícono de bandeja requiere la extensión"
echo "      \"AppIndicator and KStatusNotifierItem Support\"."
