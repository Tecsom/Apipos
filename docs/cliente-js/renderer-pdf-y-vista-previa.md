---
title: Renderizador PDF y vista previa
---

# Renderizador PDF y vista previa

## Imprimir renderizando en Apipos (`renderer: 'pdf'`)

Con `renderer: 'pdf'` Apipos maqueta el MISMO `content` como un PDF de una sola
página (del alto exacto del ticket) con fuentes del sistema o integradas, y lo
imprime por la ruta PDF (`pdfMode: 'raw'` rasteriza a ESC/POS para tiqueteras;
`'driver'` lo entrega al driver del SO). Así hay tipografías proporcionales,
tamaños en puntos, cursiva, subrayado, columnas de tabla a medida, bloques
`html` y separadores con estilo. Sin `renderer` (o con `'escpos'`) el ticket
sale por ESC/POS como siempre y los campos del renderizador PDF se ignoran.

Los campos que cada item acepta con este renderizador están en
[Renderizador PDF](../api/renderer-pdf) de la API HTTP.

```ts
import { Apipos } from '@tecsom/apipos-js';
import type { PrintOptions, TicketContent } from '@tecsom/apipos-js';

const apipos = new Apipos();
const printer = apipos.createPrinter('POS80_Kinwodon', { paper_size: 80 });

const ticket: TicketContent = [
    { type: 'image', data: logoBase64, width_mm: 30, align: 'center' },
    { type: 'text', data: 'MI TIENDA S.A.', align: 'center', font_size: 18, font_weight: 'bold' },
    { type: 'text', data: 'PEDIDO #42', align: 'center', high_contrast: true },
    { type: 'separator', style: 'dashed' },
    {
        type: 'table',
        data: {
            columns: [
                { label: 'Cant.', width: 15, align: 'left' },
                { label: 'Producto', width: 45 },
                { label: 'Precio', width: 20, align: 'right' },
                { label: 'Importe', width: 20, align: 'right' }
            ],
            rows: [
                [2, 'Coca Cola 600ml', '$18.00', '$36.00'],
                [1, 'Pan Bimbo', '$45.50', '$45.50']
            ]
        }
    },
    { type: 'separator', style: 'solid', thickness: 1 },
    { type: 'special_text', data: { text1: 'TOTAL', text2: '$81.50' }, font_size: 12, font_weight: 'bold' },
    { type: 'special_text', data: { text1: 'Folio', text2: '000123' }, font_family: 'Courier New' },
    { type: 'spacer', lines: 1 },
    { type: 'text', data: 'Términos en www.mitienda.mx', font_size: 7, font_style: 'italic', underline: true },
    { type: 'spacer', height_mm: 4 },
    { type: 'html', data: '<p style="text-align:center">Gracias por su <b>compra</b></p>' },
    { type: 'open_withdrawer' }
];

const options: PrintOptions = {
    renderer: 'pdf',
    pdfMode: 'raw', // tiquetera; 'driver' para etiqueteras con driver
    font: { family: 'Arial', size: 9, line_height: 1.25 }, // una familia de listFonts() o 'sans-serif' | 'serif' | 'monospace'
    marginsMm: { top: 1, right: 1, bottom: 3, left: 1 },
    cut: true
};

const result = await printer?.print(ticket, options);
// result: { printer, type: 'RAW', renderer: 'pdf', strategy: 'raw', width_dots: 576, cut: true,
//           page_mm: { width: 72, height: 123.4 }, fonts: [...], warnings: [...], drawer_opened: true }
console.warn(result?.warnings); // p. ej. "Font family 'X' is not installed; using sans-serif."
```

### Opciones de `print` y su clave en `settings`

Las opciones se copian a `settings` (nunca al nivel raíz del payload), encima de
los `settings` de la impresora, que no se modifican:

| Opción | Clave en `settings` |
|---|---|
| `renderer` | `renderer` (`'escpos'` \| `'pdf'`) |
| `pdfMode` | `pdf_mode` |
| `font` | `font` (`{ family, size, line_height }`) |
| `marginsMm` | `margins_mm` |
| `widthMm` | `width_mm` |
| `maxHeightMm` | `max_height_mm` |
| `cut` | `cut` |
| `settings` | se mezcla al final y gana (escape para claves nuevas del backend) |

- Solo viajan las opciones definidas: `undefined` no viaja (`false` y `0` sí).
- La mezcla es superficial: `font` o `marginsMm` reemplazan completo el objeto
  que traiga la impresora.
- `open_withdrawer` con `renderer: 'pdf'`: Apipos manda el pulso del cajón como
  un segundo trabajo raw tras imprimir el PDF (`drawer_opened: true`).

## Fuentes del sistema: `listFonts`

`apipos.listFonts()` → `GET /fonts`: las familias instaladas en la máquina de
Apipos, para elegir `font.family` o el `font_family` de un item. Lanza si
Apipos no responde (a diferencia de `listPrinters`, que devuelve `[]`).

```ts
import { Apipos } from '@tecsom/apipos-js';
import type { FontCatalog } from '@tecsom/apipos-js';

const apipos = new Apipos();

async function fillFontSelect(select: HTMLSelectElement, { refresh = false } = {}): Promise<void> {
    // refresh: true → GET /fonts?refresh=1 (vuelve a escanear, p. ej. tras instalar una fuente).
    const { families, builtin, scannedAt }: FontCatalog = await apipos.listFonts({ refresh });
    // `builtin` (sans-serif, serif, monospace) existe siempre, aunque la máquina no tenga fuentes.
    const names = [...builtin, ...families.map(family => family.family)];
    select.replaceChildren(...names.map(name => new Option(name, name)));
    select.title = `Fuentes escaneadas: ${scannedAt}`;
}
```

`families` viene ordenada por nombre; cada familia trae `monospace` y sus caras
(`faces`: `style`, `bold`, `italic`, `weight`, `full_name`, `path`, `format`...).
También devuelve `count` (número de familias) y `dirs` (directorios escaneados).

El endpoint que hay detrás se describe en [Vista previa y fuentes](../api/vista-previa-y-fuentes).

## Vista previa

### Real (la pinta Apipos): `renderTicket` y `render`

`POST /render` maqueta el ticket con el MISMO renderizador PDF que imprime y lo
devuelve sin imprimir (no valida ni toca impresoras). `content` pasa por
`transformContent`, igual que al imprimir.

```ts
import { Apipos, renderTicketPreviewPng } from '@tecsom/apipos-js';

const apipos = new Apipos();

// data URL listo para un <img> (png a 150 dpi por defecto).
const img = document.querySelector<HTMLImageElement>('#ticket-preview');
if (img) {
    img.src = await renderTicketPreviewPng(apipos, ticket, {
        settings: { paper_size: 80, font: { family: 'Arial', size: 9 } },
        dpi: 150
    });
}

// Con los settings de UNA impresora y las mismas opciones que print() (png a 203 dpi por defecto).
const preview = await printer?.render(ticket, { font: { family: 'Arial', size: 9 } });

// O el resultado completo: { format, dpi, base64, pageMm, pages, fonts, warnings, blob }.
const pdf = await apipos.renderTicket(ticket, { settings: { paper_size: 80 }, format: 'pdf' });
window.open(URL.createObjectURL(pdf.blob)); // blob: application/pdf (image/png con format: 'png')
```

| Función | Firma y defaults |
|---|---|
| `apipos.renderTicket` | `renderTicket(content, { settings = {}, format = 'pdf', dpi = 203 })`; `dpi` (72–600) solo aplica con `png` y en `pdf` el resultado trae `dpi: null`. |
| `printer.render` | `render(content, options)`: los `settings` de esa impresora más las mismas opciones que `print()`, con el mismo mapeo a `settings`; además `format` (default `png`) y `dpi` (default 203). No imprime ni valida la impresora. |
| `renderTicketPreviewPng` | `renderTicketPreviewPng(apipos, content, { settings = {}, dpi = 150 })`: data URL `data:image/png;base64,...` listo para un `<img>`. |

`base64ToBlob(base64, mime)` (base64 puro o data URI) es la misma conversión
que arma `blob`, por si guardas el `base64` y lo necesitas como archivo.

### Aproximación en pantalla (ESC/POS, sin Apipos)

`@tecsom/apipos-js/ticket-preview` exporta `renderTicketHtml(content, { paperSize })`
(HTML monoespaciado con las columnas del papel: 48 en 80 mm, 32 en 58 mm),
`TICKET_PREVIEW_CSS`, `ticketColumns(paperSize)` y `printTicketHtml(html, { title })`
(imprime desde el navegador en un iframe oculto). No necesita a Apipos, pero es
una aproximación del camino ESC/POS; `renderTicketPreviewPng` (también en ese
subpath) es la vista previa real.
