import { defineConfig } from 'vitepress'

export default defineConfig({
  lang: 'es-MX',
  title: 'Apipos',
  description:
    'API local de impresión para puntos de venta (ESC/POS, PDF y etiquetas) y su cliente JavaScript.',
  base: '/Apipos/',
  cleanUrls: true,
  lastUpdated: true,
  srcExclude: ['**/node_modules/**', '**/README.md'],

  head: [['link', { rel: 'icon', type: 'image/png', href: '/Apipos/logo.png' }]],

  themeConfig: {
    logo: '/logo.png',

    nav: [
      { text: 'Guía', link: '/guia/instalacion', activeMatch: '/guia/' },
      { text: 'API HTTP', link: '/api/', activeMatch: '/api/' },
      { text: 'Cliente JS', link: '/cliente-js/', activeMatch: '/cliente-js/' },
      { text: 'Contribuir', link: '/contribuir/', activeMatch: '/contribuir/' },
      { text: 'Descargas', link: 'https://github.com/Tecsom/Apipos/releases/latest' }
    ],

    sidebar: [
      {
        text: 'Inicio',
        items: [{ text: 'Inicio', link: '/' }]
      },
      {
        text: 'Guía',
        items: [
          { text: 'Instalación', link: '/guia/instalacion' },
          { text: 'Primeros pasos', link: '/guia/primeros-pasos' },
          { text: 'Actualizaciones y logs', link: '/guia/actualizaciones-y-logs' }
        ]
      },
      {
        text: 'API HTTP',
        items: [
          { text: 'Introducción', link: '/api/' },
          { text: 'Ticket RAW', link: '/api/ticket-raw' },
          { text: 'Renderizador PDF', link: '/api/renderer-pdf' },
          { text: 'PDF y etiquetas', link: '/api/pdf-y-etiquetas' },
          { text: 'Vista previa y fuentes', link: '/api/vista-previa-y-fuentes' },
          { text: 'Versionado', link: '/api/versionado' },
          { text: 'Errores comunes', link: '/api/errores-comunes' }
        ]
      },
      {
        text: 'Cliente JS',
        items: [
          { text: 'Introducción', link: '/cliente-js/' },
          { text: 'Uso', link: '/cliente-js/uso' },
          { text: 'Renderizador PDF y vista previa', link: '/cliente-js/renderer-pdf-y-vista-previa' },
          { text: 'Tipos y versionado', link: '/cliente-js/tipos-y-versionado' }
        ]
      },
      {
        text: 'Contribuir',
        items: [{ text: 'Contribuir', link: '/contribuir/' }]
      }
    ],

    socialLinks: [
      { icon: 'github', link: 'https://github.com/Tecsom/Apipos', ariaLabel: 'Apipos en GitHub' },
      { icon: 'github', link: 'https://github.com/Tecsom/apipos-js', ariaLabel: 'apipos-js en GitHub' }
    ],

    editLink: {
      pattern: 'https://github.com/Tecsom/Apipos/edit/main/docs/:path',
      text: 'Editar esta página'
    },

    search: {
      provider: 'local',
      options: {
        translations: {
          button: {
            buttonText: 'Buscar',
            buttonAriaLabel: 'Buscar'
          },
          modal: {
            displayDetails: 'Mostrar detalles',
            resetButtonTitle: 'Limpiar búsqueda',
            backButtonTitle: 'Cerrar búsqueda',
            noResultsText: 'Sin resultados para',
            footer: {
              selectText: 'seleccionar',
              selectKeyAriaLabel: 'Intro',
              navigateText: 'navegar',
              navigateUpKeyAriaLabel: 'flecha arriba',
              navigateDownKeyAriaLabel: 'flecha abajo',
              closeText: 'cerrar',
              closeKeyAriaLabel: 'Esc'
            }
          }
        }
      }
    },

    outline: { label: 'En esta página' },
    docFooter: { prev: 'Anterior', next: 'Siguiente' },
    lastUpdated: { text: 'Última actualización' },
    returnToTopLabel: 'Volver arriba',
    sidebarMenuLabel: 'Menú',
    darkModeSwitchLabel: 'Apariencia',
    lightModeSwitchTitle: 'Cambiar a tema claro',
    darkModeSwitchTitle: 'Cambiar a tema oscuro',
    langMenuLabel: 'Cambiar idioma',
    notFound: {
      title: 'PÁGINA NO ENCONTRADA',
      quote: 'La página que buscas no existe o se movió.',
      linkLabel: 'Ir al inicio',
      linkText: 'Volver al inicio'
    }
  }
})
