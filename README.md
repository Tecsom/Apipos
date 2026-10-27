# Apipos (Api POS)

API local de impresión para puntos de venta. Corre como una pequeña aplicación
de bandeja (system tray / barra de menú) que expone una API HTTP en
`http://localhost:50432` para imprimir tickets ESC/POS, abrir el cajón de dinero
y listar/seleccionar impresoras.

El mismo código genera instaladores para **Windows** y **macOS**: la única parte
dependiente del sistema operativo (el I/O con la impresora) está aislada en una
capa de _backends_ intercambiable.

---

## Tabla de contenido

- [¿Cómo funciona?](#cómo-funciona)
- [Arquitectura](#arquitectura)
- [Endpoints de la API](#endpoints-de-la-api)
- [Formato de impresión](#formato-de-impresión)
- [Desarrollo local](#desarrollo-local)
- [Pruebas](#pruebas)
- [Librería JS (`apipos-js`)](#librería-js-apipos-js)
- [Crear instalador según el SO](#crear-instalador-según-el-so)
- [Notas](#notas)

---

## ¿Cómo funciona?

1. Al iniciar, [apipos.py](apipos.py) levanta el servidor Flask en un hilo
   secundario (puerto `50432`) y muestra un ícono en la bandeja del sistema.
2. Desde la bandeja el usuario puede elegir la **impresora por defecto**, que se
   guarda en disco (`%APPDATA%\Apipos` en Windows, `~/Apipos` en macOS/Linux).
3. El POS (web/escritorio) hace peticiones HTTP a la API para imprimir. Cada
   petición puede:
   - usar la impresora por defecto, **o**
   - especificar otra impresora y sus _settings_ (tamaño de papel), permitiendo
     **manejar varias impresoras** desde un mismo servicio.
4. La API traduce el contenido recibido a comandos **ESC/POS** y los envía a la
   impresora a través del backend correspondiente al sistema operativo.

El servicio corre 100% local; no envía datos a internet.

---

## Arquitectura

El código está organizado por capas para mantener responsabilidades separadas:

```
apipos.py                      # Entry point: levanta Flask (hilo) + ícono de bandeja
src/
├── app.py                     # create_app(): factory de Flask, registra blueprints
├── config.py                  # Rutas, constantes, puerto, resource_path
├── routes/                    # Definición de endpoints (importan controladores)
│   ├── printer_routes.py
│   └── system_routes.py
├── controllers/               # Solo try/catch → llaman al servicio → responden
│   ├── printer_controller.py
│   └── system_controller.py
├── services/                  # Lógica de negocio + respuesta estandarizada
│   ├── printer_service.py     #   orquesta impresión / cajón / selección
│   ├── escpos_service.py      #   formateo ESC/POS (imágenes, tablas, texto)
│   ├── storage_service.py     #   persiste la impresora por defecto (pickle)
│   └── system_service.py      #   diagnóstico (SO + backend activo)
├── printers/                  # Capa de plataforma (I/O con la impresora)
│   ├── __init__.py            #   get_backend(): elige backend según el SO
│   ├── base.py                #   interfaz PrinterBackend
│   ├── windows_backend.py     #   Windows (win32print / RAW spooler)
│   └── macos_backend.py       #   macOS / Linux (CUPS: lp / lpstat)
├── tray.py                    # Ícono de bandeja (wxPython) — multiplataforma
└── utils/
    └── response.py            # Helpers de respuesta genérica
```

**Flujo de una petición:** `route → controller → service → escpos_service → backend`

- **routes**: declaran la URL y el método; delegan al controlador.
- **controllers**: un único `try/catch`, llaman al servicio y serializan la
  respuesta (mapean `status` → código HTTP). No tienen lógica de negocio.
- **services**: toda la lógica; devuelven siempre la **respuesta estandarizada**.
- **printers** (capa de plataforma): cada backend implementa `list_printers()`,
  `get_printer_width()` y `send_raw()`. `get_backend()` elige el correcto en
  tiempo de ejecución, y las librerías específicas de cada SO (`win32print`, CUPS)
  se importan de forma diferida para que el código nunca falle en el SO contrario.

### Respuesta estandarizada

Todos los servicios devuelven la misma forma:

```json
{
  "status": "success" | "error",
  "data": <T> | null,
  "message": "mensaje específico"
}
```

El controlador mapea: `success` → `200`, error de negocio → `400`, excepción no
controlada → `500`.

---

## Endpoints de la API

Base URL: `http://localhost:50432`

| Método | Ruta                  | Descripción                                        |
|--------|-----------------------|----------------------------------------------------|
| `GET`  | `/health`             | Estado del servicio, SO y backend de impresión activo |
| `GET`  | `/printers`           | Lista las impresoras disponibles en la máquina     |
| `GET`  | `/printers/selected`  | Devuelve la impresora por defecto actual           |
| `POST` | `/printers/selected`  | Cambia la impresora por defecto                    |
| `POST` | `/print`              | Imprime un ticket (`type`: `RAW` ESC/POS o `PDF`)  |
| `POST` | `/render`             | Vista previa: ticket renderizado a PDF/PNG (base64), sin imprimir |
| `GET`  | `/fonts`              | Catálogo de fuentes instaladas (`?refresh=1` re-escanea) |
| `GET`  | `/print/test`         | Imprime el PDF de prueba incluido (`?printer=` opcional) |
| `POST` | `/open-withdrawer`    | Abre el cajón de dinero                            |

### `GET /health`

```json
{
  "status": "success",
  "data": {
    "status": "ok",
    "os": "Darwin",
    "platform": "darwin",
    "backend": "MacPrinterBackend",
    "port": 50432
  },
  "message": "Service is running."
}
```

### `POST /printers/selected`

```json
{ "printer": "EPSON TM-T20" }
```

### `POST /print`

Acepta dos tipos de trabajo según el campo `type`:

- **`"RAW"`** *(por defecto)*: arma un ticket ESC/POS a partir de `content`.
- **`"PDF"`**: imprime un buffer PDF (base64) como documento.

#### Trabajo RAW (ESC/POS)

```json
{
  "printer": "EPSON TM-T20",
  "type": "RAW",
  "settings": { "paper_size": 80 },
  "content": [
    { "type": "text", "data": "MI TIENDA", "align": "center", "font_size": "lg" },
    { "type": "separator" },
    {
      "type": "table",
      "data": { "rows": [["2", "Café", "30.00", "60.00"]] }
    },
    { "type": "special_text", "data": { "text1": "Total", "text2": "$60.00" } },
    { "type": "image", "data": "<base64>", "width": 250 },
    { "type": "open_withdrawer" }
  ]
}
```

- `printer` *(opcional)*: a qué impresora va el trabajo. Si se omite, usa la
  impresora por defecto seleccionada en la bandeja.
- `type` *(opcional)*: `"RAW"` (default) o `"PDF"`.
- `settings` *(opcional, solo RAW)*:
  - `paper_size`: ancho del papel en mm (`80` → 48 columnas, `58` → 32 columnas).
  - `char_width`: número exacto de columnas (sobrescribe a `paper_size`).
  - Si no se envía, se consulta el ancho directamente a la impresora.
- `content` *(solo RAW)*: lista de elementos a imprimir.

**Tipos de elemento (`type`)**

| `type`           | `data`                                             | Notas                                  |
|------------------|----------------------------------------------------|----------------------------------------|
| `text`           | string                                             | `align`: left/center/right; `font_size`: normal/md/lg |
| `special_text`   | `{ "text1": "...", "text2": "..." }`               | Dos textos justificados a los extremos |
| `table`          | `{ "rows": [[cant, prod, precio, importe], ...] }` | Encabezado fijo Cant./Producto/Precio/Importe |
| `separator`      | —                                                  | Línea de guiones a lo ancho            |
| `image`          | string base64; `width` opcional (dots)             | Se convierte a B/N y ESC/POS; conserva la proporcion. Default: 250 dots |
| `open_withdrawer`| —                                                  | Abre el cajón al final del ticket      |

> Compatibilidad: `POST /print` también acepta el formato antiguo (una lista de
> elementos directamente, sin objeto envolvente), usando la impresora por defecto.

#### Trabajo PDF

Envía el PDF como **base64** en el campo `data`:

```json
{
  "printer": "EPSON TM-T20",
  "type": "PDF",
  "data": "JVBERi0xLjQKJ..."
}
```

- `data`: el buffer del PDF en base64 (se acepta también el prefijo
  `data:application/pdf;base64,`).
- Cómo se imprime (`settings.pdf_mode`):
  - **`"raster"` (por defecto, recomendado):** el PDF se convierte a imagen y se
    envía como ESC/POS. Es lo correcto para impresoras térmicas, que **no
    entienden PDF ni PostScript**. Requiere `PyMuPDF` (incluido en requirements).
    Respuesta: `"strategy": "raster"`.
  - **`"document"`:** se entrega el PDF al sistema de impresión del SO (CUPS en
    macOS/Linux, visor por `printto` en Windows). Útil solo para impresoras de
    página completa con driver de PDF/PostScript. En una térmica imprimirá basura.
    Respuesta: `"strategy": "document"`.
- En modo raster se respeta `settings` para el ancho: `paper_size` 80 → 576 px,
  58 → 384 px (o `char_width`). Conviene generar el PDF al ancho del papel.

### `POST /open-withdrawer`

Body opcional `{ "printer": "..." }`; si se omite usa la impresora por defecto.

### `GET /print/test`

Imprime el PDF de prueba incluido en la app (`assets/APIPOS.pdf`, 80mm) usando la
estrategia **raster**. Sirve para validar rápido que una impresora imprime bien.

1. Primero **lista las impresoras** y copia el nombre exacto:

   ```bash
   curl http://localhost:50432/printers
   ```

2. Pasa ese nombre en el query param `printer`:

   ```bash
   curl 'http://localhost:50432/print/test?printer=POS80_Kinwodon'
   ```

- `printer` *(opcional)*: si se omite, usa la impresora por defecto seleccionada.
- También responde a `POST` (mismo comportamiento), por si tu cliente no permite `GET`.
- Requiere `PyMuPDF` instalado (rasterizado). Respuesta: `"strategy": "raster"`.

---

## Formato de impresión

Apipos genera comandos **ESC/POS** (estándar de impresoras térmicas de tickets).
El ancho del ticket se mide en columnas de caracteres: típicamente **32** para
papel de 58 mm y **48** para papel de 80 mm.

### Renderizado de tickets a PDF

Con `settings.renderer: "pdf"` en un trabajo `RAW`, Apipos maqueta el mismo
`content` como un PDF de una sola página (del alto exacto del ticket) usando las
**fuentes instaladas en el sistema** (las que lista `GET /fonts`) o las
integradas `sans-serif` / `serif` / `monospace`, y lo imprime por la ruta PDF
(`pdf_mode: "raw"` lo rasteriza a ESC/POS; `"driver"` lo entrega al driver del
SO). Así el ticket puede llevar tipografías proporcionales, tamaños en puntos,
cursiva, subrayado, columnas de tabla a medida y bloques `html`. `POST /render`
devuelve ese mismo PDF (o un PNG) sin imprimir, para vista previa. El camino
ESC/POS por defecto (`renderer` ausente o `"escpos"`) no cambia: produce
exactamente los mismos bytes de siempre. El contrato completo está en
[APIPOS_API.md](APIPOS_API.md).

---

## Desarrollo local

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

Verificar que el servicio está arriba:

```bash
curl http://localhost:50432/health
```

### Dependencias

| Archivo                     | Plataforma | Incluye                                          |
|-----------------------------|------------|--------------------------------------------------|
| `requirements.txt`          | común      | Flask, Flask-Cors, Pillow, wxPython, **PyMuPDF**, **fontTools** (catálogo de fuentes y subconjunto de fuentes en PDF) |
| `requirements-windows.txt`  | Windows    | + `pywin32`                                      |
| `requirements-macos.txt`    | macOS/Linux| nada extra (usa CUPS del sistema)                |

> `PyMuPDF` es común a ambos SO porque se usa para **rasterizar PDFs** (PDF →
> imagen → ESC/POS), necesario para impresoras térmicas.
>
> `fontTools` (puro Python) lee las fuentes instaladas para `GET /fonts` y para
> el renderizado de tickets a PDF, y es lo que permite a PyMuPDF incrustar solo
> los glifos usados de cada fuente (un ticket con Arial baja de ~1.6 MB a
> decenas de KB). Los `.spec` de PyInstaller incluyen sus submódulos
> (`collect_submodules('fontTools')`) porque fontTools carga sus tablas de forma
> dinámica.
>
> En macOS/Linux la impresión de bajo nivel usa CUPS (`lp` / `lpstat`), que viene
> con el sistema. (Opcionalmente, si `python-escpos` está instalado, el backend
> usa su wrapper `Lp`.)

---

## Pruebas

Las pruebas unitarias viven en `tests/` (separadas de `src/`) y usan **pytest**
con un backend de impresora falso, así que no necesitan impresora ni el servidor
levantado. Las convenciones están en `docs/TESTING.md`.

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt   # solo la primera vez
python -m pytest tests/ -q
```

`pytest` es dependencia de desarrollo (`requirements-dev.txt`); no se empaca en
los instaladores.

---

## Librería JS (`apipos-js`)

`@tecsom/apipos-js` es el cliente oficial de esta API para el front (navegador):
TypeScript estricto compilado a módulos ES con sus tipos (`.d.ts`), sin
dependencias en runtime. Envuelve los endpoints de [APIPOS_API.md](APIPOS_API.md)
(`checkHealth`, `listPrinters`, `listFonts`, `renderTicket`, `createPrinter` →
`print` / `printPDF` / `openDrawer` / `render`). Vive en **su propio repo**,
`Tecsom/apipos-js`; en local es la carpeta hermana `../apipos-js`
(`REPOSITORIES/apipos-js`). Nada de la librería vive en este repo; su uso
detallado está en su README.

### Instalación desde ranitas-pdv

| Caso | Comando (en ranitas-pdv) |
|---|---|
| Desarrollo local (repos hermanos) | `pnpm add -D "file:../apipos-js"` |
| Release, desde git | `pnpm add -D "github:Tecsom/apipos-js#vX.Y.Z"` |
| Release, tarball | `pnpm add -D "https://github.com/Tecsom/apipos-js/releases/download/vX.Y.Z/tecsom-apipos-js-X.Y.Z.tgz"` |

Después, `pnpm run sync:apipos-js`: ranitas-pdv sirve sus módulos estáticos
desde `/public` sin empaquetador, así que copia el `dist/` compilado de la
librería a `public/dist/libs/apipos-js/` (y escribe su `VERSION`).

### Regla de lockstep

- La versión de la librería es **siempre** el `APP_VERSION` de
  [app-meta.env](app-meta.env): la librería `X.Y.Z` está hecha para Apipos
  `X.Y.Z`. Nunca se edita a mano en `apipos-js`: allí `npm run sync-version` la
  copia de `../Apipos/app-meta.env` (o de `--from <ruta>`) a `package.json` y
  `src/version.ts`, y `npm run check-version` sale con código 1 si difieren.
- En runtime se comprueba con el handshake de headers (`X-Apipos-Client` /
  `X-Apipos-Version`, ver "Versionado y handshake" en
  [APIPOS_API.md](APIPOS_API.md)): si el front y el Apipos de la caja no
  coinciden, la librería avisa en la consola del navegador una vez por página
  (por versión distinta de Apipos); con `onVersionMismatch`, una vez por
  cliente. Apipos, por su lado, escribe `[apipos] <mensaje>` en su stdout.
  Nunca bloquea la impresión.
- El front (ranitas-pdv) y el Apipos instalado en las cajas deben ir en la misma
  versión.

### Checklist de release (dos repos)

1. En Apipos: `./build-installers.sh X.Y.Z` (ver
   [Instaladores en GitHub Actions](#instaladores-en-github-actions-todos-los-so)).
   Cambia `APP_VERSION`, hace el commit `chore: bump version X.Y.Z`, crea el tag
   `vX.Y.Z`, compila Windows / macOS / Linux, corre los tests y sube los
   instaladores al release `vX.Y.Z` (en borrador).
2. En `apipos-js`: `npm run sync-version`, `npm test`, commit
   `chore: bump version X.Y.Z` y tag `vX.Y.Z`.
3. `npm run pack` en apipos-js → `release/tecsom-apipos-js-X.Y.Z.tgz` y subirlo
   a su release `vX.Y.Z`.
4. Publicar el release de Apipos (el script lo ofrece al final). Solo entonces
   el auto-updater de las cajas lo ve.

---

## Crear instalador según el SO

Hay **scripts de build** que automatizan todo (crear venv, instalar
dependencias, empaquetar). Cada build debe hacerse **en su propio sistema
operativo** (PyInstaller no hace cross-compilation entre Windows y macOS), así
que para sacar los tres a la vez se usa GitHub Actions.

### Instaladores en GitHub Actions (todos los SO)

```bash
./build-installers.sh            # pregunta la versión
./build-installers.sh 2.0.1      # sube la versión, crea el tag y compila
./build-installers.sh 2.0.0 --rebuild   # recompila un tag que ya existe
```

Se corre desde cualquier máquina (Linux, macOS o Git Bash en Windows) y
necesita [GitHub CLI](https://cli.github.com) con sesión (`gh auth login`). El
script escribe la versión en `app-meta.env`, hace commit, crea el tag `vX.Y.Z` y
lo sube. Ese push dispara
[.github/workflows/build-installers.yml](.github/workflows/build-installers.yml),
que compila en paralelo:

| Runner          | Script               | Archivo en el release                 |
|-----------------|----------------------|---------------------------------------|
| `windows-2022`  | `build-windows.bat`  | `Apipos-Setup.exe`                    |
| `macos-14` (arm64) | `build-macos.sh` / `build_macos_signed.template.sh` | `Apipos-X.Y.Z-arm64.dmg` |
| `ubuntu-22.04`  | `build-linux.sh`     | `Apipos-X.Y.Z-linux-x86_64.tar.gz`    |

Además corre los tests. Si todo pasa, sube los tres archivos al release
`vX.Y.Z` **en borrador** y el script pregunta si publicarlo. Mientras siga en
borrador, `releases/latest` no lo muestra, así que las cajas no se actualizan.

> **Firma de macOS:** sin secrets el `.dmg` sale sin firmar (Gatekeeper lo
> bloquea al descargarlo). Para firmarlo y notarizarlo en CI, agrega en
> *Settings → Secrets and variables → Actions* del repo: `MACOS_CERT_P12`
> (el .p12 del "Developer ID Application" en base64: `base64 -i cert.p12`),
> `MACOS_CERT_PASSWORD`, `MACOS_CERT_NAME`, `APPLE_TEAM_ID`, `APPLE_ID` y
> `APPLE_APP_PASSWORD` (App-Specific Password).

> **Nombre, versión y publisher** se editan en un solo lugar:
> [app-meta.env](app-meta.env). Lo leen ambos scripts de build, los `.spec` y el
> instalador de Inno Setup.

### macOS — `./build-macos.sh`

```bash
./build-macos.sh              # pregunta la arquitectura
# o directo:
./build-macos.sh arm64        # Apple Silicon
./build-macos.sh x86_64       # Intel
./build-macos.sh universal2   # Universal (Intel + Apple Silicon)
```

El script crea/usa `.venv`, instala dependencias, empaqueta con PyInstaller y
genera:
- `dist/Apipos.app` (app de barra de menú, sin ícono en el Dock por `LSUIElement`)
- `Apipos-<arch>.dmg` (instalador para distribuir)

> Construir para una arquitectura distinta a la del equipo (o `universal2`)
> requiere un Python universal2 y wheels universal2 de todas las dependencias. Si
> falla, compila de forma nativa en la Mac correspondiente.
>
> Para distribuir fuera de tu equipo, macOS requiere **firmar** (`codesign`) y
> **notarizar** la app; configura `codesign_identity` en `apipos-macos.spec`.

### Windows — `build-windows.bat`

Doble clic al archivo, o desde una terminal:

```bat
build-windows.bat
```

El script crea/usa `.venv`, instala dependencias, empaqueta con PyInstaller y
genera `dist\Apipos.exe` (app sin consola, vive en la bandeja). Si tienes
**Inno Setup** instalado (`iscc` en el PATH), además compila
[installer-windows.iss](installer-windows.iss) y produce `dist\Apipos-Setup.exe`
(instalador con accesos directos, inicio automático y desinstalador).

> Descarga Inno Setup: https://jrsoftware.org/isdl.php

### Linux — `./build-linux.sh`

```bash
./build-linux.sh          # pregunta la versión
./build-linux.sh 2.0.1
```

Crea/usa `.venv`, instala dependencias (wxPython desde
`extras.wxpython.org` para tu distro), empaqueta con
[apipos-linux.spec](apipos-linux.spec) y genera
`dist/Apipos-<ver>-linux-<arch>.tar.gz`. Para instalarlo en una caja:

```bash
tar xzf Apipos-2.0.1-linux-x86_64.tar.gz
./Apipos-2.0.1-linux-x86_64/install.sh          # --uninstall para quitarlo
```

`install.sh` ([installer-linux.sh](installer-linux.sh)) instala para el usuario
en `~/.local/share/Apipos`, agrega el lanzador y el inicio automático
(`~/.config/autostart`), y arranca la app. El auto-updater no instala solo en
Linux: abre la página del release.

> El bundle depende de la glibc de la máquina donde se compiló. CI compila en
> Ubuntu 22.04, así que corre en esa versión o más nueva.

### Resumen de archivos de build

| Archivo                  | Plataforma | Salida                                   |
|--------------------------|------------|------------------------------------------|
| `app-meta.env`           | todas      | nombre/versión/publisher (fuente única)  |
| `build-installers.sh`    | cualquiera | dispara los 3 builds en GitHub Actions + release |
| `build-macos.sh`         | macOS      | `dist/Apipos.app` + `Apipos-<ver>-<arch>.dmg` |
| `build-windows.bat`      | Windows    | `dist\Apipos.exe` (+ `Apipos-Setup.exe`) |
| `build-linux.sh`         | Linux      | `dist/Apipos-<ver>-linux-<arch>.tar.gz`  |
| `apipos-macos.spec`      | macOS      | spec de PyInstaller (.app)               |
| `apipos.spec`            | Windows    | spec de PyInstaller (.exe)               |
| `apipos-linux.spec`      | Linux      | spec de PyInstaller (carpeta)            |
| `installer-windows.iss`  | Windows    | script de Inno Setup (instalador)        |
| `installer-linux.sh`     | Linux      | `install.sh` que va dentro del .tar.gz   |

> También puedes invocar PyInstaller manualmente: `pyinstaller apipos-macos.spec`
> o `pyinstaller apipos.spec`.

---

## Notas

- **Puerto:** `50432` (configurable en [src/config.py](src/config.py)).
- **Impresora por defecto:** se guarda en `selected_printer.pkl` dentro de
  `%APPDATA%\Apipos` (Windows) o `~/Apipos` (macOS/Linux).
- **CORS** está habilitado para que el POS web pueda llamar a la API.
- El ícono de la bandeja es `assets/app-icon.png`.
