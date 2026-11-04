---
title: Contribuir
---

# Contribuir

Apipos y su cliente viven en dos repositorios:
[Tecsom/Apipos](https://github.com/Tecsom/Apipos) (el servidor, en Python) y
[Tecsom/apipos-js](https://github.com/Tecsom/apipos-js) (la librería cliente, en
TypeScript). En local se trabajan como carpetas hermanas
(`REPOSITORIES/Apipos` y `REPOSITORIES/apipos-js`). Esta página resume cómo
levantar cada uno, correr sus pruebas, compilar los instaladores y sacar un
release de los dos.

## Desarrollo local de Apipos

Requisitos: **Python 3.9+**.

```bash
# 1. Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Instalar dependencias según el SO
pip install -r requirements-macos.txt     # macOS / Linux
pip install -r requirements-windows.txt   # Windows

# 3. Ejecutar
python apipos.py
```

Verifica que el servicio está arriba:

```bash
curl -s http://localhost:50432/health
```

### Dependencias

| Archivo                     | Plataforma | Incluye                                          |
|-----------------------------|------------|--------------------------------------------------|
| `requirements.txt`          | común      | Flask, Flask-Cors, Pillow, wxPython, **PyMuPDF**, **fontTools** (catálogo de fuentes y subconjunto de fuentes en PDF) |
| `requirements-windows.txt`  | Windows    | + `pywin32`                                      |
| `requirements-macos.txt`    | macOS/Linux| nada extra (usa CUPS del sistema)                |

::: info
`PyMuPDF` es común a ambos SO porque se usa para **rasterizar PDFs** (PDF →
imagen → ESC/POS), necesario para impresoras térmicas.

`fontTools` (puro Python) lee las fuentes instaladas para `GET /fonts` y para
el renderizado de tickets a PDF, y es lo que permite a PyMuPDF incrustar solo
los glifos usados de cada fuente (un ticket con Arial baja de ~1.6 MB a
decenas de KB). Los `.spec` de PyInstaller incluyen sus submódulos
(`collect_submodules('fontTools')`) porque fontTools carga sus tablas de forma
dinámica.

En macOS/Linux la impresión de bajo nivel usa CUPS (`lp` / `lpstat`), que viene
con el sistema. (Opcionalmente, si `python-escpos` está instalado, el backend
usa su wrapper `Lp`.)
:::

### Modo headless (sin bandeja)

Con `APIPOS_NO_TRAY=1`, Apipos corre el API en primer plano sin el ícono de la
bandeja: útil para pruebas, en una máquina sin escritorio o al depurar.

```bash
APIPOS_NO_TRAY=1 python apipos.py
```

- El modo headless no tiene el guard de **una sola instancia por usuario** que
  sí tiene la app de bandeja.
- `APIPOS_LOG_FILE=/ruta/archivo.log` cambia la ruta del log (pruebas, CI).
- El puerto es `50432` (configurable en `src/config.py`).

## Pruebas de Apipos

Las pruebas unitarias viven en `tests/` (separadas de `src/`) y usan **pytest**
con un backend de impresora falso, así que no necesitan impresora ni el servidor
levantado.

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt   # solo la primera vez
python -m pytest tests/ -q
```

`pytest` es dependencia de desarrollo (`requirements-dev.txt`); no se empaca en
los instaladores.

## Desarrollo de apipos-js

Requiere **Node ≥ 22.18** (corre las pruebas y los scripts `.ts` directamente, por
type stripping: `scripts/sync-version.ts` es TypeScript sin compilar y con Node 20
no arranca). El repo trae un `.nvmrc`, así que `nvm use` toma la versión correcta.

```bash
nvm use              # toma el .nvmrc (Node 24)
npm install          # instala TypeScript y @types/node (versiones exactas) y compila (prepare)
npm run build        # tsc → dist/ (.js + .d.ts)
npm test             # build + typecheck de pruebas + node --test (las pruebas importan dist/)
npm run typecheck    # tsc sobre src/ y sobre test/ + scripts/
npm run pack         # release/tecsom-apipos-js-<versión>.tgz
```

Reglas del código (`src/`, `test/`, `scripts/`):

- **Sin `any`** en ninguna forma, sin `@ts-ignore` / `@ts-nocheck` /
  `@ts-expect-error`, sin dobles aserciones y sin el operador `!` de no-nulo.
  Lo que llega de la red entra como `unknown` y se valida con guardas de tipo;
  si la forma no cuadra se lanza `Respuesta inesperada de Apipos en <ruta>`.
- Los imports relativos llevan extensión `.js` (`import { request } from './http.js'`)
  para que el navegador cargue `dist/` sin empaquetador.
- `test/fixtures/invalid-usage.ts` es uso inválido a propósito: una prueba
  compila ese archivo y exige que `tsc` lo rechace.

La versión de apipos-js nunca se edita a mano: siempre es el `APP_VERSION` de
`app-meta.env` de Apipos y se copia con `npm run sync-version` (ver
[Tipos y versionado](../cliente-js/tipos-y-versionado#versionado-en-lockstep-con-apipos)).

## Crear los instaladores

Hay **scripts de build** que automatizan todo (crear venv, instalar
dependencias, empaquetar). Cada build debe hacerse **en su propio sistema
operativo** (PyInstaller no hace cross-compilation entre Windows y macOS), así
que para sacar los tres a la vez se usa GitHub Actions.

### En GitHub Actions (todos los SO)

```bash
./build-installers.sh            # pregunta la versión
./build-installers.sh 2.0.1      # sube la versión, crea el tag y compila
./build-installers.sh 2.0.0 --rebuild   # recompila un tag que ya existe
```

Se corre desde cualquier máquina (Linux, macOS o Git Bash en Windows) y
necesita [GitHub CLI](https://cli.github.com) con sesión (`gh auth login`). El
script escribe la versión en `app-meta.env`, hace commit, crea el tag `vX.Y.Z` y
lo sube. Ese push dispara `.github/workflows/build-installers.yml`, que compila
en paralelo:

| Runner          | Script               | Archivo en el release                 |
|-----------------|----------------------|---------------------------------------|
| `windows-2022`  | `build-windows.bat`  | `Apipos-Setup.exe`                    |
| `macos-14` (arm64) | `build-macos.sh` / `build_macos_signed.template.sh` | `Apipos-X.Y.Z-arm64.dmg` |
| `ubuntu-22.04`  | `build-linux.sh`     | `Apipos-X.Y.Z-linux-x86_64.tar.gz`    |

Además corre los tests. Si todo pasa, sube los tres archivos al release
`vX.Y.Z` **en borrador** y el script pregunta si publicarlo. Mientras siga en
borrador, `releases/latest` no lo muestra, así que las cajas no se actualizan.

Cada job prueba además su binario con `scripts/smoke_binary.py` antes de
subirlo: lo arranca sin bandeja (headless) y comprueba `/health` (con la versión
del tag), `/fonts` y `/render` en PDF y PNG. Si algo falla, el job falla y no se
sube nada al release.

### En tu máquina

| Archivo                  | Plataforma | Salida                                   |
|--------------------------|------------|------------------------------------------|
| `build-macos.sh`         | macOS      | `dist/Apipos.app` + `Apipos-<ver>-<arch>.dmg` |
| `build-windows.bat`      | Windows    | `dist\Apipos.exe` (+ `Apipos-Setup.exe`) |
| `build-linux.sh`         | Linux      | `dist/Apipos-<ver>-linux-<arch>.tar.gz`  |

```bash
./build-macos.sh              # pregunta la arquitectura (arm64, x86_64 o universal2)
./build-linux.sh 2.0.1
```

En Windows, doble clic a `build-windows.bat` o córrelo desde una terminal; si
tienes **Inno Setup** instalado (`iscc` en el PATH), además produce
`dist\Apipos-Setup.exe`. Si un script se detiene porque `pip` falló o porque al
`.venv` le falta algo que la app importa al arrancar, borra `.venv` y vuelve a
correrlo.

**Nombre, versión y publisher** se editan en un solo lugar: `app-meta.env`. Lo
leen los scripts de build, los `.spec` y el instalador de Inno Setup.

::: tip Detalle completo
Arquitecturas de macOS, firma y notarización, Inno Setup, instalación en Linux y
la prueba de humo a mano están en el README de Apipos:
[Crear instalador según el SO](https://github.com/Tecsom/Apipos#crear-instalador-según-el-so).
:::

## Checklist de release (dos repos) {#checklist-de-release-dos-repos}

Apipos y apipos-js van en **lockstep**: la librería `X.Y.Z` está hecha para
Apipos `X.Y.Z`, y un release publica el mismo tag `vX.Y.Z` en ambos repos.

1. En Apipos: `./build-installers.sh X.Y.Z` (ver
   [En GitHub Actions](#en-github-actions-todos-los-so)).
   Cambia `APP_VERSION`, hace el commit `chore: bump version X.Y.Z`, crea el tag
   `vX.Y.Z`, compila Windows / macOS / Linux, corre los tests y sube los
   instaladores al release `vX.Y.Z` (en borrador).
2. En `apipos-js`: `npm run sync-version`, `npm test`, commit
   `chore: bump version X.Y.Z` y tag `vX.Y.Z`.
3. El push del tag a apipos-js dispara `publish.yml`, que publica
   `@tecsom/apipos-js@X.Y.Z` en npm; `release.sh` espera a que termine y, además,
   sube el `.tgz` al release de GitHub como alternativa sin npm.
4. Publicar el release de Apipos (el script lo ofrece al final). Solo entonces
   el auto-updater de las cajas lo ve.

### Release interactivo: `./release.sh`

`release.sh`, en la raíz de Apipos, hace el release de los dos repos con la
misma versión:

```bash
./release.sh              # muestra la versión actual y propone la siguiente
./release.sh 2.0.2        # usa esa versión (igual pide confirmación)
./release.sh --dry-run    # revisa todo y corre las pruebas, sin commit/tag/push
```

1. Lee la versión actual (`app-meta.env` y `../apipos-js/package.json`) y el
   último release publicado de cada repo, y propone la siguiente.
2. Revisa los dos repos: sin cambios sin commit, rama al día con origin y tag
   `vX.Y.Z` libre.
3. Cambia la versión (`app-meta.env`; en apipos-js, `npm run sync-version`) y
   corre las pruebas de los dos repos. Si algo falla, revierte y sale.
4. Commit `chore: bump version X.Y.Z` + tag `vX.Y.Z` en cada repo, y push. El
   tag de Apipos dispara `.github/workflows/build-installers.yml`.
5. apipos-js: `npm run pack` y su release `vX.Y.Z` en **borrador** con el `.tgz`.
   El push del tag ya disparó `.github/workflows/publish.yml` de apipos-js.

   **5b.** Espera la publicación en npm: sigue la ejecución de `publish.yml` y, si
   pasa, comprueba con `npm view` que `@tecsom/apipos-js@X.Y.Z` ya está en el
   registro (reintenta unos segundos mientras npm lo indexa). Si falla, muestra
   el log y sale; la primera vez suele ser porque falta configurar *trusted
   publishing* en npmjs.com (ver la cabecera de `publish.yml`).
6. Espera los instaladores de Apipos (Windows, macOS, Linux), que quedan en el
   release `vX.Y.Z` de Apipos, también en **borrador**.

::: warning
`release.sh` nunca publica los releases de GitHub: los dos se publican a mano.
Solo entonces el auto-updater de las cajas ve la versión nueva. npm, en cambio,
sí queda publicado automáticamente (lo publica `publish.yml` al llegar el tag;
npm no tiene borrador).
:::

Requiere git, node/npm y GitHub CLI (`gh`) con sesión (`gh auth login`). Si
apipos-js está en otra ruta: `APIPOS_JS_DIR=/ruta/a/apipos-js ./release.sh`.
Para recompilar un tag que ya existe: `./build-installers.sh X.Y.Z --rebuild`.
