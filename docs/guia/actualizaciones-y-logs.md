---
title: Actualizaciones y logs
---

# Actualizaciones y logs

## Actualizaciones automáticas

Desde la bandeja, **Buscar actualizaciones** consulta el último release de
GitHub (`releases/latest`); Apipos también lo revisa en silencio unos segundos
después de arrancar. Si hay una versión más nueva, el diálogo muestra las
novedades y avisa que Apipos se cerrará; al aceptar, descarga el instalador de
la plataforma y lo abre.

- **Apipos se cierra solo** al abrir el instalador (mismo camino que *Salir*),
  para que la versión vieja no siga corriendo mientras se reemplaza. Si el
  instalador no se puede abrir (p. ej. se cancela el UAC de Windows) se muestra
  el error y Apipos sigue abierto.
- Si se cancela el instalador después de que Apipos se cerró, queda cerrado
  hasta abrirlo desde el menú Inicio / Aplicaciones o hasta volver a iniciar
  sesión (inicio automático).
- Un release que sigue en borrador no aparece en `releases/latest`, así que el
  auto-updater no lo ve hasta que se publica.

### Comportamiento por sistema operativo

| Sistema operativo | Qué pasa al aceptar la actualización |
|---|---|
| Windows | Descarga y ejecuta `Apipos-Setup.exe`. El Setup cierra cualquier `Apipos.exe` que siga corriendo antes de copiar archivos (si no logra cerrarlo en ~10 s se detiene con un mensaje) y la casilla final **Ejecutar Apipos ahora** arranca la versión nueva |
| macOS | Descarga y monta el `.dmg`; arrastra la app a Aplicaciones y ábrela |
| Linux | El auto-updater no instala solo: abre la página del release. Descarga el `.tar.gz` y corre su `install.sh` como en la [instalación](./instalacion#linux) |

## Logs y diagnóstico

Apipos escribe un archivo de log, porque el `.exe` de Windows no tiene consola
y sin él cualquier error de arranque se perdería.

### `apipos.log`

Está junto a los datos de la app:

| Sistema operativo | Ruta |
|---|---|
| Windows | `%APPDATA%\Apipos\apipos.log` |
| macOS / Linux | `~/Apipos/apipos.log` |

Para abrir la carpeta, usa **Abrir carpeta de logs** en el menú de la bandeja.

**Rotación:** al arrancar, si `apipos.log` pesa más de 1 MB se renombra a
`apipos.log.1` (reemplaza al anterior) y se empieza uno nuevo.

**Qué registra:**

- el arranque (versión, exe, pid, SO);
- todo lo que la app imprime;
- los tracebacks (también de hilos y de wx);
- los errores al cargar dependencias (`No se pudo cargar Apipos`);
- los crashes nativos (`faulthandler`);
- la instancia única;
- las actualizaciones;
- el cierre: al terminar escribe `Apipos terminó`. Si esa línea falta, el
  proceso murió por `kill`/`taskkill` o por un crash.

::: info
`apipos.log` **no** registra cada petición HTTP.
:::

**Cambiar la ruta:** `APIPOS_LOG_FILE=/ruta/archivo.log` cambia la ruta del
log (pruebas, CI).

### Log del instalador de Windows

Al terminar, el instalador de Windows deja una copia del log de Inno Setup en
`C:\Program Files\Apipos\install.log` (incluye si tuvo que cerrar Apipos). El
log original, `Setup Log *.txt`, queda en `%TEMP%`. Para generar uno a mano:
`Apipos-Setup.exe /LOG="C:\ruta\setup.log"`.

## Cuando algo falla

Manda estos archivos:

- `apipos.log`
- `apipos.log.1` (si existe)
- `install.log` (Windows)
