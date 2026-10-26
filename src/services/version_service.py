"""Version handshake between Apipos and its client libraries (lockstep versioning)."""
import re

from src.config import APP_VERSION

CLIENT_HEADER = 'X-Apipos-Client'     # request:  "<name>/<major.minor.patch>"
VERSION_HEADER = 'X-Apipos-Version'   # response: APP_VERSION
_warned = set()                        # (name, version) already logged

_VERSION_RE = re.compile(r'^\s*[vV]?(\d+)(?:\.(\d+))?(?:\.(\d+))?')
_CLIENT_RE = re.compile(r'^\s*([A-Za-z0-9_.-]+)/(\d+\.\d+\.\d+)\s*$')

_MESSAGES = {
    'equal': "Client and server versions match.",
    'client_older': (
        "Client {name} {cv} is older than Apipos {sv}. "
        "Update the client library; both must share the same version."
    ),
    'client_newer': (
        "Client {name} {cv} is newer than Apipos {sv}. "
        "Update Apipos on this machine (tray menu > Buscar actualizaciones); "
        "both must share the same version."
    ),
    'unknown': (
        "Unrecognized X-Apipos-Client header: '{raw}'. "
        "Expected '<name>/<major.minor.patch>'."
    ),
}


def parse_version(text):
    """'1.2.3' / 'v1.2.3' -> (1, 2, 3). Missing parts default to 0; None/'' -> None."""
    if not text:
        return None
    match = _VERSION_RE.match(str(text))
    if not match:
        return None
    return tuple(int(part) if part is not None else 0 for part in match.groups())


def parse_client_header(value):
    """'apipos-js/1.0.6' -> ('apipos-js', '1.0.6'); anything else -> None.
    Regex: ^\\s*([A-Za-z0-9_.-]+)/(\\d+\\.\\d+\\.\\d+)\\s*$"""
    if not value:
        return None
    match = _CLIENT_RE.match(value)
    if not match:
        return None
    return match.group(1), match.group(2)


def describe_client(header_value):
    """Return the `client` dict of section 5.1 (or None when header is absent).

    An empty or whitespace-only header counts as absent (None)."""
    if header_value is None or not header_value.strip():
        return None
    server = APP_VERSION
    parsed = parse_client_header(header_value)
    if parsed is None:
        return {
            'name': None,
            'version': None,
            'server': server,
            'status': 'unknown',
            'message': _MESSAGES['unknown'].format(raw=header_value),
        }
    name, version = parsed
    cv = parse_version(version)
    sv = parse_version(server) or (0, 0, 0)
    if cv < sv:
        status = 'client_older'
    elif cv > sv:
        status = 'client_newer'
    else:
        status = 'equal'
    return {
        'name': name,
        'version': version,
        'server': server,
        'status': status,
        'message': _MESSAGES[status].format(name=name, cv=version, sv=server),
    }


def log_client_once(info):
    """print('[apipos] ' + info['message']) once per (name, version) when status != 'equal'.

    Unrecognized headers have no (name, version); they are deduplicated by their
    message, which embeds the raw header value, i.e. once per distinct raw value."""
    if not info or info.get('status') == 'equal':
        return
    if info.get('name') is None:
        key = (None, info['message'])
    else:
        key = (info['name'], info['version'])
    if key in _warned:
        return
    _warned.add(key)
    print('[apipos] ' + info['message'], flush=True)
