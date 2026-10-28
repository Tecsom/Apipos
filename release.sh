#!/usr/bin/env bash
#
# Release interactivo de Apipos + apipos-js (misma versión en los dos repos).
#
# Usage:
#   ./release.sh              # muestra la versión actual y propone la siguiente
#   ./release.sh 2.0.2        # usa esa versión (igual pide confirmación)
#   ./release.sh --dry-run    # revisa todo y corre las pruebas, sin commit/tag/push
#
# Qué hace:
#   1. Lee la versión actual (app-meta.env y ../apipos-js/package.json) y el
#      último release publicado de cada repo, y propone la siguiente.
#   2. Revisa los dos repos: sin cambios sin commit, rama al día con origin y
#      tag vX.Y.Z libre.
#   3. Cambia la versión (app-meta.env; en apipos-js, npm run sync-version) y
#      corre las pruebas de los dos repos. Si algo falla, revierte y sale.
#   4. Commit "chore: bump version X.Y.Z" + tag vX.Y.Z en cada repo, y push.
#      El tag de Apipos dispara .github/workflows/build-installers.yml.
#   5. apipos-js: npm run pack y su release vX.Y.Z en BORRADOR con el .tgz.
#   6. Espera los instaladores de Apipos (Windows, macOS, Linux), que quedan en
#      el release vX.Y.Z de Apipos, también en BORRADOR.
#   Nunca publica: los dos releases se publican a mano en GitHub. Solo entonces
#   el auto-updater de las cajas ve la versión nueva.
#
# apipos-js en otra ruta:  APIPOS_JS_DIR=/ruta/a/apipos-js ./release.sh
# Recompilar un tag que ya existe:  ./build-installers.sh X.Y.Z --rebuild
#
# Requisitos: git, node/npm y GitHub CLI (`gh`) con sesión (`gh auth login`).

set -Eeuo pipefail

cd "$(dirname "$0")"
APIPOS_DIR="$PWD"
WORKFLOW="build-installers.yml"

die() { echo "❌ $*" >&2; exit 1; }
confirm() {
  local answer
  read -r -p "$1 [s/N]: " answer || true
  [[ "$answer" =~ ^[sSyY]$ ]]
}
read_meta() { grep -E "^$1=" "$APIPOS_DIR/app-meta.env" | head -n1 | cut -d= -f2-; }

# 0 when $1 > $2 (X.Y.Z, numeric per part).
version_gt() {
  local a1 a2 a3 b1 b2 b3
  IFS=. read -r a1 a2 a3 <<< "$1"
  IFS=. read -r b1 b2 b3 <<< "$2"
  if (( 10#$a1 != 10#$b1 )); then (( 10#$a1 > 10#$b1 )); return; fi
  if (( 10#$a2 != 10#$b2 )); then (( 10#$a2 > 10#$b2 )); return; fi
  (( 10#$a3 > 10#$b3 ))
}

latest_release() {  # $1 = repo dir -> tag of the latest published release
  (cd "$1" && gh release view --json tagName -q .tagName 2>/dev/null) || echo "(ninguno)"
}

# ---------------------------------------------------------------------------
# What to undo if the script stops halfway (STAGE says how far it got).
# ---------------------------------------------------------------------------
STAGE="checks"
NEW=""
TAG=""
JS_DIR=""

rollback_local() {
  git -C "$APIPOS_DIR" checkout -- app-meta.env
  git -C "$JS_DIR" checkout -- package.json src/version.ts
}

on_exit() {
  local code=$?
  [[ $code -eq 0 ]] && return 0
  case "$STAGE" in
    local)
      echo "↩️  Revirtiendo el cambio de versión (no se commiteó ni subió nada)." >&2
      rollback_local || true
      ;;
    committed)
      echo "⚠️  Quedaron commits/tags ${TAG} locales SIN subir. Para deshacerlos, en cada" >&2
      echo "    repo que los tenga:  git tag -d ${TAG} && git reset --keep HEAD~1" >&2
      ;;
    pushed)
      echo "⚠️  ${TAG} ya está en GitHub (los dos repos). Revisa:" >&2
      echo "    Instaladores:  gh run list --workflow ${WORKFLOW}" >&2
      echo "                   recompilar: ./build-installers.sh ${NEW} --rebuild" >&2
      echo "    apipos-js:     cd ${JS_DIR} && gh release view ${TAG}" >&2
      echo "                   si falta: npm run pack && gh release create ${TAG} \\" >&2
      echo "                     release/*-${NEW}.tgz --draft --verify-tag --title \"apipos-js ${NEW}\" --generate-notes" >&2
      ;;
  esac
}
trap on_exit EXIT

# ---------------------------------------------------------------------------
# 0. Arguments and tools
# ---------------------------------------------------------------------------
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    -*) die "opción desconocida: $arg (usa --help)" ;;
    *) NEW="${arg#v}" ;;
  esac
done

for tool in git node npm gh; do
  command -v "$tool" >/dev/null || die "Falta $tool."
done
gh auth status >/dev/null 2>&1 || die "gh no tiene sesión. Corre: gh auth login"

JS_DIR="$(cd "${APIPOS_JS_DIR:-$APIPOS_DIR/../apipos-js}" 2>/dev/null && pwd)" \
  || die "No encuentro apipos-js en ${APIPOS_JS_DIR:-../apipos-js}. Usa APIPOS_JS_DIR=/ruta ./release.sh"
[[ -f "$JS_DIR/package.json" ]] || die "$JS_DIR no tiene package.json (¿es apipos-js?)."

# ---------------------------------------------------------------------------
# 1. Current version and the next one
# ---------------------------------------------------------------------------
APP_NAME="$(read_meta APP_NAME)"
CUR="$(read_meta APP_VERSION)"
[[ "$CUR" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "APP_VERSION inválida en app-meta.env: \"$CUR\""
JS_CUR="$(node -p "require(process.argv[1]).version" "$JS_DIR/package.json")"
JS_PKG_NAME="$(node -p "require(process.argv[1]).name" "$JS_DIR/package.json")"

echo ""
echo "Versión actual"
echo "  ${APP_NAME}:     ${CUR}   (último release publicado: $(latest_release "$APIPOS_DIR"))"
echo "  apipos-js:  ${JS_CUR}   (último release publicado: $(latest_release "$JS_DIR"))"
[[ "$JS_CUR" == "$CUR" ]] \
  || echo "  ⚠️  apipos-js no está en lockstep con ${APP_NAME}; esta versión los vuelve a igualar."

IFS=. read -r MAJ MIN PAT <<< "$CUR"
NEXT_PATCH="${MAJ}.${MIN}.$((10#$PAT + 1))"
NEXT_MINOR="${MAJ}.$((10#$MIN + 1)).0"
NEXT_MAJOR="$((10#$MAJ + 1)).0.0"

if [[ -z "$NEW" ]]; then
  echo ""
  echo "Siguiente versión"
  echo "  1) ${NEXT_PATCH}   patch: correcciones (recomendada)"
  echo "  2) ${NEXT_MINOR}   minor: funciones nuevas compatibles"
  echo "  3) ${NEXT_MAJOR}   major: cambios incompatibles en el API"
  echo "  4) otra"
  read -r -p "Elige [1]: " choice || true
  case "${choice:-1}" in
    1) NEW="$NEXT_PATCH" ;;
    2) NEW="$NEXT_MINOR" ;;
    3) NEW="$NEXT_MAJOR" ;;
    4) read -r -p "Versión (X.Y.Z): " NEW || true; NEW="${NEW#v}" ;;
    *) die "opción inválida: $choice" ;;
  esac
fi
NEW="$(printf '%s' "$NEW" | tr -d '[:space:]')"
[[ "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "versión inválida \"$NEW\". Usa el formato X.Y.Z"
version_gt "$NEW" "$CUR" || die "la versión nueva ($NEW) debe ser mayor que la actual ($CUR)."
TAG="v${NEW}"

# ---------------------------------------------------------------------------
# 2. Both repos: clean, up to date with origin, tag still free
# ---------------------------------------------------------------------------
check_repo() {  # $1 = label, $2 = dir; prints the current branch
  local label="$1" dir="$2" branch
  branch="$(git -C "$dir" rev-parse --abbrev-ref HEAD)"
  [[ "$branch" != "HEAD" ]] || die "$label: HEAD desacoplado; cámbiate a una rama."
  [[ -z "$(git -C "$dir" status --porcelain --untracked-files=no)" ]] \
    || die "$label: hay cambios sin commit. Haz commit o stash primero."
  git -C "$dir" fetch --quiet --tags origin
  if git -C "$dir" rev-parse -q --verify "origin/$branch" >/dev/null \
      && ! git -C "$dir" merge-base --is-ancestor "origin/$branch" HEAD; then
    die "$label: tu rama $branch está atrás de origin/$branch. Haz pull primero."
  fi
  ! git -C "$dir" rev-parse -q --verify "refs/tags/$TAG" >/dev/null \
    || die "$label: el tag $TAG ya existe."
  echo "$branch"
}

outgoing() {  # $1 = dir, $2 = branch -> commits that the push would upload
  local log
  log="$(git -C "$1" log --oneline "origin/$2..HEAD" 2>/dev/null || true)"
  if [[ -n "$log" ]]; then printf '%s\n' "$log" | sed 's/^/      /'; else echo "      (ninguno además del bump)"; fi
}

echo ""
echo "==> Revisando los repos"
APIPOS_BRANCH="$(check_repo "$APP_NAME" "$APIPOS_DIR")"
JS_BRANCH="$(check_repo apipos-js "$JS_DIR")"
JS_TGZ="$JS_DIR/release/$(printf '%s' "$JS_PKG_NAME" | sed -e 's/^@//' -e 's|/|-|')-${NEW}.tgz"

echo ""
if [[ "$DRY_RUN" == 1 ]]; then
  echo "DRY RUN: solo cambia la versión en local, corre las pruebas y lo revierte."
else
  echo "Se va a subir ${TAG} y dejar los dos releases en BORRADOR:"
fi
echo "  ${APP_NAME} (${APIPOS_BRANCH}): ${CUR} -> ${NEW}, commit + tag ${TAG}, push (compila los instaladores)"
echo "    commits que se suben:"
outgoing "$APIPOS_DIR" "$APIPOS_BRANCH"
echo "  apipos-js (${JS_BRANCH}): ${JS_CUR} -> ${NEW}, commit + tag ${TAG}, push, release con $(basename "$JS_TGZ")"
echo "    commits que se suben:"
outgoing "$JS_DIR" "$JS_BRANCH"
echo ""
confirm "¿Continuar?" || { echo "Cancelado; no se cambió nada."; exit 0; }

# ---------------------------------------------------------------------------
# 3. Bump locally and run both test suites (reverted on any failure)
# ---------------------------------------------------------------------------
STAGE="local"
sed -E "s|^APP_VERSION=.*|APP_VERSION=${NEW}|" "$APIPOS_DIR/app-meta.env" > "$APIPOS_DIR/app-meta.env.tmp"
mv "$APIPOS_DIR/app-meta.env.tmp" "$APIPOS_DIR/app-meta.env"
[[ "$(read_meta APP_VERSION)" == "$NEW" ]] || die "no se pudo actualizar APP_VERSION en app-meta.env"

(cd "$JS_DIR" \
  && npm run --silent sync-version -- --from "$APIPOS_DIR/app-meta.env" \
  && npm run --silent check-version -- --from "$APIPOS_DIR/app-meta.env")

TEST_LOG="$(mktemp)"
echo "==> Pruebas de ${APP_NAME}"
if [[ -x "$APIPOS_DIR/.venv/bin/python" ]]; then
  if ! "$APIPOS_DIR/.venv/bin/python" -m pytest "$APIPOS_DIR/tests" -q -p no:cacheprovider > "$TEST_LOG" 2>&1; then
    tail -n 40 "$TEST_LOG"; die "fallaron las pruebas de ${APP_NAME}."
  fi
  grep -E '[0-9]+ passed' "$TEST_LOG" | tail -n 1 | sed 's/^/    /' || true
else
  echo "    (sin .venv: se omiten aquí; el workflow las corre antes de subir los instaladores)"
fi
echo "==> Pruebas de apipos-js"
if ! (cd "$JS_DIR" && npm test) > "$TEST_LOG" 2>&1; then
  tail -n 40 "$TEST_LOG"; die "fallaron las pruebas de apipos-js."
fi
# Summary lines are "# pass N" (TAP) or "ℹ pass N" (spec reporter).
grep -E '(pass|fail) [0-9]+$' "$TEST_LOG" | sed -E 's/^.*(pass|fail) /\1 /' \
  | tr '\n' ' ' | sed 's/^/    /' || true; echo ""
rm -f "$TEST_LOG"

if [[ "$DRY_RUN" == 1 ]]; then
  rollback_local
  STAGE="done"
  echo ""
  echo "✅ Dry run OK: ${TAG} está libre en los dos repos y las pruebas pasan."
  echo "   Se revirtió el cambio de versión; no se commiteó ni subió nada."
  exit 0
fi

# ---------------------------------------------------------------------------
# 4. Commit + tag in both repos, then push (the Apipos tag starts the builds)
# ---------------------------------------------------------------------------
STAGE="committed"
git -C "$APIPOS_DIR" add app-meta.env
git -C "$APIPOS_DIR" commit -q -m "chore: bump version ${NEW}"
git -C "$APIPOS_DIR" tag -a "$TAG" -m "${APP_NAME} ${NEW}"
git -C "$JS_DIR" add package.json src/version.ts
git -C "$JS_DIR" commit -q -m "chore: bump version ${NEW}"
git -C "$JS_DIR" tag -a "$TAG" -m "apipos-js ${NEW}"

# One minute of slack in case the local clock runs ahead of GitHub's.
START_TIME="$(date -u -d '-1 min' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
  || date -u -v-1M +%Y-%m-%dT%H:%M:%SZ)"

echo "==> Subiendo ${APP_NAME} (${APIPOS_BRANCH} + ${TAG})"
git -C "$APIPOS_DIR" push -q origin "$APIPOS_BRANCH" "$TAG"
STAGE="pushed"
echo "==> Subiendo apipos-js (${JS_BRANCH} + ${TAG})"
git -C "$JS_DIR" push -q origin "$JS_BRANCH" "$TAG"

# ---------------------------------------------------------------------------
# 5. apipos-js: package and draft release
# ---------------------------------------------------------------------------
echo "==> Empaquetando apipos-js"
(cd "$JS_DIR" && npm run --silent pack > /dev/null)
[[ -f "$JS_TGZ" ]] || die "npm run pack no generó $JS_TGZ"
(cd "$JS_DIR" && gh release create "$TAG" "$JS_TGZ" --draft --verify-tag \
  --title "apipos-js ${NEW}" --generate-notes > /dev/null)
echo "    release ${TAG} de apipos-js creado en borrador"

# ---------------------------------------------------------------------------
# 6. Wait for the Apipos installers (the workflow creates its draft release)
# ---------------------------------------------------------------------------
echo "==> Buscando la ejecución del workflow de instaladores"
RUN_ID=""
for _ in $(seq 1 30); do
  RUN_ID="$(gh run list --workflow "$WORKFLOW" --event push --limit 10 \
    --json databaseId,createdAt \
    -q "[.[] | select(.createdAt >= \"${START_TIME}\")] | .[0].databaseId // empty")"
  [[ -n "$RUN_ID" ]] && break
  sleep 3
done
[[ -n "$RUN_ID" ]] || die "No apareció la ejecución. Revísala con: gh run list --workflow ${WORKFLOW}"

echo "==> Compilando Windows, macOS y Linux (tarda unos minutos)."
echo "    Ctrl+C solo deja de esperar: el build sigue en GitHub."
if ! gh run watch "$RUN_ID" --exit-status; then
  echo ""
  gh run view "$RUN_ID" --log-failed | tail -n 60 || true
  die "Falló el build de los instaladores. Detalle: $(gh run view "$RUN_ID" --json url -q .url)"
fi

# ---------------------------------------------------------------------------
# 7. Show both drafts (never published here)
# ---------------------------------------------------------------------------
show_release() {  # $1 = label, $2 = repo dir
  echo ""
  echo "$1"
  (cd "$2" && gh release view "$TAG" --json url,isDraft,assets \
    -q '"  \(.url)  (borrador: \(.isDraft))\n" + ([.assets[] | "  - \(.name)  (\(.size / 1048576 * 10 | floor / 10) MB)"] | join("\n"))')
}
STAGE="done"
show_release "$APP_NAME" "$APIPOS_DIR"
show_release "apipos-js" "$JS_DIR"
echo ""
echo "✅ ${TAG} listo en BORRADOR en los dos repos. Publícalos desde GitHub"
echo "   (Releases → Edit → Publish release). Solo entonces el auto-updater de las"
echo "   cajas ofrece la versión nueva."
