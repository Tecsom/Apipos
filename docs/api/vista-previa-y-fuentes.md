---
title: Vista previa y fuentes
---

# Vista previa y fuentes

## Vista previa — `POST /render` {#vista-previa}

Renderiza un ticket RAW con el [renderizador PDF](./renderer-pdf) y devuelve el
resultado en base64 **sin imprimir**: no valida impresora ni toca ninguna. Sirve
para mostrar una vista previa en el front o probar un ticket sin hardware.

Body: el mismo de `POST /print` (`settings` y `content`; también se acepta la
lista legacy de items) más los campos de abajo. `printer` y `type` se ignoran, y
siempre se usa el renderizador PDF (no hace falta `settings.renderer`;
`pdf_mode`, `cut` y `open_withdrawer` no tienen efecto aquí).

| Campo | Valores | Default |
|---|---|---|
| `format` | `"pdf"` \| `"png"` | `"pdf"` |
| `dpi` | entero 72–600 (solo con `png`) | `203` |

```json
{
  "format": "png",
  "dpi": 203,
  "settings": { "paper_size": 80, "font": { "family": "sans-serif", "size": 9 } },
  "content": [
    { "type": "text", "data": "HOLA", "align": "center", "font_size": "lg" },
    { "type": "special_text", "data": { "text1": "TOTAL", "text2": "$1.00" } }
  ]
}
```

Guarda el JSON como `preview.json` y envíalo:

```bash
curl -s -X POST http://localhost:50432/render \
  -H 'Content-Type: application/json' \
  -d @preview.json
```

Respuesta:

```json
{
  "status": "success",
  "data": {
    "format": "png", "dpi": 203, "base64": "<PNG en base64>",
    "page_mm": { "width": 72, "height": 19.9 }, "pages": 1,
    "fonts": [ { "family": "sans-serif", "resolved": "Helvetica", "source": "builtin", "bold": false, "italic": false } ],
    "warnings": []
  },
  "message": "Ticket rendered."
}
```

- Con `format: "pdf"` el `base64` es el PDF (empieza con `JVBERi`) y `dpi` vale
  `null` (el `dpi` del body se ignora). Con `png` es la imagen de la página
  (empieza con `iVBORw0KGgo`); a 203 dpi un ticket de 72 mm mide 576 px de ancho.
- `dpi` acepta un entero (`203`, `203.0` o `"203"`); solo se valida con `png`.
- `page_mm`, `fonts` y `warnings` tienen el mismo significado que en la
  [respuesta del renderizador PDF](./renderer-pdf#respuesta).

### Errores de `/render` {#errores-render}

- `format` inválido → `Unsupported format 'X'. Use 'pdf' or 'png'.`
- `dpi` fuera de rango o no entero → `'dpi' must be an integer between 72 and 600.`
- sin `content` → `No content to print.`
- el resto (`font.size`, ticket demasiado alto, imagen inválida,
  `label_settings` inválido), con los mismos textos que en `POST /print`
  (ver [Errores comunes](./errores-comunes)).

## Fuentes del sistema — `GET /fonts` {#fuentes-del-sistema}

Lista las familias de fuentes instaladas en la máquina (con sus estilos) para
elegir `settings.font.family` / `font_family` del renderizador PDF.

| Petición | Efecto |
|---|---|
| `GET /fonts` | usa el catálogo en memoria (el primer acceso escanea) |
| `GET /fonts?refresh=1` | vuelve a escanear (ej. tras instalar una fuente) |

```bash
curl -s http://localhost:50432/fonts
curl -s 'http://localhost:50432/fonts?refresh=1'
```

Respuesta (recortada a una familia con una sola cara):

```json
{
  "status": "success",
  "data": {
    "families": [
      {
        "family": "Arial",
        "monospace": false,
        "faces": [
          { "style": "Regular", "bold": false, "italic": false, "weight": 400,
            "full_name": "Arial", "postscript_name": "ArialMT",
            "path": "/System/Library/Fonts/Supplemental/Arial.ttf", "index": 0, "format": "ttf" }
        ]
      }
    ],
    "count": 380,
    "builtin": ["sans-serif", "serif", "monospace"],
    "dirs": ["/System/Library/Fonts", "/Library/Fonts", "/Users/x/Library/Fonts"],
    "scanned_at": "2026-10-26T18:04:11"
  },
  "message": "Fonts listed."
}
```

En una respuesta real `faces` trae una entrada por cara de la familia (por
ejemplo, la cara `"Bold"` con `"bold": true` y `"weight": 700`).

- `families` viene ordenada por `family` sin distinguir mayúsculas; `faces`, por
  (`weight`, `italic`). Usa el valor de `family` tal cual (las mayúsculas no
  importan) en `settings.font.family` o `font_family`.
- `count` = número de familias. `monospace` es `true` si todas las caras de la
  familia son de ancho fijo.
- Cada cara: `style`, `bold`, `italic`, `weight` (peso OpenType: 400 = normal,
  700 = negrita; `bold` es `true` desde 600), `full_name`,
  `postscript_name`, `path`, `index` (posición de la cara dentro de un `.ttc`/`.otc`;
  `0` en archivos de una sola cara) y `format` (`ttf` \| `otf` \| `ttc` \| `otc`).
- `builtin`: familias genéricas que el renderizador acepta **siempre**, aunque
  la máquina no tenga ninguna fuente instalada.
- `dirs`: directorios escaneados que existen en esta máquina. Windows:
  `%WINDIR%\Fonts` y `%LOCALAPPDATA%\Microsoft\Windows\Fonts`; macOS:
  `/System/Library/Fonts`, `/Library/Fonts` y `~/Library/Fonts`.
- `scanned_at`: fecha y hora local del último escaneo (ISO 8601).
- `refresh` acepta `1`, `true`, `yes`, `on` o `si`. Las fuentes que no se
  pueden leer se omiten sin error.

Cómo se resuelve cada familia al renderizar (integradas, instaladas, sustitutos
y avisos) está en [Renderizador PDF → Fuentes](./renderer-pdf#fuentes).
