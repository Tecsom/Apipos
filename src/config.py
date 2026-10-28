import os
import sys


def resource_path(relative_path):
    """Get the absolute path to a resource, works for development and for PyInstaller executables."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def _read_app_meta():
    """Read app-meta.env (single source of truth) so the running app knows its
    own name/version/bundle id. Bundled as a data file by the PyInstaller specs;
    in development it is read from the project root."""
    meta = {}
    try:
        with open(resource_path('app-meta.env'), encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                meta[key.strip()] = value.strip()
    except OSError:
        pass
    return meta


_META = _read_app_meta()
APP_NAME = _META.get('APP_NAME', 'Apipos')
APP_VERSION = _META.get('APP_VERSION', '1.0.0')
APP_BUNDLE_ID = _META.get('APP_BUNDLE_ID', 'mx.tecsom.apipos')

# GitHub repo (owner/name) used by the auto-updater to look up Releases.
GITHUB_REPO = 'Tecsom/Apipos'

# AppData directory used to persist the default/selected printer.
# Falls back to the user's home directory on non-Windows platforms.
APPDATA_DIR = os.path.join(os.getenv('APPDATA') or os.path.expanduser('~'), 'Apipos')
PICKLE_FILE = os.path.join(APPDATA_DIR, 'selected_printer.pkl')

# App log (src/app_log.py). APIPOS_LOG_FILE overrides it (tests, CI smoke test).
LOG_FILE = os.getenv('APIPOS_LOG_FILE') or os.path.join(APPDATA_DIR, 'apipos.log')

TRAY_TOOLTIP = APP_NAME
TRAY_ICON = resource_path(os.path.join('assets', 'app-icon.png'))

# Bundled PDF used by the /print/test endpoint (80mm @ 300 DPI ticket).
TEST_PDF = resource_path(os.path.join('assets', 'APIPOS.pdf'))

# Bundled PDF used by the /print/test-label endpoint (2.36in x 1.18in price label).
TEST_LABEL_PDF = resource_path(os.path.join('assets', 'APIPOS_LABEL.pdf'))

FLASK_PORT = 50432
