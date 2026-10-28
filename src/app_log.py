"""File log for the app: apipos.log next to the app data (APPDATA_DIR).

The packaged app has no console (on Windows the PyInstaller build is windowed,
so sys.stdout / sys.stderr are None): without this module every print,
thread traceback and startup error is lost. `setup_logging()` runs first
thing in apipos.py and sends to LOG_FILE:

  - logging records (`from src.app_log import log`),
  - everything written to sys.stdout / sys.stderr (prints, and the tracebacks
    Python, threading and wx write there), still echoed to the console when
    there is one,
  - native crashes (faulthandler).

  Windows:      %APPDATA%\\Apipos\\apipos.log
  macOS/Linux:  ~/Apipos/apipos.log
  Override:     APIPOS_LOG_FILE=/path/to/file.log

Best-effort and idempotent: if the file cannot be opened the app still starts.
"""
import atexit
import faulthandler
import io
import logging
import os
import platform
import subprocess
import sys

from src.config import APP_NAME, APP_VERSION, LOG_FILE

LOG_MAX_BYTES = 1_000_000  # bigger at startup -> renamed to apipos.log.1
_FORMAT = '%(asctime)s %(levelname)s [%(process)d %(threadName)s] %(name)s: %(message)s'

log = logging.getLogger('apipos')
_configured = False
_crash_file = None  # kept open: faulthandler writes native crashes here


class _LogStream(io.TextIOBase):
    """Stand-in for sys.stdout / sys.stderr: logs each line and echoes the
    text to the original stream (None in the windowed build)."""

    def __init__(self, logger, level, echo):
        super().__init__()
        self._logger = logger
        self._level = level
        self._echo = echo
        self._pending = ''

    @property
    def encoding(self):
        return 'utf-8'

    def writable(self):
        return True

    def write(self, text):
        if self._echo is not None:
            try:
                self._echo.write(text)
            except Exception:  # noqa: BLE001 - a broken console must not break the app
                pass
        self._pending += text
        while '\n' in self._pending:
            line, self._pending = self._pending.split('\n', 1)
            if line.strip():
                self._logger.log(self._level, line.rstrip())
        return len(text)

    def flush(self):
        if self._echo is not None:
            try:
                self._echo.flush()
            except Exception:  # noqa: BLE001
                pass


def _rotate(path):
    """Start a fresh log when the current one is too big. Renaming a file that
    another instance has open fails on Windows; then the old one is kept."""
    try:
        if os.path.getsize(path) > LOG_MAX_BYTES:
            os.replace(path, path + '.1')
    except OSError:
        pass


def setup_logging():
    """Send logging, stdout/stderr and native crashes to LOG_FILE.

    Returns the log path, or None when it could not be opened (the app keeps
    running without a file log). Calling it again does nothing.
    """
    global _configured, _crash_file
    if _configured:
        return LOG_FILE
    _configured = True
    logging.raiseExceptions = False  # a logging failure must never crash the app

    formatter = logging.Formatter(_FORMAT)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if sys.stderr is not None:  # a terminal: development or headless runs
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        root.addHandler(console)
    # One line per HTTP request is noise; startup and errors are logged by us.
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        _rotate(LOG_FILE)
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        _crash_file = open(LOG_FILE, 'a', encoding='utf-8')
    except OSError as exc:
        log.warning('No se pudo abrir el log %s: %s', LOG_FILE, exc)
        return None
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Prints and tracebacks: own loggers that only write to the file (the
    # echo already shows them on the console, if any).
    for name, level in (('stdout', logging.INFO), ('stderr', logging.WARNING)):
        stream_logger = logging.getLogger(name)
        stream_logger.propagate = False
        stream_logger.addHandler(file_handler)
        setattr(sys, name, _LogStream(stream_logger, level, getattr(sys, name)))

    faulthandler.enable(file=_crash_file)
    atexit.register(lambda: log.info('%s terminó (pid %s)', APP_NAME, os.getpid()))
    log.info('%s %s iniciando · exe=%s · frozen=%s · pid=%s · %s · Python %s',
             APP_NAME, APP_VERSION, sys.executable, getattr(sys, 'frozen', False),
             os.getpid(), platform.platform(), platform.python_version())
    return LOG_FILE


def open_log_folder():
    """Open the folder that holds apipos.log in the OS file manager."""
    folder = os.path.dirname(LOG_FILE)
    os.makedirs(folder, exist_ok=True)
    if sys.platform == 'win32':
        os.startfile(folder)  # noqa: S606
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', folder])
    else:
        subprocess.Popen(['xdg-open', folder])
