---
title: Renderizador PDF
---

# Renderizar el ticket a PDF en Apipos (`settings.renderer: "pdf"`)

Manda el MISMO `content` de un [ticket RAW](./ticket-raw) y agrega
`settings.renderer: "pdf"`: Apipos maqueta el ticket como un PDF de **una sola
página, del alto exacto del contenido**, con fuentes del sistema (las de
[`GET /fonts`](./vista-previa-y-fuentes#fuentes-del-sistema)) o con las integradas
(`sans-serif`, `serif`, `monospace`, que siempre existen y traen acentos y `ñ`),
y lo imprime por la ruta PDF: `pdf_mode: "raw"` (rasteriza a ESC/POS; para
tiqueteras) o `"driver"` (el driver del SO lo imprime; para etiqueteras con
driver). Así obtienes tipografías proporcionales, tamaños en puntos, cursiva,
subrayado, columnas de tabla a medida y separadores con estilo.

Sin `renderer` (o con `"escpos"`) el ticket sigue el camino ESC/POS de siempre y
produce exactamente los mismos bytes, aunque el payload traiga los campos de
esta sección (se ignoran en silencio). Para ver el resultado sin imprimir usa
[`POST /render`](./vista-previa-y-fuentes#vista-previa).

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

Guarda el JSON como `ticket-pdf.json` (sustituye `"<PNG base64>"` por tu logo en
base64) y envíalo:

```bash
curl -s -X POST http://localhost:50432/print \
  -H 'Content-Type: application/json' \
  -d @ticket-pdf.json
```

## `settings` del renderizador PDF (todos opcionales) {#settings}

| Clave | Tipo / valores | Default | Notas |
|---|---|---|---|
| `renderer` | `"escpos"` \| `"pdf"` | `"escpos"` | Se normaliza (sin espacios ni mayúsculas: `" PDF "` = `"pdf"`). Otro valor → error `Unsupported renderer 'X'. Use 'escpos' or 'pdf'.` |
| `pdf_mode` | `"raw"` \| `"driver"` (alias `raster` / `document`) | `"driver"` si hay `label_settings`, si no `"raw"` | Misma regla y mismo texto de error que los [trabajos PDF](./pdf-y-etiquetas) |
| `font` | objeto `{ "family", "size", "line_height" }` | `{ "family": "sans-serif", "size": 9, "line_height": 1.25 }` | Fuente base del ticket. `family`: una familia de `GET /fonts` o de `builtin`. `size` en puntos, número entre 4 y 72 (si no: error `'font.size' must be a number between 4 and 72.`). `line_height`: multiplicador 0.8–3.0 (fuera de rango → 1.25 en silencio) |
| `margins_mm` | objeto `{ "top", "right", "bottom", "left" }` | `{ "top": 1, "right": 1, "bottom": 3, "left": 1 }` | Claves faltantes toman su default; valores no numéricos o negativos → default en silencio |
| `width_mm` | número | ver [Ancho de página](#ancho-de-pagina) | Ancho de la página en mm |
| `max_height_mm` | número | `1000` | Si el ticket renderizado lo excede → error `Rendered ticket is too tall ({h} mm > {max} mm).` (`h` con 1 decimal). Un valor no numérico o ≤ 0 usa el default |
| `cut`, `width_dots`, `label_settings`, `max_image_height_dots` | como hoy | como hoy | Mismo significado que en los trabajos [PDF](./pdf-y-etiquetas) / [RAW](./ticket-raw#settings) |

## Ancho de página {#ancho-de-pagina}

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

## Campos por item {#campos-por-item}

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
| `html` | `data` | fragmento HTML (string) | sí (ver [Bloque `html`](#bloque-html)) | no (ignorado) |
| `open_withdrawer` | — | — | sí: tras imprimir el PDF se manda el pulso del cajón como trabajo raw aparte | sí (como hoy) |

Los items con `type` desconocido se ignoran en ambos caminos. El texto de los
items se maqueta tal cual (no pasa por HTML: no hace falta escapar `<` ni `&`);
solo el `data` de `html` se interpreta como HTML. En `table`, el encabezado sale
siempre en negrita y las filas en la cara normal (`font_weight` no aplica); si
todas las `label` están vacías no se dibuja encabezado.

## Fuentes {#fuentes}

Cada `font_family` (o `settings.font.family` si el item no trae una) se resuelve así:

1. `sans-serif`, `serif`, `monospace` → fuentes integradas (Helvetica, Times y
   Courier equivalentes), en cualquier combinación de negrita/cursiva.
2. Familia instalada (sin distinguir mayúsculas) → esa familia, incluidas las
   caras de archivos `.ttc`/`.otc`. Si falta la cara pedida se usa la más
   cercana y se agrega un aviso (ej. `Font family 'Verdana' has no italic face; using Regular.`);
   si falta la negrita, además se simula (negrita sintética).
3. `Arial`, `Helvetica`, `Times`, `Times New Roman`, `Courier` y `Courier New`
   no instaladas → la integrada equivalente, sin aviso.
4. Cualquier otra no instalada → `sans-serif` y el aviso
   `Font family 'X' is not installed; using sans-serif.`

El PDF incrusta solo los glifos usados de cada fuente (subconjunto), así que un
ticket típico pesa decenas de KB aunque use fuentes del sistema.

Las familias instaladas en la máquina se consultan con
[`GET /fonts`](./vista-previa-y-fuentes#fuentes-del-sistema).

## Bloque `html` {#bloque-html}

El `data` de un item `html` se maqueta con el motor HTML/CSS de MuPDF al ancho
disponible y con la fuente base de `settings.font` (familia, tamaño e
interlineado). Funcionan `<b>`, `<i>`, `<u>`, `<br>`, `<hr>`, `font-size`,
`text-align`, `line-height`, `margin`, `padding`, `border` en bloques y
`white-space: pre`. En `font-family` puedes usar las genéricas (`sans-serif`,
`serif`, `monospace`) y las familias de sistema que ya usaron items anteriores
del mismo ticket.

::: warning Limitaciones
**`<img>` no está soportado** (usa un item `image`); las tablas HTML no se
estiran al 100 % (usa el item `table`); `background-color` solo se pinta en
bloques (`<p>`, `<td>`), no en `<span>`; no funcionan `letter-spacing`, `float`
ni `display: inline-block`. Si el bloque no se puede renderizar se omite, el
ticket se imprime igual y queda un aviso en `warnings`.
:::

## Respuesta {#respuesta}

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
  - `Font family 'X' is not installed; using sans-serif.`
  - `Font family 'X' has no italic face; using Regular.` (o `bold` / `bold italic`)
  - `Image in item N scaled down to fit M dots.` (imagen más alta que
    `max_image_height_dots`, default 600)
  - `HTML block in item N could not be rendered: ...`
  - `Font subsetting skipped: ...`

  `N` es el índice (desde 0) del item en `content`.
- `drawer_opened`: `true` si el ticket traía `open_withdrawer` y se mandó el pulso.

La impresora se valida **antes** de renderizar (`Printer 'X' not found.` como
siempre).

::: warning `open_withdrawer` con `renderer: "pdf"`
Un PDF no puede llevar comandos ESC/POS, así que el pulso del cajón se manda como
un **segundo trabajo raw** a la misma impresora, justo después de imprimir el
ticket. En modo `driver` con etiqueteras (ej. AiYin) ese trabajo raw puede
ignorarse —su firmware ignora los trabajos raw genéricos—; es esperado y no es un
error: el cajón se usa con tiqueteras.
:::

Los errores del renderizador (`Unsupported renderer 'X'. Use 'escpos' or 'pdf'.`,
`'font.size' must be a number between 4 and 72.`, `Rendered ticket is too tall ({h} mm > {max} mm).`,
`Invalid image data in item {n}.`) están reunidos en [Errores comunes](./errores-comunes).
