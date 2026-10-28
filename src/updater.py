"""Auto-updater backed by GitHub Releases.

The repo (Tecsom/Apipos) is public, so no auth token is required. This module
uses only the standard library (urllib) to avoid adding dependencies to the
bundle.

Flow:
  1. check_for_update()  -> queries the latest release and compares versions.
  2. download_asset()    -> downloads the matching installer to a temp file.
  3. launch_installer()  -> opens it (mounts the .dmg on macOS / runs the
                            Setup.exe on Windows) and the app quits; on
                            Windows the Setup also closes any instance still
                            running. Signed/notarized installers keep working.
"""
import json
import os
import platform
import re
import ssl
import sys
import tempfile
import urllib.error
import urllib.request

from src.config import APP_VERSION, GITHUB_REPO

API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
_TIMEOUT = 20
_USER_AGENT = 'Apipos-Updater'


def _parse_version(text):
    """'v1.2.3' / 'Apipos 1.2.3' -> (1, 2, 3). Missing parts default to 0."""
    nums = [int(n) for n in re.findall(r'\d+', text or '')[:3]]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def _http_get(url, accept='application/vnd.github+json'):
    req = urllib.request.Request(
        url, headers={'User-Agent': _USER_AGENT, 'Accept': accept}
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx) as resp:
        return resp.read()


def _pick_asset(assets):
    """Choose the installer asset that matches the current platform/arch."""
    if sys.platform == 'darwin':
        arch = platform.machine()  # 'arm64' | 'x86_64'
        dmgs = [a for a in assets if a.get('name', '').lower().endswith('.dmg')]
        # Prefer an arch-specific build; fall back to any dmg (e.g. universal2).
        for a in dmgs:
            if arch in a['name']:
                return a
        return dmgs[0] if dmgs else None
    if sys.platform == 'win32':
        exes = [a for a in assets if a.get('name', '').lower().endswith('.exe')]
        # Prefer the installer ("Setup") over a portable exe if both exist.
        for a in exes:
            if 'setup' in a['name'].lower():
                return a
        return exes[0] if exes else None
    return None


def check_for_update():
    """Return a dict describing an available update, or None if up to date.

    Returned dict: {version, tag, name, notes, asset, page}.
    Raises on network/parse errors so the caller can report them.
    """
    try:
        raw = _http_get(API_LATEST)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None  # repo has no published releases yet
        raise
    data = json.loads(raw)
    tag = data.get('tag_name') or data.get('name') or ''
    if _parse_version(tag) <= _parse_version(APP_VERSION):
        return None
    return {
        'version': tag.lstrip('vV'),
        'tag': tag,
        'name': data.get('name') or tag,
        'notes': data.get('body') or '',
        'asset': _pick_asset(data.get('assets') or []),
        'page': data.get('html_url') or RELEASES_PAGE,
    }


def download_asset(asset, progress=None):
    """Download a release asset to a temp file and return its path.

    `progress`, if given, is called as progress(bytes_read, total_bytes).
    """
    url = asset['browser_download_url']
    dest = os.path.join(tempfile.gettempdir(), asset['name'])
    req = urllib.request.Request(url, headers={'User-Agent': _USER_AGENT})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx) as resp, \
            open(dest, 'wb') as out:
        total = int(resp.headers.get('Content-Length') or 0)
        read = 0
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            out.write(chunk)
            read += len(chunk)
            if progress:
                progress(read, total)
    return dest


def launch_installer(path):
    """Open the downloaded installer; return True when one was launched.

    Returns False when the platform has no installer flow (the releases page
    is opened instead). On True the caller is expected to quit the app: the
    installer replaces this executable, and on Windows it also closes any
    instance still running (see installer-windows.iss), so that exactly one
    Apipos is left after the update.
    """
    if sys.platform == 'darwin':
        import subprocess
        subprocess.Popen(['open', path])     # mounts the .dmg
        return True
    if sys.platform == 'win32':
        os.startfile(path)                   # runs the Setup.exe  # noqa: S606
        return True
    import webbrowser
    webbrowser.open(RELEASES_PAGE)
    return False
