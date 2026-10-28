"""wxPython system tray icon.

Shows the port the API is running on and the app version. Printer selection is
handled entirely through the API (`GET/POST /printers...`), so the tray only
displays status, checks for updates, and lets the user quit the app. When an
update is accepted the tray quits the app as soon as the installer is launched.
`start_tray` also guarantees a single running instance per user.
"""
import os
import threading
import webbrowser

import wx
import wx.adv

from src.config import TRAY_ICON, TRAY_TOOLTIP, FLASK_PORT, APP_NAME, APP_VERSION, APPDATA_DIR
from src import updater

HEALTH_URL = f'http://localhost:{FLASK_PORT}/health'


def create_menu_item(menu, label, func, kind=wx.ITEM_NORMAL):
    item = wx.MenuItem(menu, -1, label, kind=kind)
    menu.Bind(wx.EVT_MENU, func, id=item.GetId())
    menu.Append(item)
    return item


class TaskBarIcon(wx.adv.TaskBarIcon):
    def __init__(self, frame=None):
        super(TaskBarIcon, self).__init__()
        # Hidden anchor frame: on macOS the MainLoop exits immediately if there
        # is no top-level window to keep it running.
        self._frame = frame
        self._checking = False  # guards against overlapping update checks
        self.set_icon(TRAY_ICON)
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self.on_left_down)
        # Check for updates a few seconds after startup, quietly.
        wx.CallLater(4000, self.check_for_updates, True)

    def CreatePopupMenu(self):
        menu = wx.Menu()
        # Non-clickable status lines showing version + where the API is running.
        version_item = create_menu_item(menu, f'{APP_NAME} v{APP_VERSION}', self.on_noop)
        version_item.Enable(False)
        status_item = create_menu_item(
            menu, f'Corriendo en http://localhost:{FLASK_PORT}', self.on_noop
        )
        status_item.Enable(False)

        menu.AppendSeparator()
        create_menu_item(menu, 'Ver estado', self.on_open_health)
        create_menu_item(menu, 'Buscar actualizaciones', self.on_check_updates)
        create_menu_item(menu, 'Salir', self.on_exit)
        return menu

    def set_icon(self, path):
        # The bundled app icon is full resolution (~1254px). The macOS menu bar
        # is ~22pt tall and does NOT scale the bitmap for us, so a giant image
        # renders blank/invisible. Scale it down to menu-bar/tray size first.
        img = wx.Image(path, wx.BITMAP_TYPE_PNG)
        size = 22
        img = img.Scale(size, size, wx.IMAGE_QUALITY_HIGH)
        icon = wx.Icon(wx.Bitmap(img))
        self.SetIcon(icon, f'{TRAY_TOOLTIP} — puerto {FLASK_PORT}')

    def on_left_down(self, event):
        self.open_health()

    def on_open_health(self, event):
        self.open_health()

    def open_health(self):
        """Open the API health endpoint in the default browser."""
        webbrowser.open(HEALTH_URL)

    def on_noop(self, event):
        pass

    # --- Updates ----------------------------------------------------------- #
    def on_check_updates(self, event):
        self.check_for_updates(silent=False)

    def check_for_updates(self, silent=False):
        """Look for a newer release on GitHub. Runs the network call off the UI
        thread; `silent` suppresses the "you're up to date" / error dialogs
        (used for the automatic check at startup)."""
        if self._checking:
            return
        self._checking = True
        threading.Thread(
            target=self._check_worker, args=(silent,), daemon=True
        ).start()

    def _check_worker(self, silent):
        try:
            info = updater.check_for_update()
        except Exception as exc:  # noqa: BLE001 - report instead of crashing
            wx.CallAfter(self._on_check_done, None, str(exc), silent)
            return
        wx.CallAfter(self._on_check_done, info, None, silent)

    def _on_check_done(self, info, error, silent):
        self._checking = False
        if error is not None:
            if not silent:
                wx.MessageBox(
                    f'No se pudo verificar actualizaciones:\n{error}',
                    APP_NAME, wx.OK | wx.ICON_WARNING,
                )
            return
        if info is None:
            if not silent:
                wx.MessageBox(
                    f'{APP_NAME} está actualizado (v{APP_VERSION}).',
                    APP_NAME, wx.OK | wx.ICON_INFORMATION,
                )
            return

        notes = (info.get('notes') or '').strip()
        if len(notes) > 600:
            notes = notes[:600] + '…'
        message = f'Hay una nueva versión disponible: v{info["version"]}.\n'
        if notes:
            message += f'\nNovedades:\n{notes}\n'
        message += f'\n¿Descargar e instalar ahora?\n{APP_NAME} se cerrará para instalar la actualización.'

        if wx.MessageBox(message, APP_NAME, wx.YES_NO | wx.ICON_QUESTION) != wx.YES:
            return

        asset = info.get('asset')
        if not asset:
            # No matching installer attached to the release -> open the page.
            webbrowser.open(info['page'])
            return
        self._download_and_launch(asset)

    def _download_and_launch(self, asset):
        progress = wx.ProgressDialog(
            APP_NAME, f'Descargando {asset["name"]}…',
            maximum=100, style=wx.PD_AUTO_HIDE | wx.PD_APP_MODAL,
        )

        def worker():
            try:
                def on_progress(read, total):
                    pct = int(read * 100 / total) if total else 0
                    wx.CallAfter(progress.Update, pct)

                path = updater.download_asset(asset, progress=on_progress)
            except Exception as exc:  # noqa: BLE001
                wx.CallAfter(progress.Destroy)
                wx.CallAfter(
                    wx.MessageBox,
                    f'Falló la descarga:\n{exc}',
                    APP_NAME, wx.OK | wx.ICON_ERROR,
                )
                return
            wx.CallAfter(progress.Destroy)
            wx.CallAfter(self._installer_ready, path)

        threading.Thread(target=worker, daemon=True).start()

    def _installer_ready(self, path):
        try:
            launched = updater.launch_installer(path)
        except OSError as exc:  # e.g. the user declined the UAC prompt
            wx.MessageBox(
                f'No se pudo abrir el instalador:\n{exc}',
                APP_NAME, wx.OK | wx.ICON_ERROR,
            )
            return
        if launched:
            # The installer replaces this executable: quit now so the old
            # instance is gone before the new one starts (see TASK-007).
            self.quit_app()

    def quit_app(self):
        """Remove the tray icon and end the MainLoop (the process exits)."""
        wx.CallAfter(self.Destroy)
        # Closing the anchor frame ends the MainLoop and stops the process.
        if self._frame is not None:
            wx.CallAfter(self._frame.Close)

    def on_exit(self, event):
        self.quit_app()


def start_tray(on_ready=None):
    """Start the wxPython tray icon event loop (runs on the main thread).

    Enforces one instance per user: when another Apipos is already running
    this returns False right away without calling `on_ready`. Otherwise
    `on_ready()` (if given) runs before the icon appears and the loop starts.
    """
    app = wx.App(False)
    os.makedirs(APPDATA_DIR, exist_ok=True)  # lock file dir on macOS/Linux
    # Kept as an attribute so it outlives MainLoop: while the checker exists,
    # IsAnotherRunning() in other processes returns True.
    app.single_instance = wx.SingleInstanceChecker(
        f'{APP_NAME}-{wx.GetUserId()}.lock', APPDATA_DIR
    )
    if app.single_instance.IsAnotherRunning():
        print(f'{APP_NAME} ya está corriendo; esta instancia se cierra.')
        return False
    if on_ready is not None:
        on_ready()
    # Created but never Show()n -> invisible window that keeps MainLoop alive.
    frame = wx.Frame(None, title=TRAY_TOOLTIP)
    TaskBarIcon(frame)
    app.MainLoop()
    return True
