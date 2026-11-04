---
title: Tipos y versionado
---

# Tipos y versionado

## Tipos

Todos los tipos públicos se exportan desde `@tecsom/apipos-js` (y desde
`@tecsom/apipos-js/types`). Los más usados:

- `TicketContent` / `TicketItem`: unión discriminada por `type` (`text`,
  `special_text`, `table`, `separator`, `image`, `spacer`, `html`,
  `open_withdrawer`) con todos los campos del contrato de Apipos (ver
  [Ticket RAW](../api/ticket-raw)), incluidos los del renderizador PDF
  (`font_family`, `font_size` en puntos, `underline`, columnas de tabla...).
  Un `type` o un valor fuera del contrato no compila.
- `PrintSettings`: los `settings` en el formato del cable (`paper_size`,
  `char_width`, `renderer`, `pdf_mode`, `font`, `margins_mm`, `label_settings`...).
- `PrintOptions` (de `print`), `PrinterRenderOptions` (de `printer.render`),
  `RenderTicketOptions`, `RenderPreviewOptions`, `ListFontsOptions`.
- `FontCatalog` / `FontFamily` / `FontFace`, `RenderResult` / `RenderedFont`,
  `OpenDrawerResult`, `HealthResult`, `HealthData`, `PrintResult`,
  `VersionInfo` / `VersionStatus` / `VersionTuple`, `ApiposOptions`, `FetchLike`...

Los items y `settings` van en snake_case porque viajan tal cual a Apipos; las
opciones propias de la librería y los resultados ya adaptados van en camelCase
(`pdfMode`, `marginsMm`, `labelSettings`, `scannedAt`, `pageMm`).

```ts
import type { PrintOptions, PrintSettings, TicketContent } from '@tecsom/apipos-js';
```

## Versionado en lockstep con Apipos

La versión de esta librería **siempre** es el `APP_VERSION` de
`Apipos/app-meta.env`; nunca se edita a mano en apipos-js. La sube el usuario en
Apipos y se propaga con:

```bash
npm run sync-version    # app-meta.env → package.json + src/version.ts
npm run check-version   # exit 1 si alguna difiere (antes de un release)
```

Por defecto leen `../Apipos/app-meta.env` (el checkout hermano); con otra ruta:
`node scripts/sync-version.ts --check --from <ruta>`.

Un release publica el mismo tag `vX.Y.Z` en ambos repos: Apipos con sus
instaladores y apipos-js con `release/tecsom-apipos-js-X.Y.Z.tgz` (`npm run pack`).
Además, el tag `vX.Y.Z` de apipos-js dispara `publish.yml` (GitHub Actions), que
publica `@tecsom/apipos-js@X.Y.Z` en npm con *provenance*; el `.tgz` del release
queda como alternativa sin npm.
El checklist completo está en [Contribuir](../contribuir/#checklist-de-release-dos-repos).

El lado HTTP del versionado (headers y `data.client` de `GET /health`) se
describe en [Versionado y handshake](../api/versionado).

## Handshake: el aviso en la consola {#handshake-el-aviso-en-la-consola}

La librería manda `X-Apipos-Client: apipos-js/<VERSION>` en cada petición y lee
el header `X-Apipos-Version` de cada respuesta de Apipos (también de las de
error). Si las versiones no coinciden, avisa con `console.warn`. El aviso es
informativo: **nunca bloquea ni cancela la petición**, el ticket se imprime igual.

| Aviso en la consola | Qué pasa | Cómo se resuelve |
|---|---|---|
| `[apipos-js] Apipos X.Y.Z es más nuevo que la librería apipos-js A.B.C. Actualiza la librería en el front: ambas deben ir en la misma versión.` | El front trae una librería más vieja que el Apipos de la caja. | Actualiza la dependencia del front a `X.Y.Z` (`npm i -D @tecsom/apipos-js@X.Y.Z` o `pnpm add -D @tecsom/apipos-js@X.Y.Z`; sin npm, desde git o el tarball del release) y, si la sirves sin empaquetador, vuelve a copiar `dist/` a tu carpeta estática. |
| `[apipos-js] La librería apipos-js A.B.C es más nueva que Apipos X.Y.Z instalado en esta máquina. Actualiza Apipos (menú de bandeja → Buscar actualizaciones): ambas deben ir en la misma versión.` | La caja tiene un Apipos más viejo que la librería del front. | Actualiza Apipos en esa máquina: menú de bandeja → "Buscar actualizaciones", o el instalador del release `vA.B.C`. |
| `[apipos-js] Apipos no reporta su versión (falta el header X-Apipos-Version): es anterior a la librería apipos-js A.B.C. Actualiza Apipos en esta máquina.` | El Apipos de la caja es anterior a 1.0.6 (aún no tenía handshake). | Actualiza Apipos en esa máquina, igual que el caso anterior. |

- El aviso sale **una vez por página (por versión distinta de Apipos)**, no en
  cada petición, aunque la app cree varios `new Apipos()` (por ejemplo,
  uno por impresión). Con `onVersionMismatch`, una vez por cliente.
- Las respuestas sin `headers` (dobles de `fetch` en pruebas) no se evalúan.
- Con versiones iguales no hay ningún aviso.

Cómo actualizar Apipos en la caja se explica en
[Actualizaciones y logs](../guia/actualizaciones-y-logs).

### `onVersionMismatch` {#onversionmismatch}

`onVersionMismatch` reemplaza al `console.warn` (por ejemplo, para mostrarlo en
la UI o mandarlo a tu telemetría). Recibe `{ client, backend, status, message }`
una vez por versión distinta de Apipos **en ese cliente** (quien inyecta el hook
controla su propia política); si lanza, el error va a `console.error` y la
petición sigue:

```ts
import { Apipos } from '@tecsom/apipos-js';
import type { VersionInfo } from '@tecsom/apipos-js';

const apipos = new Apipos({
    onVersionMismatch: (info: VersionInfo) => {
        // info.status: 'client_older' | 'client_newer' | 'unknown'
        showBanner(info.message);
    }
});
```

### La versión en `checkHealth`

`checkHealth()` devuelve la comparación en `version`, calculada con
`data.version` de `GET /health` (útil en una pantalla de diagnóstico):

```ts
const { ok, version } = await apipos.checkHealth();
if (ok && version?.status !== 'equal') {
    console.info(version?.message);
}
// version: { client, backend, status, message }; null cuando ok es false (sin conexión o error).
```

`checkHealth()` usa el mismo aviso deduplicado: si el header ya avisó esa
versión no se repite, y si la respuesta no trajo headers el aviso sale de
`data.version`.

### Funciones puras del handshake

Las funciones puras del handshake también se exportan:

```ts
import { compareVersions, describeVersions, parseVersion, VERSION } from '@tecsom/apipos-js';

parseVersion('v1.2');                  // [1, 2, 0] (vacío, null o no numérico → null)
compareVersions('1.0.9', '1.0.10');    // 'client_older' (numérico, no de texto)
compareVersions(VERSION, null);        // 'unknown'
describeVersions('1.0.6', '1.0.6');    // { client: '1.0.6', backend: '1.0.6', status: 'equal', message: null }
```

`VERSION` (y `CLIENT_NAME`, `'apipos-js'`) también están en
`@tecsom/apipos-js/version`.
