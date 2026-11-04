---
title: Cliente JS
---

# Cliente JS

`@tecsom/apipos-js` es el cliente oficial de [Apipos](https://github.com/Tecsom/Apipos),
el agente local de impresión que corre en cada caja (`http://127.0.0.1:50432`) y
expone por HTTP las tiqueteras y etiqueteras de la máquina. Su código está en
[github.com/Tecsom/apipos-js](https://github.com/Tecsom/apipos-js).

- Escrita en **TypeScript estricto**; se distribuye compilada a `dist/`
  (módulos ES + `.d.ts`). El navegador carga `dist/` tal cual, sin empaquetador.
- **Sin dependencias** en runtime (solo `fetch`, `Blob`, `btoa` y `atob`, que
  existen en el navegador y en Node ≥ 18).
- **Desacoplada** del POS que la usa: lo que cada app quiera hacerle al texto
  antes de imprimir entra por el hook `transformContent` (ver
  [Uso](./uso#transformcontent)).
- **Versionada en lockstep con Apipos**: la librería `X.Y.Z` está hecha para
  Apipos `X.Y.Z` (ver [Tipos y versionado](./tipos-y-versionado)).

El contrato HTTP que envuelve se documenta en la sección [API HTTP](../api/).

## Instalación

| Caso | Comando |
|---|---|
| Desarrollo local (repos hermanos en `REPOSITORIES/`) | `pnpm add -D "file:../apipos-js"` |
| Release, desde git | `pnpm add -D "github:Tecsom/apipos-js#vX.Y.Z"` |
| Release, tarball | `pnpm add -D "https://github.com/Tecsom/apipos-js/releases/download/vX.Y.Z/tecsom-apipos-js-X.Y.Z.tgz"` |

Desde git, el gestor de paquetes instala las devDependencies y corre `prepare`
(= `npm run build`), así que `dist/` se genera solo. El tarball ya trae `dist/`.

::: warning
Usa siempre la versión **igual** a la del Apipos instalado en las cajas.
:::

## Servir `dist/` sin empaquetador

Para servirla al navegador sin empaquetador, copia
`node_modules/@tecsom/apipos-js/dist/` a una carpeta estática e impórtala desde
ahí (`.../apipos-js/index.js`). Funciona porque los imports relativos de la
librería llevan extensión `.js` (`import { request } from './http.js'`).

Cada vez que actualices la dependencia, vuelve a copiar `dist/` a tu carpeta
estática.

## Puntos de entrada (`exports`)

El `package.json` publica estos subpaths. Lo que no se exporta en ellos es
interno y puede cambiar sin aviso.

| Import | Archivo | Qué exporta |
|---|---|---|
| `@tecsom/apipos-js` | `dist/index.js` | `Apipos`, `ApiPosPrinter`, `ApiposError`, `base64ToBlob`, `VERSION`, `CLIENT_NAME`, `parseVersion`, `compareVersions`, `describeVersions`, `stripAccents`, `stripAccentsFromContent`, `ticketColumns`, `TICKET_PREVIEW_CSS`, `renderTicketHtml`, `printTicketHtml`, `renderTicketPreviewPng` y todos los tipos públicos |
| `@tecsom/apipos-js/strip-accents` | `dist/strip-accents.js` | `stripAccents`, `stripAccentsFromContent` |
| `@tecsom/apipos-js/ticket-preview` | `dist/ticket-preview.js` | `ticketColumns`, `TICKET_PREVIEW_CSS`, `renderTicketHtml`, `printTicketHtml`, `renderTicketPreviewPng` |
| `@tecsom/apipos-js/version` | `dist/version.js` | `VERSION`, `CLIENT_NAME` (`'apipos-js'`) |
| `@tecsom/apipos-js/types` | `dist/types.js` | Todos los tipos públicos (solo tipos) |

Cada subpath trae su `.d.ts` junto al `.js`.

## Siguientes pasos

- [Uso](./uso): crear el cliente, listar impresoras, imprimir tickets y PDFs,
  abrir el cajón y manejar errores.
- [Renderizador PDF y vista previa](./renderer-pdf-y-vista-previa): `renderer: 'pdf'`,
  fuentes del sistema y vista previa.
- [Tipos y versionado](./tipos-y-versionado): tipos exportados y el aviso de
  versión en la consola.
