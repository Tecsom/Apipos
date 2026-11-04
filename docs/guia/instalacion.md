---
title: Instalación
---

# Instalación

Apipos es una API local de impresión para puntos de venta. Corre como una
pequeña aplicación de bandeja (system tray / barra de menú) en la misma máquina
que la impresora y expone una API HTTP en `http://localhost:50432` para imprimir
tickets ESC/POS, abrir el cajón de dinero y listar/seleccionar impresoras.

El servicio corre 100% local; no envía datos a internet.

## Descarga

Descarga el instalador de tu sistema operativo desde el último release:
[github.com/Tecsom/Apipos/releases/latest](https://github.com/Tecsom/Apipos/releases/latest).

| Sistema operativo | Archivo en el release |
|---|---|
| Windows x64 | `Apipos-Setup.exe` |
| macOS arm64 (Apple Silicon) | `Apipos-X.Y.Z-arm64.dmg` |
| Linux x86_64 | `Apipos-X.Y.Z-linux-x86_64.tar.gz` |

`X.Y.Z` es la versión del release (por ejemplo `Apipos-2.0.1-linux-x86_64.tar.gz`).

## Windows

Ejecuta `Apipos-Setup.exe`. El instalador:

- instala Apipos en `C:\Program Files\Apipos`;
- crea en el menú Inicio los accesos directos **Apipos** y **Desinstalar Apipos**;
- registra el inicio automático al iniciar sesión;
- si Apipos ya estaba corriendo, lo cierra antes de copiar archivos (si no logra
  cerrarlo en ~10 s se detiene con un mensaje);
- al final ofrece la casilla **Ejecutar Apipos ahora**, que arranca la versión
  instalada;
- deja una copia de su log en `C:\Program Files\Apipos\install.log` (ver
  [Actualizaciones y logs](./actualizaciones-y-logs#log-del-instalador-de-windows)).

El desinstalador también cierra la app antes de quitarla.

::: info
El `.exe` de Windows es *onefile* de PyInstaller, así que **una** instancia se
ve como **dos** procesos `Apipos.exe` en el Administrador de tareas.
:::

## macOS

Abre el `.dmg`, arrastra la app a Aplicaciones y ábrela. Apipos es una app de
barra de menú: no muestra ícono en el Dock, solo en la barra de menú.

La primera vez que se abre, la propia app se registra para arrancar al iniciar
sesión (un LaunchAgent en `~/Library/LaunchAgents`).

::: warning
Un `.dmg` sin firmar lo bloquea Gatekeeper al descargarlo.
:::

## Linux

Descomprime el `.tar.gz` y corre `install.sh` desde la carpeta descomprimida:

```bash
tar xzf Apipos-2.0.1-linux-x86_64.tar.gz
./Apipos-2.0.1-linux-x86_64/install.sh          # --uninstall para quitarlo
```

`install.sh` instala para el usuario (no necesita `sudo`) en
`~/.local/share/Apipos`, agrega el lanzador al menú de apps y el inicio
automático (`~/.config/autostart`), y arranca la app. Si Apipos ya estaba
corriendo, lo detiene antes de reemplazarlo. Para desinstalar:
`./install.sh --uninstall`.

::: warning
El bundle depende de la glibc de la máquina donde se compiló. Los instaladores
se compilan en Ubuntu 22.04, así que corre en esa versión o más nueva.
:::

::: tip
En GNOME el ícono de bandeja requiere la extensión
"AppIndicator and KStatusNotifierItem Support".
:::

## El ícono de bandeja

Al iniciar, Apipos levanta el servidor HTTP (puerto `50432`) y muestra un ícono
en la bandeja del sistema (barra de menú en macOS). Al pasar el mouse muestra
`Apipos — puerto 50432`; un clic izquierdo abre `http://localhost:50432/health`
en el navegador.

Su menú tiene estas entradas:

| Entrada | Qué hace |
|---|---|
| `Apipos vX.Y.Z` | Solo informativa (no se puede hacer clic): la versión instalada |
| `Corriendo en http://localhost:50432` | Solo informativa: dónde está escuchando el API |
| **Ver estado** | Abre `http://localhost:50432/health` en el navegador |
| **Buscar actualizaciones** | Consulta el último release de GitHub (ver [Actualizaciones y logs](./actualizaciones-y-logs)) |
| **Abrir carpeta de logs** | Abre la carpeta que contiene `apipos.log` |
| **Salir** | Quita el ícono y cierra Apipos (el API deja de responder) |

## Impresora por defecto

La impresora por defecto es la que usa Apipos cuando una petición no indica
`printer`. Se elige por el API, con `POST /printers/selected` (ver
[Primeros pasos](./primeros-pasos#fija-la-impresora-por-defecto)), y se guarda
en disco en `selected_printer.pkl`:

| Sistema operativo | Carpeta |
|---|---|
| Windows | `%APPDATA%\Apipos` |
| macOS / Linux | `~/Apipos` |

Ahí mismo viven los logs de la app (`apipos.log`).

## Inicio automático

Apipos arranca solo al iniciar sesión:

| Sistema operativo | Cómo se registra |
|---|---|
| Windows | Valor `Apipos` en `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (lo crea el instalador y la app lo vuelve a registrar al arrancar) |
| macOS | LaunchAgent en `~/Library/LaunchAgents` (lo escribe la app al arrancar) |
| Linux | Entrada en `~/.config/autostart` (la crea `install.sh`) |

## Una sola instancia por usuario

Solo corre un Apipos por usuario: una segunda instancia (doble clic en el acceso
directo, inicio automático, etc.) sale en silencio sin levantar el API.

## Siguiente paso

Comprueba que el servicio responde e imprime tu primer ticket en
[Primeros pasos](./primeros-pasos).
