---
title: Ticket RAW
---

# Ticket RAW — `POST /print` con `type: "RAW"`

Construye el ticket como una lista de items en `content`; el corte de papel se
agrega automáticamente al final. Por defecto Apipos lo convierte a comandos
ESC/POS; con `settings.renderer: "pdf"` lo maqueta como PDF (ver
[Renderizador PDF](./renderer-pdf)).

```json
{
  "printer": "POS80_Kinwodon",
  "type": "RAW",
  "settings": { "paper_size": 80 },
  "content": [
    { "type": "image", "data": "<PNG/JPG en base64>", "width": 250 },
    { "type": "text", "data": "MI TIENDA S.A.", "align": "center", "font_size": "md", "font_weight": "bold" },
    { "type": "text", "data": "Av. Principal 123", "align": "center" },
    { "type": "text", "data": "RFC ABC010101XYZ  Términos y condiciones", "align": "center", "font": "b" },
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

Guarda el JSON como `ticket.json` (sustituye `"<PNG/JPG en base64>"` por tu
logo en base64) y envíalo:

```bash
curl -s -X POST http://localhost:50432/print \
  -H 'Content-Type: application/json' \
  -d @ticket.json
```

## Items de `content` {#items-de-content}

| `type` | Campos | Notas |
|---|---|---|
| `text` | `data` (string), `align`: `left`\|`center`\|`right`, `font_size`: `normal`\|`md`\|`lg`, `font_weight`: `normal`\|`bold` (opcional, default `normal`), `font`: `a`\|`b`\|`c` (opcional, default `a`), `high_contrast`: bool (opcional, default `false`) | `md` = doble tamaño, `lg` = triple. `font_weight: "bold"` imprime en negrita. `font` elige la tipografía interna de la impresora y recalcula las columnas del renglón (ver [Fuentes soportadas](#fuentes-soportadas)). `high_contrast: true` imprime el texto en alto contraste (fondo negro / texto blanco) con un margen de 1 espacio; el relleno de alineación queda fuera del bloque. Las cuatro opciones son combinables |
| `special_text` | `data: {"text1", "text2"}`, `font_size`: `normal`\|`md`\|`lg`, `font_weight`: `normal`\|`bold` (opcional, default `normal`), `font`: `a`\|`b`\|`c` (opcional, default `a`), `high_contrast`: bool (opcional, default `false`) | text1 a la izquierda, text2 a la derecha (para TOTAL, CAMBIO, etc.). `font_size`, `font_weight` y `font` aplican al renglón completo. `md` = doble tamaño, `lg` = triple. `high_contrast: true` invierte la línea completa (fondo negro / texto blanco). Las opciones son combinables |
| `table` | `data: {"rows": [[cant, producto, precio, importe], ...]}` | Imprime encabezado Cant./Producto/Precio/Importe |
| `separator` | — | Línea de guiones |
| `image` | `data` (imagen base64), `width` opcional (dots) | Se convierte a B/N, conserva la proporcion y se centra. Default: 384 dots. `width_dots` es un alias |
| `spacer` | `lines`: entero ≥ 1 (opcional, default `1`), `height_mm`: número (opcional) | Espacio vertical en blanco. En ESC/POS imprime `lines` saltos de línea (tope **50**); si no viene `lines`, `height_mm` se convierte a ~4 mm por línea (`round(height_mm / 4)`, mínimo 1, tope 50); valores inválidos → 1 línea, sin error. Con `renderer: "pdf"`, `height_mm` tiene prioridad (0–200 mm) y si no, `lines` × la altura de línea base |
| `html` | `data`: fragmento HTML (string) | **Solo con `settings.renderer: "pdf"`** (ver [Renderizar el ticket a PDF en Apipos](./renderer-pdf)); el camino ESC/POS lo ignora en silencio. `<img>` **no está soportado** dentro de `html`: usa un item `image` |
| `open_withdrawer` | — | Abre el cajón al final del ticket |

Los items con un `type` desconocido se ignoran sin error.

## Fuentes soportadas (`font`) {#fuentes-soportadas}

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

::: warning Caveats de firmware
En firmwares no estándar el ancho en dots de las fuentes B y C puede variar (la
alineación de esos renglones queda levemente desviada) o el comando puede
ignorarse por completo (el texto sale en la fuente activa). Es una degradación
aceptable, no un error del API.
:::

::: tip
Las fuentes `a`/`b`/`c` son las internas de la impresora (camino ESC/POS). Para
usar fuentes del sistema (Arial, Courier New, etc.) usa el
[Renderizador PDF](./renderer-pdf#fuentes).
:::

## `settings` (opcional, modo RAW) {#settings}

- `renderer`: `"escpos"` (default) o `"pdf"`. Con `"pdf"` Apipos maqueta el
  ticket como PDF con fuentes del sistema (ver [Renderizador PDF](./renderer-pdf));
  sin él todo funciona exactamente como siempre.
- `paper_size`: `80` (default, 48 columnas) o `58` (32 columnas), en mm.
- `char_width`: columnas explícitas (`48`/`32`); tiene prioridad sobre `paper_size`.
- `max_band_bytes`: bytes por comando de imagen (default `1024`). Las imágenes se
  mandan en bandas `GS v 0` de ese tamaño; si una impresora concreta se descarrila
  con imágenes (saca el raster como letras `ÿ` en vez de dibujarlo), bájalo a `512`.
  Medido en una POS80: 2 304 bytes en un comando fallan, 1 152 imprimen bien.
- `max_image_height_dots`: alto máximo de una imagen en puntos (default `600`, unos
  75 mm). Lo más alto se REDUCE conservando la proporción y se avisa en el log; no
  se rechaza el trabajo.

::: info
Las imágenes se centran rellenando de blanco por la izquierda hasta el ancho
imprimible, no con `ESC a 1`: ese centrado lo pierden algunas impresoras en
cuanto la imagen es alta.
:::

Los errores que puede devolver un ticket RAW (`No content to print.`,
`Error converting image to black and white.`, impresora inexistente…) están en
[Errores comunes](./errores-comunes).
