---
title: Uso
---

# Uso

Esta página recorre el cliente de punta a punta: crear el `Apipos`, comprobar
que Apipos responde, crear una impresora y mandarle tickets, PDFs y la apertura
del cajón. El contrato HTTP de cada llamada está en la sección [API HTTP](../api/).

## Crear el cliente

```ts
import { Apipos, ApiposError } from '@tecsom/apipos-js';
import type { TicketContent } from '@tecsom/apipos-js';

const apipos = new Apipos(); // baseUrl por defecto: http://127.0.0.1:50432
```

`new Apipos({ baseUrl, fetch, transformContent, onVersionMismatch })` acepta
estas opciones, todas opcionales:

| Opción | Default | Qué hace |
|---|---|---|
| `baseUrl` | `http://127.0.0.1:50432` | URL base de Apipos. |
| `fetch` | el `fetch` global vigente en cada petición | Inyectable (pruebas). |
| `transformContent` | copia superficial (`content.slice()`) | Se aplica al `content` en cada trabajo; ver [`transformContent`](#transformcontent). |
| `onVersionMismatch` | el aviso en la consola (`console.warn`) | Reemplaza el aviso de versión en consola; ver [Tipos y versionado](./tipos-y-versionado#onversionmismatch). |

`apipos.apiUrl` (get/set) se conserva como alias de `baseUrl` por compatibilidad.

Toda petición lleva el header `X-Apipos-Client: apipos-js/<versión>` y toda
respuesta de Apipos trae `X-Apipos-Version`: así cada lado sabe la versión del
otro (handshake). Si no coinciden, la librería avisa en la consola del navegador
(ver [Tipos y versionado](./tipos-y-versionado#handshake-el-aviso-en-la-consola)).

## `checkHealth`: ¿está corriendo Apipos? {#checkhealth}

`checkHealth()` nunca lanza.

```ts
const { ok, data, version } = await apipos.checkHealth();
// data: { status, version, os, platform, backend, port, client }
// version: { client: '1.0.6', backend: '1.0.6', status: 'equal', message: null } (null si ok es false)
```

`ok` es `true` si el servicio responde `"ok"`. Ante cualquier error devuelve
`{ ok: false, data: null, version: null }`.

## `listPrinters`: impresoras instaladas

Devuelve los nombres **exactos** de las impresoras instaladas (`[]` si Apipos no
responde).

```ts
const printers = await apipos.listPrinters(); // ['POS80_Kinwodon', 'AiYin_AS240_BT']
```

## `createPrinter`: una impresora con sus settings

`apipos.createPrinter(name, settings)` recibe el nombre exacto (de
`listPrinters()`) y los `settings` de la impresora. `paper_size` numérico es
obligatorio; si falta o no es número, lanza uno de estos errores:

- `Missing required setting: paper_size`
- `Invalid type for setting paper_size: expected number, got <tipo>`

Sin nombre devuelve `null` (y lo reporta en consola con `Printer name is required`).

```ts
const printer = apipos.createPrinter('POS80_Kinwodon', { paper_size: 80 });
```

## `print`: ticket RAW (ESC/POS)

```ts
const ticket: TicketContent = [
    { type: 'text', data: 'MI TIENDA S.A.', align: 'center', font_size: 'md', font_weight: 'bold' },
    { type: 'separator' },
    { type: 'table', data: { rows: [[2, 'Coca Cola 600ml', '$18.00', '$36.00']] } },
    { type: 'special_text', data: { text1: 'TOTAL', text2: '$36.00' }, font_weight: 'bold' },
    { type: 'open_withdrawer' }
];

try {
    await printer?.print(ticket);
} catch (error) {
    if (error instanceof ApiposError) {
        // Mensaje de Apipos (p. ej. "Printer 'X' not found.") y su `data`
        // (p. ej. { available: [...] } con las impresoras válidas).
        console.error(error.message, error.data);
    } else {
        // Sin conexión: "No se pudo conectar con Apipos (<url>). ¿Está abierta la app de bandeja?"
        console.error(error);
    }
}
```

- `print(content)` manda exactamente `{ printer, type: 'RAW', settings, content }`
  a `POST /print` y devuelve el `data` de la respuesta de Apipos.
- `print(content, options)` acepta opciones del renderizador PDF (ver
  [Renderizador PDF y vista previa](./renderer-pdf-y-vista-previa)); sin `options`
  (o con `{}`) el payload es el de siempre, byte a byte.
- El `content` pasa por `transformContent` en cada trabajo.

Los items de `content` y sus campos están en [Ticket RAW](../api/ticket-raw).

## `printPDF`: imprimir un PDF

`printPDF(blob, options)` recibe el PDF como `Blob` y manda
`{ printer, type: 'PDF', settings, data }` a `POST /print`, con el PDF en base64.
Devuelve el `data` de la respuesta de Apipos.

```ts
// PDF (Blob): 'driver' para etiqueteras con driver (AiYin), 'raw' para tiqueteras.
await printer?.printPDF(pdfBlob, { pdfMode: 'driver', labelSettings: { width: 60, height: 30, unit: 'mm' } });
```

| Opción | Clave en `settings` | Valores |
|---|---|---|
| `pdfMode` | `pdf_mode` | `'driver'` (el driver de la impresora renderiza el PDF; el modo correcto para etiquetas, ej. AiYin) \| `'raw'` (rasteriza a ESC/POS, para tiqueteras de recibos). Default del servidor: `'driver'` si se mandan `labelSettings`, `'raw'` si no. |
| `labelSettings` | `label_settings` | `{ width, height, unit: 'mm' \| 'inch' }`: tamaño de la etiqueta; la página del PDF debe medir lo mismo. |

Las reglas de `pdf_mode` y `label_settings` del lado de Apipos están en
[PDF y etiquetas](../api/pdf-y-etiquetas).

## `openDrawer`: abrir el cajón

Abre el cajón de dinero conectado a esa impresora sin imprimir
(`POST /open-withdrawer` con `{ printer }`).

```ts
await printer?.openDrawer(); // → { printer: 'POS80_Kinwodon' }
```

Lanza `ApiposError` si Apipos responde error (p. ej. `Printer 'X' not found.`).

## Errores: `ApiposError`

| Situación | Qué lanza |
|---|---|
| Apipos responde `status: 'error'` o un HTTP no-2xx | `ApiposError`: `message` es el del backend (p. ej. `Printer 'X' not found.`) y `data` lo que traiga el sobre (p. ej. `{ available: [...] }` con las impresoras válidas). Sigue siendo `instanceof Error`. |
| Apipos no responde | `Error` con `No se pudo conectar con Apipos (<url>). ¿Está abierta la app de bandeja?` |
| Apipos responde éxito con una forma que no es la del contrato | `Error` con `Respuesta inesperada de Apipos en <ruta>` |

`checkHealth()` y `listPrinters()` no lanzan: devuelven
`{ ok: false, data: null, version: null }` y `[]`, respectivamente.

## `transformContent`: preparar el texto antes de imprimir {#transformcontent}

La librería no toca el texto del ticket. Si tu app necesita limpiarlo (comillas
tipográficas, quitar acentos para tiqueteras sin Latin-1...), pásalo como hook:

```ts
import { Apipos, stripAccentsFromContent } from '@tecsom/apipos-js';

const apipos = new Apipos({
    // Se llama en CADA trabajo (un ajuste cambiado vale desde el siguiente ticket)
    // y debe devolver un arreglo NUEVO: la librería nunca muta lo que recibe.
    transformContent: content => (deviceWantsNoAccents() ? stripAccentsFromContent(content) : content.slice())
});
```

El default es una copia superficial (`content.slice()`). `stripAccents` y
`stripAccentsFromContent` (también en `@tecsom/apipos-js/strip-accents`) quitan
acentos, `ñ`, `¿ ¡` y ordinales sin mover el ancho de las líneas, y no recorren
el base64 de las imágenes.

`transformContent` también se aplica al `content` de la vista previa real
(`renderTicket`), igual que al imprimir.
