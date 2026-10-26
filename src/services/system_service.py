"""System / diagnostics business logic."""
import platform
import sys

from src.config import FLASK_PORT, APP_VERSION
from src.printers import get_backend
from src.services import version_service
from src.utils.response import success_response


def get_health(client_header=None):
    """Report the OS and the active printer backend (useful per installer).

    `client_header` is the raw X-Apipos-Client request header (or None); its
    comparison against APP_VERSION is reported in data['client']."""
    backend = get_backend()
    data = {
        "status": "ok",
        "version": APP_VERSION,
        "os": platform.system(),            # 'Windows' | 'Darwin' | 'Linux'
        "platform": sys.platform,           # 'win32' | 'darwin' | ...
        "backend": type(backend).__name__,  # WindowsPrinterBackend | MacPrinterBackend
        "port": FLASK_PORT,
        "client": version_service.describe_client(client_header),
    }
    return success_response(data=data, message="Service is running.")
