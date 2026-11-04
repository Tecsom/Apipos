---
title: Inicio
layout: home

hero:
  name: Apipos
  text: API local de impresión para puntos de venta
  tagline: Una pequeña aplicación de bandeja que expone tus impresoras de tickets y de etiquetas por HTTP en http://localhost:50432. Corre 100% local; no envía datos a internet.
  image:
    src: /logo.png
    alt: Apipos
  actions:
    - theme: brand
      text: Instalar
      link: /guia/instalacion
    - theme: alt
      text: API HTTP
      link: /api/

features:
  - title: ESC/POS por HTTP
    details: El POS (web o escritorio) hace peticiones HTTP a la API; Apipos traduce el contenido a comandos ESC/POS y los envía a la impresora. También abre el cajón de dinero y lista o selecciona impresoras, con una impresora por defecto o varias desde el mismo servicio.
  - title: PDF y etiquetas
    details: Imprime PDF enviados como base64 en el JSON, con pdf_mode "driver" (el driver de la impresora lo renderiza; el modo correcto para etiquetas) o "raw" (rasterizado a ESC/POS), y define el tamaño de la etiqueta con label_settings.
  - title: Cliente JS tipado
    details: "@tecsom/apipos-js es el cliente oficial para el navegador: TypeScript estricto compilado a módulos ES con tipos (.d.ts), sin dependencias, y siempre con la misma versión que Apipos."
---
