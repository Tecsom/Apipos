---
title: Errores comunes
---

# Errores comunes

Todos los errores llegan con el [formato de respuesta](./#formato-de-respuesta)
estándar: `"status": "error"` y el texto en `message` (HTTP `400` para errores
de negocio/validación, `500` para errores inesperados). En los textos de la
tabla, `X`, `{h}`, `{max}`, `{n}` y `{raw}` se sustituyen por el valor real.

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

Más detalle de cada caso en [PDF y etiquetas](./pdf-y-etiquetas),
[Renderizador PDF](./renderer-pdf), [Vista previa y fuentes](./vista-previa-y-fuentes)
y [Versionado y handshake](./versionado).

## Pruebas rápidas {#pruebas-rapidas}

Ticket de prueba:

```bash
curl -s 'http://localhost:50432/print/test?printer=POS80_Kinwodon'
```

Etiqueta de prueba 60×30 mm (modo driver):

```bash
curl -s 'http://localhost:50432/print/test-label?printer=AiYin_AS240_BT'
```

Etiqueta de prueba rasterizada (`mode=raw`) con un tamaño propio:

```bash
curl -s 'http://localhost:50432/print/test-label?printer=AiYin_AS240_BT&mode=raw&width=50&height=25&unit=mm'
```

Si no sabes el nombre exacto de la impresora, consúltalo antes con
[`GET /printers`](./#impresoras).
