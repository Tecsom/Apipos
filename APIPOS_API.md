# Apipos — API de impresión (guía de integración)

Apipos es un agente local que expone impresoras térmicas (tickets) y de etiquetas
por HTTP. Corre en la misma máquina que la impresora.

- **Base URL:** `http://127.0.0.1:50432`
- **Formato:** JSON (`Content-Type: application/json`). Sin autenticación. CORS habilitado.
- Los PDF se envían **embebidos en el JSON como base64** (no multipart, no URL).

## Formato de respuesta (todos los endpoints)

```json
{ "status": "success" | "error", "data": <objeto o null>, "message": "texto" }
```

HTTP `200` = éxito, `400` = error de negocio/validación, `500` = error inesperado.
Evalúa siempre el campo `status`, no solo el código HTTP.

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado del servicio (incluye el handshake de versión en `data.client`) |
| GET | `/printers` | Lista los nombres de impresoras instaladas |
| GET | `/printers/selected` | Impresora seleccionada por defecto (o `null`) |
| POST | `/printers/selected` | Fija la impresora por defecto: `{"printer": "NOMBRE"}` |
| POST | `/print` | Imprime un trabajo RAW (ticket ESC/POS o renderizado a PDF) o PDF |
| POST | `/render` | Vista previa: renderiza un ticket RAW a PDF o PNG (base64) **sin imprimir** |
| GET | `/fonts` | Catálogo de fuentes instaladas en la máquina (`?refresh=1` re-escanea) |
| GET/POST | `/print/test` | Imprime el ticket de prueba integrado |
| GET/POST | `/print/test-label` | Imprime la etiqueta de prueba integrada (60×30 mm) |
| POST | `/open-withdrawer` | Abre el cajón de dinero: `{"printer": "NOMBRE"}` (opcional) |

## Reglas generales

1. **Manda siempre `"printer"` explícito.** Si se omite se usa la impresora
   seleccionada, que puede no ser la que esperas. Los nombres exactos vienen de
   `GET /printers` (ej. `"AiYin_AS240_BT"` — respeta guiones bajos).
2. Si la impresora no existe, la respuesta es `400` con
   `message: "Printer 'X' not found."` y `data.available` = lista de impresoras
   válidas. Úsala para corregir el nombre.
3. `message: "No printer selected."` significa que omitiste `"printer"` y no hay
   impresora por defecto configurada.

---

## Versionado y handshake

Apipos y su librería cliente oficial (`@tecsom/apipos-js`) **comparten siempre
el mismo número de versión**: la librería `X.Y.Z` está hecha para Apipos `X.Y.Z`.
Para detectar desfases, servidor y cliente se anuncian su versión por headers
HTTP. El handshake es informativo: **nunca bloquea ni rechaza una petición**.

- **Toda** respuesta HTTP (éxitos, errores `400`/`500` y preflight CORS) trae el
  header `X-Apipos-Version: <versión de Apipos>` (ej. `X-Apipos-Version: 1.0.6`).
- El cliente puede mandar `X-Apipos-Client: <nombre>/<major.minor.patch>`
  (ej. `apipos-js/1.0.6`). Es opcional; si falta, nada cambia. La librería
  oficial lo manda sola y avisa en la consola del navegador si las versiones
  difieren.
- CORS: `Access-Control-Allow-Headers` incluye `Content-Type` y
  `X-Apipos-Client` (el preflight lo acepta) y `Access-Control-Expose-Headers`
  incluye `X-Apipos-Version` (así `fetch` puede leerlo desde el navegador).

`GET /health` reporta la comparación en `data.client`:

```json
{
  "status": "success",
  "data": {
    "status": "ok", "version": "1.0.6", "os": "Darwin", "platform": "darwin",
    "backend": "MacPrinterBackend", "port": 50432,
    "client": {
      "name": "apipos-js", "version": "1.0.5", "server": "1.0.6",
      "status": "client_older",
      "message": "Client apipos-js 1.0.5 is older than Apipos 1.0.6. Update the client library; both must share the same version."
    }
  },
  "message": "Service is running."
}
```

`data.client` es `null` cuando la petición no trae `X-Apipos-Client` (o lo trae
vacío). La comparación es numérica por `major.minor.patch`. Valores de
`client.status` y su `message` exacto:

| `status` | `message` |
|---|---|
| `equal` | `Client and server versions match.` |
| `client_older` | `Client {name} {cv} is older than Apipos {sv}. Update the client library; both must share the same version.` |
| `client_newer` | `Client {name} {cv} is newer than Apipos {sv}. Update Apipos on this machine (tray menu > Buscar actualizaciones); both must share the same version.` |
| `unknown` | `Unrecognized X-Apipos-Client header: '{raw}'. Expected '<name>/<major.minor.patch>'.` |

`{name}`/`{cv}` = nombre y versión del cliente, `{sv}` = versión de Apipos,
`{raw}` = el header tal como llegó. Con `unknown`, `name` y `version` son `null`.

Cuando `status` no es `equal`, Apipos imprime además en su stdout (visible al
correrlo headless con `APIPOS_NO_TRAY=1`) la línea `[apipos] <message>`
**una sola vez por valor distinto del header**, no en cada petición.

---

## Cliente JS oficial

`@tecsom/apipos-js` es el cliente oficial de esta API para el navegador:
TypeScript estricto compilado a módulos ES con tipos (`.d.ts`), sin
dependencias, que envuelve los endpoints de esta guía (`checkHealth`,
`listPrinters`, `listFonts`, `renderTicket` y, por impresora, `print`,
`printPDF`, `openDrawer` y `render`) y tipa los items y `settings` descritos
aquí. Vive en su propio repositorio, `Tecsom/apipos-js`, y su versión es
**siempre** la de Apipos: la librería `X.Y.Z` está hecha para Apipos `X.Y.Z`.

Se instala con la versión del Apipos que corre en las cajas:
`pnpm add -D "github:Tecsom/apipos-js#vX.Y.Z"` o el tarball del release
(`https://github.com/Tecsom/apipos-js/releases/download/vX.Y.Z/tecsom-apipos-js-X.Y.Z.tgz`);
en desarrollo local, `pnpm add -D "file:../apipos-js"`. Un front que sirve
módulos estáticos sin empaquetador (como ranitas-pdv) copia el `dist/` del
paquete a su carpeta pública (`pnpm run sync:apipos-js`) e importa
`.../apipos-js/index.js`. El uso completo está en el README del paquete.

La librería manda `X-Apipos-Client: apipos-js/<versión>` en cada petición y lee
`X-Apipos-Version` de cada respuesta (también de las de error). Si las versiones
difieren, avisa **una sola vez** en la consola del navegador: una vez por página
(por versión distinta de Apipos); con `onVersionMismatch`, una vez por cliente.
Nunca bloquea la impresión. Si
el aviso dice `[apipos-js] Apipos X.Y.Z es más nuevo que la librería apipos-js A.B.C...`,
el front quedó atrás: actualiza la dependencia del front a `vX.Y.Z` y vuelve a
vendorizarla. Si dice `[apipos-js] La librería apipos-js A.B.C es más nueva que Apipos X.Y.Z instalado en esta máquina...`,
la caja quedó atrás: actualiza Apipos en esa máquina (menú de bandeja → "Buscar
actualizaciones"). Si dice que Apipos no reporta su versión (falta el header),
es un Apipos anterior a 1.0.6: actualízalo igual. `checkHealth()` devuelve la
misma comparación en `version` (`{ client, backend, status, message }`) y el
aviso se puede redirigir con la opción `onVersionMismatch`.

---

## Imprimir un PDF — `POST /print` con `type: "PDF"`

```json
{
  "printer": "AiYin_AS240_BT",
  "type": "PDF",
  "data": "<PDF en base64>",
  "settings": {
    "pdf_mode": "driver",
    "label_settings": { "width": 60, "height": 30, "unit": "mm" }
  }
}
```

### Campos

- `data` (requerido): el PDF en base64. Se acepta base64 puro o data URI
  (`"data:application/pdf;base64,..."`).
- `settings.pdf_mode`: **`"driver"` o `"raw"`**.
  - `"driver"`: el driver de la impresora renderiza el PDF (vía el sistema de
    impresión del SO). **Es el modo correcto para impresoras de etiquetas con
    driver instalado (ej. AiYin)** — su firmware ignora los trabajos raw genéricos.
  - `"raw"`: rasteriza el PDF a imagen ESC/POS y lo manda crudo. Para
    tiqueteras térmicas de recibos o impresoras sin driver.
- `settings.label_settings` (para etiquetas): `{ "width", "height", "unit" }`.
  `unit` es `"mm"` (default) o `"inch"`. En modo driver define el tamaño del
  media (ej. `media=Custom.60x30mm`); en modo raw define el ancho de
  rasterización (8 dots/mm ≈ 203 DPI).

### Defaults (si omites `pdf_mode`)

- Con `label_settings` → `"driver"`.
- Sin `label_settings` → `"raw"` (comportamiento de recibo).

### Reglas para etiquetas

- La **página del PDF debe medir lo mismo que la etiqueta** (ej. 60×30 mm =
  170×85 pt). El driver escala al media: un PDF tamaño carta saldría deforme.
- Un PDF de varias páginas imprime **una etiqueta por página**.
- Ejemplo de respuesta exitosa en modo driver:
  `{"status":"success","data":{"strategy":"driver","media":"Custom.60x30mm",...}}`

---

## Imprimir un ticket — `POST /print` con `type: "RAW"`

Construye el ticket como una lista de items en `content`; el corte de papel se
agrega automáticamente al final.

```json
{
  "printer": "POS80_Kinwodon",
  "type": "RAW",
  "settings": { "paper_size": 80 },
  "content": [
    { "type": "image", "data": "<PNG/JPG en base64>", "width": 250 },
    { "type": "text", "data": "MI TIENDA S.A.", "align": "center", "font_size": "md", "font_weight": "bold" },
    { "type": "text", "data": "Av. Principal 123", "align": "center" },
    { "type": "text", "data": "RFC ABC010101XYZ  Términos y condiciones...", "align": "center", "font": "b" },
    { "type": "separator" },
    { "type": "table", "data": { "rows": [
        [2, "Coca Cola 600ml", "$18.00", "$36.00"],
        [1, "Pan Bimbo", "$45.50", "$45.50"]
    ]}},
    { "type": "separator" },
    { "type": "text", "data": "PEDIDO #42", "align": "center", "high_contrast": true },
    { "type": "special_text", "data": { "text1": "TOTAL", "text2": "$81.50" }, "font_size": "md", "font_weight": "bold", "high_contrast": true },
    { "type": "special_text", "data": { "text1": "Folio", "text2": "000123" }, "font": "b" },
    { "type": "text", "data": "¡Gracias por su compra!", "align": "center" },
    { "type": "open_withdrawer" }
  ]
}
```

### Items de `content`

| `type` | Campos | Notas |
|---|---|---|
| `text` | `data` (string), `align`: `left`\|`center`\|`right`, `font_size`: `normal`\|`md`\|`lg`, `font_weight`: `normal`\|`bold` (opcional, default `normal`), `font`: `a`\|`b`\|`c` (opcional, default `a`), `high_contrast`: bool (opcional, default `false`) | `md` = doble tamaño, `lg` = triple. `font_weight: "bold"` imprime en negrita. `font` elige la tipografía interna de la impresora y recalcula las columnas del renglón (ver "Fuentes soportadas"). `high_contrast: true` imprime el texto en alto contraste (fondo negro / texto blanco) con un margen de 1 espacio; el relleno de alineación queda fuera del bloque. Las cuatro opciones son combinables |
| `special_text` | `data: {"text1", "text2"}`, `font_size`: `normal`\|`md`\|`lg`, `font_weight`: `normal`\|`bold` (opcional, default `normal`), `font`: `a`\|`b`\|`c` (opcional, default `a`), `high_contrast`: bool (opcional, default `false`) | text1 a la izquierda, text2 a la derecha (para TOTAL, CAMBIO, etc.). `font_size`, `font_weight` y `font` aplican al renglón completo. `md` = doble tamaño, `lg` = triple. `high_contrast: true` invierte la línea completa (fondo negro / texto blanco). Las opciones son combinables |
| `table` | `data: {"rows": [[cant, producto, precio, importe], ...]}` | Imprime encabezado Cant./Producto/Precio/Importe |
| `separator` | — | Línea de guiones |
| `image` | `data` (imagen base64), `width` opcional (dots) | Se convierte a B/N, conserva la proporcion y se centra. Default: 384 dots. `width_dots` es un alias |
| `spacer` | `lines`: entero ≥ 1 (opcional, default `1`), `height_mm`: número (opcional) | Espacio vertical en blanco. En ESC/POS imprime `lines` saltos de línea (tope **50**); si no viene `lines`, `height_mm` se convierte a ~4 mm por línea (`round(height_mm / 4)`, mínimo 1, tope 50); valores inválidos → 1 línea, sin error. Con `renderer: "pdf"`, `height_mm` tiene prioridad (0–200 mm) y si no, `lines` × la altura de línea base |
| `html` | `data`: fragmento HTML (string) | **Solo con `settings.renderer: "pdf"`** (ver "Renderizar el ticket a PDF en Apipos"); el camino ESC/POS lo ignora en silencio. `<img>` **no está soportado** dentro de `html`: usa un item `image` |
| `open_withdrawer` | — | Abre el cajón al final del ticket |

Los items con un `type` desconocido se ignoran sin error.

### Fuentes soportadas (`font`)

`font` elige la tipografía interna de la impresora (comando `ESC M`). Cada
tipografía tiene un ancho distinto por carácter, así que el número de columnas
del renglón se recalcula automáticamente (el relleno de alineación, el bloque de
`high_contrast` y el formato de `special_text` usan ese ancho).

| `font` | Comando | Tamaño estándar (dots/carácter) | Columnas en 80 mm / 58 mm | Soporte de firmware |
|---|---|---|---|---|
| `"a"` | `ESC M 0` | 12×24 | 48 / 32 | Universal (es el default de fábrica) |
| `"b"` | `ESC M 1` | 9×17 | 64 / 42 | Mayoría de térmicas Epson-compatibles; se ve más pequeña y ligera |
| `"c"` | `ESC M 2` | 8×16 | 72 / 48 | **Limitado**: solo algunos modelos Epson y clones recientes; muchos firmwares la ignoran (el texto sale en la fuente activa) |

El valor se normaliza sin distinguir mayúsculas ni espacios (`"B"` y `" b "`
equivalen a `"b"`); un valor no reconocido usa la Fuente A en silencio.

> **Caveats de firmware.** En firmwares no estándar el ancho en dots de las
> fuentes B y C puede variar (la alineación de esos renglones queda levemente
> desviada) o el comando puede ignorarse por completo (el texto sale en la
> fuente activa). Es una degradación aceptable, no un error del API.

### `settings` (opcional, modo RAW)

- `renderer`: `"escpos"` (default) o `"pdf"`. Con `"pdf"` Apipos maqueta el
  ticket como PDF con fuentes del sistema (ver la subsección siguiente); sin él
  todo funciona exactamente como siempre.
- `paper_size`: `80` (default, 48 columnas) o `58` (32 columnas), en mm.
- `char_width`: columnas explícitas (`48`/`32`); tiene prioridad sobre `paper_size`.
- `max_band_bytes`: bytes por comando de imagen (default `1024`). Las imágenes se
  mandan en bandas `GS v 0` de ese tamaño; si una impresora concreta se descarrila
  con imágenes (saca el raster como letras `ÿ` en vez de dibujarlo), bájalo a `512`.
  Medido en una POS80: 2 304 bytes en un comando fallan, 1 152 imprimen bien.
- `max_image_height_dots`: alto máximo de una imagen en puntos (default `600`, unos
  75 mm). Lo más alto se REDUCE conservando la proporción y se avisa en el log; no
  se rechaza el trabajo.

> Las imágenes se centran rellenando de blanco por la izquierda hasta el ancho
> imprimible, no con `ESC a 1`: ese centrado lo pierden algunas impresoras en
> cuanto la imagen es alta.

### Renderizar el ticket a PDF en Apipos (`settings.renderer: "pdf"`)

Manda el MISMO `content` de un ticket RAW y agrega `settings.renderer: "pdf"`:
Apipos maqueta el ticket como un PDF de **una sola página, del alto exacto del
contenido**, con fuentes del sistema (las de `GET /fonts`) o con las integradas
(`sans-serif`, `serif`, `monospace`, que siempre existen y traen acentos y `ñ`),
y lo imprime por la ruta PDF: `pdf_mode: "raw"` (rasteriza a ESC/POS; para
tiqueteras) o `"driver"` (el driver del SO lo imprime; para etiqueteras con
driver). Así obtienes tipografías proporcionales, tamaños en puntos, cursiva,
subrayado, columnas de tabla a medida y separadores con estilo.

Sin `renderer` (o con `"escpos"`) el ticket sigue el camino ESC/POS de siempre y
produce exactamente los mismos bytes, aunque el payload traiga los campos de
esta sección (se ignoran en silencio). Para ver el resultado sin imprimir usa
`POST /render` (siguiente sección).

```json
{
  "printer": "POS80_Kinwodon",
  "type": "RAW",
  "settings": {
    "paper_size": 80,
    "renderer": "pdf",
    "pdf_mode": "raw",
    "font": { "family": "Arial", "size": 9, "line_height": 1.25 },
    "margins_mm": { "top": 1, "right": 1, "bottom": 3, "left": 1 },
    "max_height_mm": 1000,
    "cut": true
  },
  "content": [
    { "type": "image", "data": "<PNG base64>", "width_mm": 30, "align": "center" },
    { "type": "text", "data": "MI TIENDA S.A.", "align": "center", "font_size": 18, "font_weight": "bold" },
    { "type": "text", "data": "Av. Principal 123, Col. Centro", "align": "center", "font_size": "normal" },
    { "type": "text", "data": "PEDIDO #42", "align": "center", "high_contrast": true },
    { "type": "separator", "style": "dashed" },
    { "type": "table", "data": {
        "columns": [
          { "label": "Cant.", "width": 15, "align": "left" },
          { "label": "Producto", "width": 45, "align": "left" },
          { "label": "Precio", "width": 20, "align": "right" },
          { "label": "Importe", "width": 20, "align": "right" }
        ],
        "rows": [[2, "Coca Cola 600ml", "$18.00", "$36.00"], [1, "Pan Bimbo", "$45.50", "$45.50"]]
    }},
    { "type": "separator", "style": "solid" },
    { "type": "special_text", "data": { "text1": "TOTAL", "text2": "$81.50" }, "font_size": 12, "font_weight": "bold" },
    { "type": "special_text", "data": { "text1": "Folio", "text2": "000123" }, "font_family": "Courier New" },
    { "type": "text", "data": "Términos y condiciones en www.mitienda.mx", "font_size": 7, "font_style": "italic", "underline": true },
    { "type": "spacer", "lines": 1 },
    { "type": "html", "data": "<p style=\"text-align:center\">Gracias por su <b>compra</b></p>" },
    { "type": "open_withdrawer" }
  ]
}
```

#### `settings` del renderizador PDF (todos opcionales)

| Clave | Tipo / valores | Default | Notas |
|---|---|---|---|
| `renderer` | `"escpos"` \| `"pdf"` | `"escpos"` | Se normaliza (sin espacios ni mayúsculas: `" PDF "` = `"pdf"`). Otro valor → error `Unsupported renderer 'X'. Use 'escpos' or 'pdf'.` |
| `pdf_mode` | `"raw"` \| `"driver"` (alias `raster` / `document`) | `"driver"` si hay `label_settings`, si no `"raw"` | Misma regla y mismo texto de error que los trabajos PDF |
| `font` | objeto `{ "family", "size", "line_height" }` | `{ "family": "sans-serif", "size": 9, "line_height": 1.25 }` | Fuente base del ticket. `family`: una familia de `GET /fonts` o de `builtin`. `size` en puntos, número entre 4 y 72 (si no: error `'font.size' must be a number between 4 and 72.`). `line_height`: multiplicador 0.8–3.0 (fuera de rango → 1.25 en silencio) |
| `margins_mm` | objeto `{ "top", "right", "bottom", "left" }` | `{ "top": 1, "right": 1, "bottom": 3, "left": 1 }` | Claves faltantes toman su default; valores no numéricos o negativos → default en silencio |
| `width_mm` | número | ver "Ancho de página" | Ancho de la página en mm |
| `max_height_mm` | número | `1000` | Si el ticket renderizado lo excede → error `Rendered ticket is too tall ({h} mm > {max} mm).` (`h` con 1 decimal). Un valor no numérico o ≤ 0 usa el default |
| `cut`, `width_dots`, `label_settings`, `max_image_height_dots` | como hoy | como hoy | Mismo significado que en los trabajos PDF / RAW |

#### Ancho de página

Se usa la primera regla que aplique (un valor no numérico o ≤ 0 no aplica y pasa
a la siguiente; un `label_settings` inválido da su error de siempre):

1. `settings.width_mm`
2. `label_settings.width` (convertido a mm según su `unit`)
3. `settings.width_dots / 8`
4. `paper_size`: `>= 80` → 72 mm; si no, 48 mm
5. `char_width`: `>= 48` → 72 mm; si no, 48 mm
6. 72 mm

72 mm = los 576 dots imprimibles del papel de 80 mm; 48 mm = los 384 dots del de
58 mm. Los márgenes se restan de ese ancho.

Cómo llega el PDF a la impresora:

- **`raw`**: se rasteriza al ancho de la página × 8 dots (ej. 72 mm → 576);
  `settings.width_dots` lo sobrescribe y, con `label_settings`, manda el ancho de
  la etiqueta × 8. El corte sigue la regla de los PDF: `cut` explícito; si se
  omite, corta en recibos y no en etiquetas.
- **`driver`**: el media es el tamaño exacto de la página renderizada
  (ej. `Custom.72x123.4mm`); el corte lo decide el driver.

#### Campos por item

"pdf" = los honra el renderizador PDF; "escpos" = los honra el camino ESC/POS
(el de siempre). **Un campo que un camino no honra se ignora en silencio** (sin
error ni aviso), así que el mismo `content` sirve para ambos.

| Item | Campo | Valores | pdf | escpos |
|---|---|---|---|---|
| `text`, `special_text`, `table` | `font_family` | string (nombre de familia de `GET /fonts` o de `builtin`) | sí | no |
| `text`, `special_text` | `font_size` | `"normal"` \| `"md"` \| `"lg"` **o número en pt** | keyword = tamaño base ×1 / ×2 / ×3; número = pt (se acota a 4–72) | keyword como hoy; **número → `normal`** |
| `text`, `special_text` | `font_weight` | `normal` \| `bold` | sí (si la familia no tiene cara bold, negrita sintética + aviso) | sí (como hoy) |
| `text`, `special_text`, `table` | `font_style` | `normal` \| `italic` | sí | no |
| `text`, `special_text` | `underline` | bool | sí | no |
| `text`, `special_text`, `table` | `line_height` | número (multiplicador, 0.8–3.0) | sí (sobrescribe el de `settings.font`) | no |
| `text` | `align` | `left` \| `center` \| `right` | sí | sí |
| `text`, `special_text` | `high_contrast` | bool | sí: bloque de ANCHO COMPLETO negro con texto blanco | sí (como hoy) |
| `text`, `special_text` | `font` | `a` \| `b` \| `c` | no | sí (como hoy) |
| `table` | `data.columns` | lista de `{ "label", "width" (porcentaje), "align" }` | sí; default = las 4 columnas clásicas `Cant./Producto/Precio/Importe` con `15/45/20/20` y `left/left/right/right`. Si los `width` no suman 100 se escalan; los faltantes se reparten el resto | no (siempre las 4 clásicas) |
| `table` | `data.rows` | lista de listas | sí (celdas → texto; celdas faltantes vacías; sobrantes ignoradas) | sí (como hoy) |
| `separator` | `style` | `dashed` (default) \| `solid` \| `dotted` \| `double` | sí (valor desconocido → `dashed`) | no |
| `separator` | `thickness` | número en pt | sí (default `0.6`, se acota a 0.2–3) | no |
| `image` | `width` / `width_dots` | dots | sí (`dots / 8` mm; default 384 dots; nunca más ancha que el área imprimible) | sí (como hoy) |
| `image` | `width_mm` | mm | sí (prioridad sobre `width`) | no |
| `image` | `align` | `left` \| `center` \| `right` | sí (default `center`) | no (siempre centrada) |
| `spacer` | `lines` | entero ≥ 1 (default `1`) | sí (`lines` × altura de línea base = `font.size` × `font.line_height`) | sí (`lines` saltos de línea, tope 50) |
| `spacer` | `height_mm` | número | sí (prioridad sobre `lines`; se acota a 0–200 mm) | solo si falta `lines`: `lines = max(1, round(height_mm / 4))`, tope 50 |
| `html` | `data` | fragmento HTML (string) | sí (ver "Bloque `html`") | no (ignorado) |
| `open_withdrawer` | — | — | sí: tras imprimir el PDF se manda el pulso del cajón como trabajo raw aparte | sí (como hoy) |

Los items con `type` desconocido se ignoran en ambos caminos. El texto de los
items se maqueta tal cual (no pasa por HTML: no hace falta escapar `<` ni `&`);
solo el `data` de `html` se interpreta como HTML. En `table`, el encabezado sale
siempre en negrita y las filas en la cara normal (`font_weight` no aplica); si
todas las `label` están vacías no se dibuja encabezado.

#### Fuentes

Cada `font_family` (o `settings.font.family` si el item no trae una) se resuelve así:

1. `sans-serif`, `serif`, `monospace` → fuentes integradas (Helvetica, Times y
   Courier equivalentes), en cualquier combinación de negrita/cursiva.
2. Familia instalada (sin distinguir mayúsculas) → esa familia, incluidas las
   caras de archivos `.ttc`/`.otc`. Si falta la cara pedida se usa la más
   cercana y se agrega un aviso (ej. `Font family 'Verdana' has no italic face;
   using Regular.`); si falta la negrita, además se simula (negrita sintética).
3. `Arial`, `Helvetica`, `Times`, `Times New Roman`, `Courier` y `Courier New`
   no instaladas → la integrada equivalente, sin aviso.
4. Cualquier otra no instalada → `sans-serif` y el aviso
   `Font family 'X' is not installed; using sans-serif.`

El PDF incrusta solo los glifos usados de cada fuente (subconjunto), así que un
ticket típico pesa decenas de KB aunque use fuentes del sistema.

#### Bloque `html`

El `data` de un item `html` se maqueta con el motor HTML/CSS de MuPDF al ancho
disponible y con la fuente base de `settings.font` (familia, tamaño e
interlineado). Funcionan `<b>`, `<i>`, `<u>`, `<br>`, `<hr>`, `font-size`,
`text-align`, `line-height`, `margin`, `padding`, `border` en bloques y
`white-space: pre`. En `font-family` puedes usar las genéricas (`sans-serif`,
`serif`, `monospace`) y las familias de sistema que ya usaron items anteriores
del mismo ticket.

Limitaciones: **`<img>` no está soportado** (usa un item `image`); las tablas
HTML no se estiran al 100 % (usa el item `table`); `background-color` solo se
pinta en bloques (`<p>`, `<td>`), no en `<span>`; no funcionan `letter-spacing`,
`float` ni `display: inline-block`. Si el bloque no se puede renderizar se
omite, el ticket se imprime igual y queda un aviso en `warnings`.

#### Respuesta

Modo `raw`:

```json
{
  "status": "success",
  "data": {
    "printer": "POS80_Kinwodon", "type": "RAW", "renderer": "pdf",
    "strategy": "raw", "width_dots": 576, "cut": true,
    "page_mm": { "width": 72, "height": 123.4 },
    "fonts": [
      { "family": "Arial", "resolved": "Arial Bold", "source": "system", "bold": true, "italic": false },
      { "family": "Courier New", "resolved": "Courier New", "source": "system", "bold": false, "italic": false }
    ],
    "warnings": ["Font family 'Comic Sans' is not installed; using sans-serif."],
    "drawer_opened": true
  },
  "message": "Rendered ticket sent as PDF."
}
```

Modo `driver`: igual, pero con `"strategy": "driver"` y
`"media": "Custom.72x123.4mm"` en lugar de `width_dots` y `cut`.

- `page_mm`: tamaño de la página renderizada (alto = el del contenido).
- `fonts`: cada fuente pedida, con lo que se usó realmente (`resolved`) y su
  origen `source`: `system` (instalada), `builtin` (integrada) o `fallback`
  (no instalada → `sans-serif`).
- `warnings`: avisos que no impiden imprimir. Textos posibles:
  `Font family 'X' is not installed; using sans-serif.`,
  `Font family 'X' has no italic face; using Regular.` (o `bold` / `bold italic`),
  `Image in item N scaled down to fit M dots.` (imagen más alta que
  `max_image_height_dots`, default 600), `HTML block in item N could not be
  rendered: ...` y `Font subsetting skipped: ...`. `N` es el índice (desde 0)
  del item en `content`.
- `drawer_opened`: `true` si el ticket traía `open_withdrawer` y se mandó el pulso.

La impresora se valida **antes** de renderizar (`Printer 'X' not found.` como
siempre).

> **`open_withdrawer` con `renderer: "pdf"`.** Un PDF no puede llevar comandos
> ESC/POS, así que el pulso del cajón se manda como un **segundo trabajo raw** a
> la misma impresora, justo después de imprimir el ticket. En modo `driver` con
> etiqueteras (ej. AiYin) ese trabajo raw puede ignorarse —su firmware ignora
> los trabajos raw genéricos—; es esperado y no es un error: el cajón se usa con
> tiqueteras.

---

## Vista previa — `POST /render`

Renderiza un ticket RAW con el renderizador PDF y devuelve el resultado en
base64 **sin imprimir**: no valida impresora ni toca ninguna. Sirve para mostrar
una vista previa en el front o probar un ticket sin hardware.

Body: el mismo de `POST /print` (`settings` y `content`; también se acepta la
lista legacy de items) más los campos de abajo. `printer` y `type` se ignoran, y
siempre se usa el renderizador PDF (no hace falta `settings.renderer`;
`pdf_mode`, `cut` y `open_withdrawer` no tienen efecto aquí).

| Campo | Valores | Default |
|---|---|---|
| `format` | `"pdf"` \| `"png"` | `"pdf"` |
| `dpi` | entero 72–600 (solo con `png`) | `203` |

```json
{
  "format": "png",
  "dpi": 203,
  "settings": { "paper_size": 80, "font": { "family": "sans-serif", "size": 9 } },
  "content": [
    { "type": "text", "data": "HOLA", "align": "center", "font_size": "lg" },
    { "type": "special_text", "data": { "text1": "TOTAL", "text2": "$1.00" } }
  ]
}
```

Respuesta:

```json
{
  "status": "success",
  "data": {
    "format": "png", "dpi": 203, "base64": "iVBORw0KGgo...",
    "page_mm": { "width": 72, "height": 19.9 }, "pages": 1,
    "fonts": [ { "family": "sans-serif", "resolved": "Helvetica", "source": "builtin", "bold": false, "italic": false } ],
    "warnings": []
  },
  "message": "Ticket rendered."
}
```

- Con `format: "pdf"` el `base64` es el PDF (empieza con `JVBERi`) y `dpi` vale
  `null` (el `dpi` del body se ignora). Con `png` es la imagen de la página
  (empieza con `iVBORw0KGgo`); a 203 dpi un ticket de 72 mm mide 576 px de ancho.
- `dpi` acepta un entero (`203`, `203.0` o `"203"`); solo se valida con `png`.
- Errores: `format` inválido → `Unsupported format 'X'. Use 'pdf' or 'png'.`;
  `dpi` fuera de rango o no entero → `'dpi' must be an integer between 72 and 600.`;
  sin `content` → `No content to print.`; el resto (`font.size`, ticket
  demasiado alto, imagen inválida, `label_settings` inválido), con los mismos
  textos que en `POST /print`.

---

## Fuentes del sistema — `GET /fonts`

Lista las familias de fuentes instaladas en la máquina (con sus estilos) para
elegir `settings.font.family` / `font_family` del renderizador PDF.

```
GET /fonts              → usa el catálogo en memoria (el primer acceso escanea)
GET /fonts?refresh=1    → vuelve a escanear (ej. tras instalar una fuente)
```

```json
{
  "status": "success",
  "data": {
    "families": [
      {
        "family": "Arial",
        "monospace": false,
        "faces": [
          { "style": "Regular", "bold": false, "italic": false, "weight": 400,
            "full_name": "Arial", "postscript_name": "ArialMT",
            "path": "/System/Library/Fonts/Supplemental/Arial.ttf", "index": 0, "format": "ttf" },
          { "style": "Bold", "bold": true, "italic": false, "weight": 700, "...": "..." }
        ]
      }
    ],
    "count": 380,
    "builtin": ["sans-serif", "serif", "monospace"],
    "dirs": ["/System/Library/Fonts", "/Library/Fonts", "/Users/x/Library/Fonts"],
    "scanned_at": "2026-10-26T18:04:11"
  },
  "message": "Fonts listed."
}
```

- `families` viene ordenada por `family` sin distinguir mayúsculas; `faces`, por
  (`weight`, `italic`). Usa el valor de `family` tal cual (las mayúsculas no
  importan) en `settings.font.family` o `font_family`.
- `count` = número de familias. `monospace` es `true` si todas las caras de la
  familia son de ancho fijo.
- Cada cara: `style`, `bold`, `italic`, `weight` (peso OpenType: 400 = normal,
  700 = negrita; `bold` es `true` desde 600), `full_name`,
  `postscript_name`, `path`, `index` (posición de la cara dentro de un `.ttc`/`.otc`;
  `0` en archivos de una sola cara) y `format` (`ttf` \| `otf` \| `ttc` \| `otc`).
- `builtin`: familias genéricas que el renderizador acepta **siempre**, aunque
  la máquina no tenga ninguna fuente instalada.
- `dirs`: directorios escaneados que existen en esta máquina. Windows:
  `%WINDIR%\Fonts` y `%LOCALAPPDATA%\Microsoft\Windows\Fonts`; macOS:
  `/System/Library/Fonts`, `/Library/Fonts` y `~/Library/Fonts`.
- `scanned_at`: fecha y hora local del último escaneo (ISO 8601).
- `refresh` acepta `1`, `true`, `yes`, `on` o `si`. Las fuentes que no se
  pueden leer se omiten sin error.

---

## Pruebas rápidas

```
GET /print/test?printer=POS80_Kinwodon            → ticket de prueba
GET /print/test-label?printer=AiYin_AS240_BT      → etiqueta de prueba 60×30 mm (modo driver)
GET /print/test-label?printer=X&mode=raw&width=50&height=25&unit=mm
```

## Errores comunes

| `message` | Causa | Corrección |
|---|---|---|
| `Printer 'X' not found.` | Nombre mal escrito | Usa un nombre de `data.available` |
| `No printer selected.` | Sin `printer` y sin default | Manda `"printer"` explícito |
| `Invalid base64 PDF data.` / `Provided data is not a valid PDF.` | `data` corrupto o no es PDF | Verifica la codificación base64 |
| `Unsupported pdf_mode 'X'. Use 'driver' or 'raw'.` | Modo inválido | Solo `driver` o `raw` |
| `Unsupported unit 'X'. Use 'mm' or 'inch'.` | Unidad inválida | Solo `mm` o `inch` |
| `label_settings requires a numeric 'width'.` | Falta ancho | Incluye `width` numérico |
| `No content to print.` | `content` vacío o ausente (en `/print` RAW o en `/render`) | Manda al menos un item |
| `Unsupported renderer 'X'. Use 'escpos' or 'pdf'.` | `settings.renderer` inválido | Solo `escpos` o `pdf` |
| `'font.size' must be a number between 4 and 72.` | `settings.font.size` no numérico o fuera de rango (renderizador PDF) | Número de puntos entre 4 y 72 |
| `Rendered ticket is too tall ({h} mm > {max} mm).` | El ticket renderizado mide más que `settings.max_height_mm` (default 1000) | Recorta el contenido o sube `max_height_mm` |
| `Invalid image data in item {n}.` | Imagen ilegible en el item `n` (índice desde 0 en `content`); solo renderizador PDF y `/render` | Verifica el base64 (PNG/JPG). En ESC/POS el mismo caso da `Error converting image to black and white.` |
| `Unsupported format 'X'. Use 'pdf' or 'png'.` | `format` inválido en `POST /render` | Solo `pdf` o `png` |
| `'dpi' must be an integer between 72 and 600.` | `dpi` inválido en `POST /render` (con `format: "png"`) | Entero entre 72 y 600 |
| `Unrecognized X-Apipos-Client header: '{raw}'. Expected '<name>/<major.minor.patch>'.` | **No es un error HTTP**: solo aparece en `GET /health` → `data.client.message` cuando el header `X-Apipos-Client` tiene otro formato | Manda `<nombre>/<major.minor.patch>`, ej. `apipos-js/1.0.6` |
| No imprime pero responde `success` | Etiquetera con job raw genérico | Usa `pdf_mode: "driver"` |
