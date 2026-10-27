#!/usr/bin/env bash
#
# Compila los instaladores de Windows, macOS (arm64) y Linux en GitHub Actions
# y los sube al Release vX.Y.Z del repo. Se puede correr desde cualquier SO.
#
# Usage:
#   ./build-installers.sh                  # pregunta la versión
#   ./build-installers.sh 2.0.1            # sube la versión, crea el tag y compila
#   ./build-installers.sh 2.0.0 --rebuild  # recompila un tag que ya existe
#
# Qué hace:
#   1. Escribe la versión en app-meta.env y hace commit (si cambió).
#   2. Crea el tag vX.Y.Z y lo sube junto con la rama actual.
#      El push del tag dispara .github/workflows/build-installers.yml.
#   3. Espera a que terminen los builds y muestra el release (en borrador).
#   4. Pregunta si publicar el release (solo entonces lo ve el auto-updater).
#
# Requisitos: git y GitHub CLI (`gh`) con sesión iniciada (`gh auth login`).

set -euo pipefail

cd "$(dirname "$0")"

WORKFLOW="build-installers.yml"

die() { echo "❌ $*" >&2; exit 1; }
confirm() {
  local answer
  read -r -p "$1 [s/N]: " answer || true
  [[ "$answer" =~ ^[sSyY]$ ]]
}

command -v git >/dev/null || die "Falta git."
command -v gh >/dev/null || die "Falta GitHub CLI (gh): https://cli.github.com"
gh auth status >/dev/null 2>&1 || die "gh no tiene sesión. Corre: gh auth login"

# --- App metadata (single source of truth) --------------------------------
read_meta() { grep -E "^$1=" app-meta.env | head -n1 | cut -d= -f2-; }
APP_NAME="$(read_meta APP_NAME)"
APP_VERSION="$(read_meta APP_VERSION)"

# ---------------------------------------------------------------------------
# 0. Arguments and version
# ---------------------------------------------------------------------------
NEW_VERSION=""
REBUILD=0
for arg in "$@"; do
  case "$arg" in
    --rebuild) REBUILD=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) NEW_VERSION="$arg" ;;
  esac
done

if [[ -z "$NEW_VERSION" ]]; then
  echo "Versión actual: ${APP_VERSION}"
  read -r -p "Versión a compilar [${APP_VERSION}]: " NEW_VERSION || true
fi
NEW_VERSION="${NEW_VERSION:-$APP_VERSION}"
NEW_VERSION="$(printf '%s' "$NEW_VERSION" | tr -d '[:space:]')"
NEW_VERSION="${NEW_VERSION#v}"

[[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)*$ ]] \
  || die "versión inválida \"$NEW_VERSION\". Usa el formato 1.0.5"

TAG="v${NEW_VERSION}"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[[ "$BRANCH" != "HEAD" ]] || die "Estás en un HEAD desacoplado; cámbiate a una rama."

echo "==> Consultando tags en origin"
git fetch --tags --quiet origin
TAG_EXISTS=0
git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null && TAG_EXISTS=1

# Lockstep con apipos-js: misma versión en los dos repos (ver README).
JS_PKG="../apipos-js/package.json"
if [[ -f "$JS_PKG" ]]; then
  JS_VERSION="$(sed -nE 's/^[[:space:]]*"version":[[:space:]]*"([^"]+)".*/\1/p' "$JS_PKG" | head -n1)"
  if [[ "$JS_VERSION" != "$NEW_VERSION" ]]; then
    echo "⚠️  apipos-js está en ${JS_VERSION}; Apipos va a ${NEW_VERSION}."
    echo "    Recuerda en apipos-js: npm run sync-version (y su release ${TAG})."
  fi
fi

# Un minuto de margen por si el reloj local va adelantado respecto a GitHub.
START_TIME="$(date -u -d '-1 min' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
  || date -u -v-1M +%Y-%m-%dT%H:%M:%SZ)"

# ---------------------------------------------------------------------------
# 1a. Rebuild an existing tag (workflow_dispatch)
# ---------------------------------------------------------------------------
if [[ "$TAG_EXISTS" == 1 ]]; then
  if [[ "$REBUILD" != 1 ]]; then
    die "El tag ${TAG} ya existe. Para recompilarlo: ./build-installers.sh ${NEW_VERSION} --rebuild"
  fi
  echo ""
  echo "Se va a recompilar ${TAG} (sin commits ni tags nuevos)."
  confirm "¿Continuar?" || exit 1
  gh workflow run "$WORKFLOW" -f tag="$TAG"
  EVENT="workflow_dispatch"

# ---------------------------------------------------------------------------
# 1b. New version: bump, commit, tag, push
# ---------------------------------------------------------------------------
else
  [[ "$REBUILD" != 1 ]] || die "El tag ${TAG} no existe; no hay nada que recompilar."
  [[ -z "$(git status --porcelain --untracked-files=no)" ]] \
    || die "Hay cambios sin commit. Haz commit o stash antes de crear el release."

  git fetch --quiet origin "$BRANCH" 2>/dev/null || true
  if git rev-parse -q --verify "origin/${BRANCH}" >/dev/null \
      && ! git merge-base --is-ancestor "origin/${BRANCH}" HEAD; then
    die "Tu rama ${BRANCH} está atrás de origin/${BRANCH}. Haz pull primero."
  fi

  echo ""
  echo "Se va a:"
  [[ "$NEW_VERSION" != "$APP_VERSION" ]] \
    && echo "  - cambiar APP_VERSION ${APP_VERSION} -> ${NEW_VERSION} y hacer commit"
  echo "  - crear el tag ${TAG}"
  echo "  - subir ${BRANCH} y ${TAG} a origin (dispara los builds en GitHub Actions)"
  confirm "¿Continuar?" || exit 1

  if [[ "$NEW_VERSION" != "$APP_VERSION" ]]; then
    sed -E "s|^APP_VERSION=.*|APP_VERSION=${NEW_VERSION}|" app-meta.env > app-meta.env.tmp
    mv app-meta.env.tmp app-meta.env
    [[ "$(read_meta APP_VERSION)" == "$NEW_VERSION" ]] \
      || die "no se pudo actualizar APP_VERSION en app-meta.env"
    git add app-meta.env
    git commit -m "chore: bump version ${NEW_VERSION}"
  fi

  git tag -a "$TAG" -m "${APP_NAME} ${NEW_VERSION}"
  git push origin "$BRANCH"
  git push origin "$TAG"
  EVENT="push"
fi

# ---------------------------------------------------------------------------
# 2. Wait for the workflow run
# ---------------------------------------------------------------------------
echo "==> Buscando la ejecución del workflow"
RUN_ID=""
for _ in $(seq 1 30); do
  RUN_ID="$(gh run list --workflow "$WORKFLOW" --event "$EVENT" --limit 10 \
    --json databaseId,createdAt \
    -q "[.[] | select(.createdAt >= \"${START_TIME}\")] | .[0].databaseId // empty")"
  [[ -n "$RUN_ID" ]] && break
  sleep 3
done
[[ -n "$RUN_ID" ]] || die "No apareció la ejecución. Revísala en: gh run list --workflow ${WORKFLOW}"

echo "==> Compilando (Windows, macOS, Linux). Esto tarda unos minutos."
if ! gh run watch "$RUN_ID" --exit-status; then
  echo ""
  gh run view "$RUN_ID" --log-failed | tail -n 60 || true
  die "Falló el build. Detalle: $(gh run view "$RUN_ID" --json url -q .url)"
fi

# ---------------------------------------------------------------------------
# 3. Show the release and offer to publish it
# ---------------------------------------------------------------------------
echo ""
gh release view "$TAG" --json url,isDraft,assets \
  -q '"Release: \(.url)\n" + ([.assets[] | "  - \(.name)  (\(.size / 1048576 | floor) MB)"] | join("\n"))'

if [[ "$(gh release view "$TAG" --json isDraft -q .isDraft)" == "true" ]]; then
  echo ""
  echo "El release está en borrador: las cajas no lo ven todavía."
  if confirm "¿Publicarlo ahora (el auto-updater lo ofrecerá a todas las cajas)?"; then
    gh release edit "$TAG" --draft=false --latest
    echo "✅ ${TAG} publicado."
  else
    echo "Para publicarlo después: gh release edit ${TAG} --draft=false --latest"
  fi
fi
