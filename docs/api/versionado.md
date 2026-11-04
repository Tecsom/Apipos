---
title: Versionado y handshake
---

# Versionado y handshake

Apipos y su librería cliente oficial (`@tecsom/apipos-js`) **comparten siempre
el mismo número de versión**: la librería `X.Y.Z` está hecha para Apipos `X.Y.Z`.
Para detectar desfases, servidor y cliente se anuncian su versión por headers
HTTP. El handshake es informativo: **nunca bloquea ni rechaza una petición**.

## Headers {#headers}

- **Toda** respuesta HTTP (éxitos, errores `400`/`500` y preflight CORS) trae el
  header `X-Apipos-Version: <versión de Apipos>` (ej. `X-Apipos-Version: 1.0.6`).
- El cliente puede mandar `X-Apipos-Client: <nombre>/<major.minor.patch>`
  (ej. `apipos-js/1.0.6`). Es opcional; si falta, nada cambia. La librería
  oficial lo manda sola y avisa en la consola del navegador si las versiones
  difieren.
- CORS: `Access-Control-Allow-Headers` incluye `Content-Type` y
  `X-Apipos-Client` (el preflight lo acepta) y `Access-Control-Expose-Headers`
  incluye `X-Apipos-Version` (así `fetch` puede leerlo desde el navegador).

Para ver el header `X-Apipos-Version` de una respuesta, pide los headers con `-i`:

```bash
curl -s -i http://localhost:50432/health
```

## `GET /health` {#get-health}

`GET /health` reporta la comparación en `data.client`. Manda tu versión en
`X-Apipos-Client`:

```bash
curl -s http://localhost:50432/health -H 'X-Apipos-Client: apipos-js/1.0.5'
```

Respuesta (contra un Apipos 1.0.6):

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

::: info
Cuando `status` no es `equal`, Apipos imprime además en su stdout (visible al
correrlo headless con `APIPOS_NO_TRAY=1`) la línea `[apipos] <message>`
**una sola vez por valor distinto del header**, no en cada petición.
:::

## Lado del cliente {#lado-del-cliente}

La librería oficial `@tecsom/apipos-js` manda `X-Apipos-Client: apipos-js/<versión>`
en cada petición y lee `X-Apipos-Version` de cada respuesta (también de las de
error). Si las versiones difieren, avisa **una sola vez** en la consola del
navegador y nunca bloquea la impresión; `checkHealth()` devuelve la misma
comparación en `version` y el aviso se puede redirigir con la opción
`onVersionMismatch`. Los textos del aviso, qué hacer en cada caso y cómo
mantener la dependencia en lockstep están en
[Cliente JS → Tipos y versionado](../cliente-js/tipos-y-versionado).
