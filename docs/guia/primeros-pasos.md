---
title: Primeros pasos
---

# Primeros pasos

Con Apipos [instalado](./instalacion) y corriendo, todo se hace por HTTP contra
`http://localhost:50432`. El formato es JSON (`Content-Type: application/json`),
sin autenticación y con CORS habilitado. Los ejemplos de esta página usan `curl`.

## Comprueba que Apipos responde

```bash
curl -s http://localhost:50432/health
```

Respuesta:

```json
{
  "status": "success",
  "data": {
    "status": "ok",
    "version": "1.0.6",
    "os": "Darwin",
    "platform": "darwin",
    "backend": "MacPrinterBackend",
    "port": 50432,
    "client": null
  },
  "message": "Service is running."
}
```

`data.version` es la versión de Apipos instalada y `data.backend` el backend de
impresión activo según el sistema operativo. `data.client` es `null` cuando la
petición no trae el header `X-Apipos-Client`; el handshake de versión se explica
en [Versionado](../api/versionado).

## Lista las impresoras

```bash
curl -s http://localhost:50432/printers
```

Respuesta:

```json
{
  "status": "success",
  "data": ["POS80_Kinwodon", "AiYin_AS240_BT"],
  "message": "Printers listed."
}
```

Copia el nombre **exacto** de la impresora que vas a usar (respeta guiones
bajos, como en `"AiYin_AS240_BT"`).

## Fija la impresora por defecto

La impresora por defecto es la que Apipos usa cuando una petición omite
`"printer"`. Guarda el JSON como `impresora.json`:

```json
{ "printer": "POS80_Kinwodon" }
```

y envíalo:

```bash
curl -s -X POST http://localhost:50432/printers/selected \
  -H 'Content-Type: application/json' \
  -d @impresora.json
```

Respuesta:

```json
{
  "status": "success",
  "data": "POS80_Kinwodon",
  "message": "Selected printer updated."
}
```

Para consultar cuál está seleccionada (`data` es `null` si no hay ninguna):

```bash
curl -s http://localhost:50432/printers/selected
```

Si el nombre no existe, la respuesta es `400` con
`message: "Printer 'X' not found."` y `data.available` = lista de impresoras
válidas. Úsala para corregir el nombre.

::: tip
**Manda siempre `"printer"` explícito** en tus trabajos de impresión. Si se
omite se usa la impresora seleccionada, que puede no ser la que esperas.
:::

## Imprime el ticket de prueba

`/print/test` imprime el ticket de prueba integrado (un PDF de 80 mm incluido en
la app). Sirve para validar rápido que una impresora imprime bien. Pasa el
nombre en el query param `printer` (si lo omites, usa la impresora por defecto):

```bash
curl -s 'http://localhost:50432/print/test?printer=POS80_Kinwodon'
```

Respuesta:

```json
{
  "status": "success",
  "data": {
    "printer": "POS80_Kinwodon",
    "type": "PDF",
    "strategy": "raw",
    "width_dots": 576,
    "cut": true
  },
  "message": "PDF print job sent."
}
```

También responde a `POST` (mismo comportamiento), por si tu cliente no permite
`GET`. Para etiqueteras existe `/print/test-label`, que imprime una etiqueta de
prueba de 60×30 mm (ver [PDF y etiquetas](../api/pdf-y-etiquetas)).

## Imprime tu primer ticket

Un ticket es un trabajo `RAW`: una lista de items en `content` que Apipos
traduce a ESC/POS. El corte de papel se agrega automáticamente al final.
Guarda el JSON como `ticket.json`:

```json
{
  "printer": "POS80_Kinwodon",
  "type": "RAW",
  "settings": { "paper_size": 80 },
  "content": [
    { "type": "text", "data": "MI TIENDA S.A.", "align": "center", "font_size": "md", "font_weight": "bold" },
    { "type": "text", "data": "Av. Principal 123", "align": "center" },
    { "type": "separator" },
    { "type": "table", "data": { "rows": [
        [2, "Coca Cola 600ml", "$18.00", "$36.00"],
        [1, "Pan Bimbo", "$45.50", "$45.50"]
    ]}},
    { "type": "separator" },
    { "type": "special_text", "data": { "text1": "TOTAL", "text2": "$81.50" }, "font_size": "md", "font_weight": "bold" },
    { "type": "text", "data": "¡Gracias por su compra!", "align": "center" }
  ]
}
```

y envíalo:

```bash
curl -s -X POST http://localhost:50432/print \
  -H 'Content-Type: application/json' \
  -d @ticket.json
```

Respuesta:

```json
{
  "status": "success",
  "data": { "printer": "POS80_Kinwodon", "char_width": 48 },
  "message": "Print job completed."
}
```

`data.char_width` son las columnas del ticket: `paper_size` `80` da 48 columnas
y `58` da 32. Todos los items (`image`, `spacer`, `html`, `open_withdrawer`…),
sus campos y los `settings` están en [Ticket RAW](../api/ticket-raw).

## Formato de respuesta

Todos los endpoints responden con la misma forma:

```json
{ "status": "success", "data": null, "message": "texto" }
```

- `status`: `"success"` o `"error"`.
- `data`: el resultado (su forma depende del endpoint) o `null`.
- `message`: texto que describe el resultado.

HTTP `200` = éxito, `400` = error de negocio/validación, `500` = error inesperado.
Evalúa siempre el campo `status`, no solo el código HTTP.

## Siguientes pasos

- [API HTTP](../api/): todos los endpoints, tickets RAW, PDF y etiquetas, vista
  previa y errores comunes.
- [Cliente JS](../cliente-js/): `@tecsom/apipos-js`, el cliente oficial y tipado
  para el navegador.
