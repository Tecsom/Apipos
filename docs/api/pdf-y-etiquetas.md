---
title: PDF y etiquetas
---

# Imprimir un PDF — `POST /print` con `type: "PDF"`

Manda un PDF ya generado (por ejemplo, una etiqueta de precio) embebido en el
JSON como base64:

```json
{
  "printer": "AiYin_AS240_BT",
  "type": "PDF",
  "data": "<PDF en base64>",
  "settings": {
    "pdf_mode": "driver",
    "label_settings": { "width": 60, "height": 30, "unit": "mm" }
  }
}
```

Guarda el JSON como `etiqueta.json` (sustituye `"<PDF en base64>"` por tu PDF en
base64) y envíalo:

```bash
curl -s -X POST http://localhost:50432/print \
  -H 'Content-Type: application/json' \
  -d @etiqueta.json
```

## Campos {#campos}

- `data` (requerido): el PDF en base64. Se acepta base64 puro o data URI
  (`"data:application/pdf;base64,..."`).
- `settings.pdf_mode`: **`"driver"` o `"raw"`**.
  - `"driver"`: el driver de la impresora renderiza el PDF (vía el sistema de
    impresión del SO). **Es el modo correcto para impresoras de etiquetas con
    driver instalado (ej. AiYin)** — su firmware ignora los trabajos raw genéricos.
  - `"raw"`: rasteriza el PDF a imagen ESC/POS y lo manda crudo. Para
    tiqueteras térmicas de recibos o impresoras sin driver.
- `settings.label_settings` (para etiquetas): `{ "width", "height", "unit" }`.
  `unit` es `"mm"` (default) o `"inch"`. En modo driver define el tamaño del
  media (ej. `media=Custom.60x30mm`); en modo raw define el ancho de
  rasterización (8 dots/mm ≈ 203 DPI).

## Defaults (si omites `pdf_mode`) {#defaults}

- Con `label_settings` → `"driver"`.
- Sin `label_settings` → `"raw"` (comportamiento de recibo).

## Reglas para etiquetas {#reglas-para-etiquetas}

- La **página del PDF debe medir lo mismo que la etiqueta** (ej. 60×30 mm =
  170×85 pt). El driver escala al media: un PDF tamaño carta saldría deforme.
- Un PDF de varias páginas imprime **una etiqueta por página**.
- Ejemplo de respuesta exitosa en modo driver:
  `{"status":"success","data":{"strategy":"driver","media":"Custom.60x30mm",...}}`

::: tip
Si una etiquetera responde `success` pero no imprime, casi siempre recibió un
trabajo raw genérico: usa `pdf_mode: "driver"` (ver
[Errores comunes](./errores-comunes)).
:::

Para probar una etiquetera sin generar tu propio PDF usa
[`/print/test-label`](./#pruebas-de-impresion).

## Errores {#errores}

| `message` | Causa | Corrección |
|---|---|---|
| `Invalid base64 PDF data.` / `Provided data is not a valid PDF.` | `data` corrupto o no es PDF | Verifica la codificación base64 |
| `Unsupported pdf_mode 'X'. Use 'driver' or 'raw'.` | Modo inválido | Solo `driver` o `raw` |
| `Unsupported unit 'X'. Use 'mm' or 'inch'.` | Unidad inválida | Solo `mm` o `inch` |
| `label_settings requires a numeric 'width'.` | Falta ancho | Incluye `width` numérico |

La tabla completa está en [Errores comunes](./errores-comunes).
