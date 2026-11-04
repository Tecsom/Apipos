---
title: API HTTP
---

# API HTTP

Apipos es un agente local que expone impresoras térmicas (tickets) y de etiquetas
por HTTP. Corre en la misma máquina que la impresora.

- **Base URL:** `http://127.0.0.1:50432`
- **Formato:** JSON (`Content-Type: application/json`). Sin autenticación. CORS habilitado.
- Los PDF se envían **embebidos en el JSON como base64** (no multipart, no URL).

## Formato de respuesta

Todos los endpoints responden con la misma forma:

```text
{ "status": "success" | "error", "data": <objeto o null>, "message": "texto" }
```

HTTP `200` = éxito, `400` = error de negocio/validación, `500` = error inesperado.
Evalúa siempre el campo `status`, no solo el código HTTP.

Por ejemplo, un error de validación (HTTP `400`) se ve así:

```json
{
  "status": "error",
  "data": { "available": ["POS80_Kinwodon", "AiYin_AS240_BT"] },
  "message": "Printer 'AiYin-AS240-BT' not found."
}
```

## Endpoints

| Método | Ruta | Descripción | Documentación |
|---|---|---|---|
| GET | `/health` | Estado del servicio (incluye el handshake de versión en `data.client`) | [Estado del servicio](#estado-del-servicio), [Versionado](./versionado) |
| GET | `/printers` | Lista los nombres de impresoras instaladas | [Impresoras](#impresoras) |
| GET | `/printers/selected` | Impresora seleccionada por defecto (o `null`) | [Impresoras](#impresoras) |
| POST | `/printers/selected` | Fija la impresora por defecto: `{"printer": "NOMBRE"}` | [Impresoras](#impresoras) |
| POST | `/print` | Imprime un trabajo RAW (ticket ESC/POS o renderizado a PDF) o PDF | [Ticket RAW](./ticket-raw), [Renderizador PDF](./renderer-pdf), [PDF y etiquetas](./pdf-y-etiquetas) |
| POST | `/render` | Vista previa: renderiza un ticket RAW a PDF o PNG (base64) **sin imprimir** | [Vista previa](./vista-previa-y-fuentes#vista-previa) |
| GET | `/fonts` | Catálogo de fuentes instaladas en la máquina (`?refresh=1` re-escanea) | [Fuentes del sistema](./vista-previa-y-fuentes#fuentes-del-sistema) |
| GET/POST | `/print/test` | Imprime el ticket de prueba integrado | [Pruebas de impresión](#pruebas-de-impresion) |
| GET/POST | `/print/test-label` | Imprime la etiqueta de prueba integrada (60×30 mm) | [Pruebas de impresión](#pruebas-de-impresion) |
| POST | `/open-withdrawer` | Abre el cajón de dinero: `{"printer": "NOMBRE"}` (opcional) | [Cajón de dinero](#cajon-de-dinero) |

## Reglas generales

1. **Manda siempre `"printer"` explícito.** Si se omite se usa la impresora
   seleccionada, que puede no ser la que esperas. Los nombres exactos vienen de
   `GET /printers` (ej. `"AiYin_AS240_BT"` — respeta guiones bajos).
2. Si la impresora no existe, la respuesta es `400` con
   `message: "Printer 'X' not found."` y `data.available` = lista de impresoras
   válidas. Úsala para corregir el nombre.
3. `message: "No printer selected."` significa que omitiste `"printer"` y no hay
   impresora por defecto configurada.

### CORS

CORS está habilitado y no hay autenticación, así que puedes llamar a Apipos
directamente desde el navegador:

- `Access-Control-Allow-Headers` incluye `Content-Type` y `X-Apipos-Client`
  (el preflight lo acepta).
- `Access-Control-Expose-Headers` incluye `X-Apipos-Version` (así `fetch` puede
  leerlo desde el navegador).
- **Toda** respuesta HTTP (éxitos, errores `400`/`500` y preflight CORS) trae el
  header `X-Apipos-Version`. Los detalles del handshake están en
  [Versionado y handshake](./versionado).

## Estado del servicio {#estado-del-servicio}

`GET /health` confirma que Apipos está corriendo y, si mandas el header
`X-Apipos-Client`, compara tu versión con la del servidor en `data.client`:

```bash
curl -s http://localhost:50432/health
```

La respuesta completa y los valores de `data.client` están en
[Versionado y handshake](./versionado#get-health).

## Impresoras {#impresoras}

Lista los nombres de las impresoras instaladas. Copia el nombre exacto de aquí
para el campo `"printer"` de tus trabajos:

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

Consulta la impresora seleccionada por defecto (`data` es `null` si no hay
ninguna):

```bash
curl -s http://localhost:50432/printers/selected
```

Respuesta:

```json
{
  "status": "success",
  "data": "POS80_Kinwodon",
  "message": ""
}
```

Fija la impresora por defecto, la que se usa cuando un trabajo no trae
`"printer"`:

```json
{ "printer": "POS80_Kinwodon" }
```

Guarda el JSON como `impresora.json` y envíalo:

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

Si falta `printer` la respuesta es `400` con `message: "Field 'printer' is required."`;
si el nombre no existe, `400` con `Printer 'X' not found.` y `data.available`.

## Cajón de dinero {#cajon-de-dinero}

`POST /open-withdrawer` abre el cajón de dinero conectado a la impresora. El body
`{"printer": "NOMBRE"}` es opcional; si se omite usa la impresora por defecto
(y si no hay ninguna, responde `No printer selected.`).

```json
{ "printer": "POS80_Kinwodon" }
```

Guarda el JSON como `cajon.json` y envíalo:

```bash
curl -s -X POST http://localhost:50432/open-withdrawer \
  -H 'Content-Type: application/json' \
  -d @cajon.json
```

Respuesta:

```json
{
  "status": "success",
  "data": { "printer": "POS80_Kinwodon" },
  "message": "Cash drawer opened."
}
```

Para abrir el cajón al final de un ticket usa el item `open_withdrawer` de
[Ticket RAW](./ticket-raw#items-de-content).

## Pruebas de impresión {#pruebas-de-impresion}

Ambos endpoints aceptan `GET` o `POST` (mismo comportamiento) y toman la
impresora del query param `printer`; si se omite, usan la impresora por defecto.

`/print/test` imprime el ticket de prueba integrado:

```bash
curl -s 'http://localhost:50432/print/test?printer=POS80_Kinwodon'
```

Respuesta:

```json
{
  "status": "success",
  "data": {
    "printer": "POS80_Kinwodon", "type": "PDF", "strategy": "raw",
    "width_dots": 576, "cut": true
  },
  "message": "PDF print job sent."
}
```

`/print/test-label` imprime la etiqueta de prueba integrada (60×30 mm). Por
defecto usa el modo `driver`; con `mode=raw` la rasteriza a ESC/POS, y `width`,
`height` y `unit` cambian el tamaño (mismo significado que
[`label_settings`](./pdf-y-etiquetas#campos)):

```bash
curl -s 'http://localhost:50432/print/test-label?printer=AiYin_AS240_BT'
curl -s 'http://localhost:50432/print/test-label?printer=AiYin_AS240_BT&mode=raw&width=50&height=25&unit=mm'
```

Más comandos de prueba en [Errores comunes → Pruebas rápidas](./errores-comunes#pruebas-rapidas).
