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
| `requirements.txt`          | común      | Flask, Flask-Cors, Pillow, wxPython, **PyMuPDF** |
| `requirements-windows.txt`  | Windows    | + `pywin32`                                      |
| `requirements-macos.txt`    | macOS/Linux| nada extra (usa CUPS del sistema)                |

> `PyMuPDF` es común a ambos SO porque se usa para **rasterizar PDFs** (PDF →
> imagen → ESC/POS), necesario para impresoras térmicas.
>
> En macOS/Linux la impresión de bajo nivel usa CUPS (`lp` / `lpstat`), que viene
> con el sistema. (Opcionalmente, si `python-escpos` está instalado, el backend
> usa su wrapper `Lp`.)

---

## Crear instalador según el SO

Hay **scripts de build** que automatizan todo (crear venv, instalar
dependencias, empaquetar). Cada build debe hacerse **en su propio sistema
operativo** (PyInstaller no hace cross-compilation entre Windows y macOS).

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

### Resumen de archivos de build

| Archivo                  | Plataforma | Salida                                   |
|--------------------------|------------|------------------------------------------|
| `app-meta.env`           | ambos      | nombre/versión/publisher (fuente única)  |
| `build-macos.sh`         | macOS      | `dist/Apipos.app` + `Apipos-<ver>-<arch>.dmg` |
| `build-windows.bat`      | Windows    | `dist\Apipos.exe` (+ `Apipos-Setup.exe`) |
| `apipos-macos.spec`      | macOS      | spec de PyInstaller (.app)               |
| `apipos.spec`            | Windows    | spec de PyInstaller (.exe)               |
| `installer-windows.iss`  | Windows    | script de Inno Setup (instalador)        |

> También puedes invocar PyInstaller manualmente: `pyinstaller apipos-macos.spec`
> o `pyinstaller apipos.spec`.

---

## Notas

- **Puerto:** `50432` (configurable en [src/config.py](src/config.py)).
- **Impresora por defecto:** se guarda en `selected_printer.pkl` dentro de
  `%APPDATA%\Apipos` (Windows) o `~/Apipos` (macOS/Linux).
- **CORS** está habilitado para que el POS web pueda llamar a la API.
- El ícono de la bandeja es `assets/app-icon.png`.
