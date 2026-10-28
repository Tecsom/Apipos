"""Entry point: starts the Flask API in a background thread and the tray icon.

The application logic is organized in layers under ./src:
  - routes/       -> endpoint definitions
  - controllers/  -> thin try/catch wrappers that call the services
  - services/     -> business logic + standardized responses
  - utils/        -> shared helpers (response shape)

Only one tray instance runs per user: a second one exits silently without
starting Flask. The headless mode (below) has no such guard.

The log (src/app_log.py) is set up before anything else is imported, so a
missing dependency or a crash at startup still ends up in apipos.log.

Set APIPOS_NO_TRAY=1 to run the API in the foreground without the tray icon
(useful for testing, e.g. on a headless machine or while debugging).
"""
import os
import threading

from src.app_log import log, setup_logging
from src.config import FLASK_PORT

setup_logging()

try:
    from src.app import create_app
except Exception:
    # The windowed PyInstaller build may report this only in a dialog.
    log.critical('No se pudo cargar Apipos', exc_info=True)
    raise


def run_flask_app():
    app = create_app()
    log.info('Levantando el API en http://127.0.0.1:%s', FLASK_PORT)
    app.run(host='127.0.0.1', port=FLASK_PORT, use_reloader=False)


def start_background():
    """Autostart registration + Flask thread. The tray calls this only when
    this process is the single running instance (see src/tray.py)."""
    # Register the app to start on login (idempotent; no-op when run from source).
    from src.autostart import enable_autostart
    enable_autostart()

    # Start the Flask app in a daemon thread so it stops when the tray exits.
    flask_thread = threading.Thread(target=run_flask_app, name='flask', daemon=True)
    flask_thread.start()


def main():
    # Headless mode: run the API in the foreground (blocks here, stays alive).
    if os.getenv('APIPOS_NO_TRAY') == '1':
        log.info('Modo headless (sin bandeja)')
        print(f"Apipos running (headless) on http://127.0.0.1:{FLASK_PORT}")
        run_flask_app()
        return

    # Start the wxPython tray icon on the main thread (keeps the process alive).
    # It starts the API via start_background() unless Apipos is already running.
    from src.tray import start_tray
    start_tray(on_ready=start_background)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.critical('Apipos se detuvo por un error no controlado', exc_info=True)
        raise
