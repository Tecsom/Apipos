"""Unit tests for the GitHub Releases auto-updater (pure parts only)."""
import json
import urllib.error

import pytest

from src import updater

ASSETS = [
    {"name": "Apipos-2.0.2-arm64.dmg", "browser_download_url": "u1"},
    {"name": "Apipos-2.0.2-x86_64.dmg", "browser_download_url": "u2"},
    {"name": "Apipos-Setup.exe", "browser_download_url": "u3"},
    {"name": "Apipos.exe", "browser_download_url": "u4"},
    {"name": "Apipos-2.0.2-linux-x86_64.tar.gz", "browser_download_url": "u5"},
]


def _set_platform(monkeypatch, platform, machine=None):
    """Pin the OS (and CPU arch) the updater believes it runs on."""
    monkeypatch.setattr(updater.sys, "platform", platform)
    if machine is not None:
        monkeypatch.setattr(updater.platform, "machine", lambda: machine)


def _serve_release(monkeypatch, payload):
    """Make the updater 'download' `payload` as the latest-release JSON."""
    raw = json.dumps(payload).encode()
    monkeypatch.setattr(updater, "_http_get", lambda *args, **kwargs: raw)


def _fail_http(monkeypatch, code):
    """Make the updater's GitHub request fail with an HTTP status `code`."""
    def raiser(*args, **kwargs):
        raise urllib.error.HTTPError(
            updater.API_LATEST, code, "error", hdrs=None, fp=None
        )
    monkeypatch.setattr(updater, "_http_get", raiser)


# ---------------------------------------------------------------------------
# _parse_version
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("v2.0.1", (2, 0, 1)),
    ("Apipos 2.0.1", (2, 0, 1)),
    ("2.1", (2, 1, 0)),
    ("", (0, 0, 0)),
    (None, (0, 0, 0)),
])
def test_parse_version_returns_three_ints(text, expected):
    assert updater._parse_version(text) == expected


# ---------------------------------------------------------------------------
# _pick_asset
# ---------------------------------------------------------------------------

def test_pick_asset_darwin_arm64_returns_arm64_dmg(monkeypatch):
    _set_platform(monkeypatch, "darwin", "arm64")
    assert updater._pick_asset(ASSETS)["name"] == "Apipos-2.0.2-arm64.dmg"


def test_pick_asset_darwin_x86_64_returns_x86_64_dmg(monkeypatch):
    _set_platform(monkeypatch, "darwin", "x86_64")
    assert updater._pick_asset(ASSETS)["name"] == "Apipos-2.0.2-x86_64.dmg"


def test_pick_asset_darwin_without_matching_arch_returns_first_dmg(monkeypatch):
    _set_platform(monkeypatch, "darwin", "ppc64")
    assert updater._pick_asset(ASSETS)["name"] == "Apipos-2.0.2-arm64.dmg"


def test_pick_asset_win32_returns_setup_exe(monkeypatch):
    _set_platform(monkeypatch, "win32")
    # Reversed so the portable exe comes first: the "setup" name must win.
    assert updater._pick_asset(list(reversed(ASSETS)))["name"] == "Apipos-Setup.exe"


def test_pick_asset_win32_without_setup_returns_first_exe(monkeypatch):
    _set_platform(monkeypatch, "win32")
    assets = [a for a in ASSETS if a["name"] != "Apipos-Setup.exe"]
    assert updater._pick_asset(assets)["name"] == "Apipos.exe"


def test_pick_asset_linux_returns_none(monkeypatch):
    _set_platform(monkeypatch, "linux")
    assert updater._pick_asset(ASSETS) is None


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_pick_asset_empty_list_returns_none(monkeypatch, platform):
    _set_platform(monkeypatch, platform, "arm64")
    assert updater._pick_asset([]) is None


# ---------------------------------------------------------------------------
# check_for_update
# ---------------------------------------------------------------------------

def test_check_for_update_newer_tag_returns_release_info(monkeypatch):
    _set_platform(monkeypatch, "win32")
    monkeypatch.setattr(updater, "APP_VERSION", "2.0.1")
    _serve_release(monkeypatch, {
        "tag_name": "v2.0.2",
        "name": "Apipos 2.0.2",
        "body": "Fixes the update flow.",
        "assets": ASSETS,
        "html_url": "https://github.com/Tecsom/Apipos/releases/tag/v2.0.2",
    })
    assert updater.check_for_update() == {
        "version": "2.0.2",
        "tag": "v2.0.2",
        "name": "Apipos 2.0.2",
        "notes": "Fixes the update flow.",
        "asset": ASSETS[2],
        "page": "https://github.com/Tecsom/Apipos/releases/tag/v2.0.2",
    }


def test_check_for_update_sparse_release_falls_back_to_defaults(monkeypatch):
    _set_platform(monkeypatch, "win32")
    monkeypatch.setattr(updater, "APP_VERSION", "2.0.1")
    _serve_release(monkeypatch, {"tag_name": "v2.1.0"})
    info = updater.check_for_update()
    assert info["name"] == "v2.1.0"
    assert info["notes"] == ""
    assert info["asset"] is None
    assert info["page"] == updater.RELEASES_PAGE


def test_check_for_update_same_tag_returns_none(monkeypatch):
    monkeypatch.setattr(updater, "APP_VERSION", "2.0.1")
    _serve_release(monkeypatch, {"tag_name": "v2.0.1", "assets": ASSETS})
    assert updater.check_for_update() is None


def test_check_for_update_older_tag_returns_none(monkeypatch):
    monkeypatch.setattr(updater, "APP_VERSION", "2.0.1")
    _serve_release(monkeypatch, {"tag_name": "v1.9.9", "assets": ASSETS})
    assert updater.check_for_update() is None


def test_check_for_update_compares_numerically_not_lexically(monkeypatch):
    monkeypatch.setattr(updater, "APP_VERSION", "2.0.10")
    _serve_release(monkeypatch, {"tag_name": "v2.0.9", "assets": ASSETS})
    assert updater.check_for_update() is None


def test_check_for_update_http_404_returns_none(monkeypatch):
    _fail_http(monkeypatch, 404)
    assert updater.check_for_update() is None


def test_check_for_update_http_500_propagates(monkeypatch):
    _fail_http(monkeypatch, 500)
    with pytest.raises(urllib.error.HTTPError):
        updater.check_for_update()


# ---------------------------------------------------------------------------
# launch_installer
# ---------------------------------------------------------------------------

def test_launch_installer_win32_runs_startfile_and_returns_true(monkeypatch):
    calls = []
    _set_platform(monkeypatch, "win32")
    monkeypatch.setattr(updater.os, "startfile", calls.append, raising=False)
    assert updater.launch_installer(r"C:\tmp\Apipos-Setup.exe") is True
    assert calls == [r"C:\tmp\Apipos-Setup.exe"]


def test_launch_installer_darwin_opens_dmg_and_returns_true(monkeypatch):
    calls = []
    _set_platform(monkeypatch, "darwin", "arm64")
    monkeypatch.setattr("subprocess.Popen", lambda args, *a, **k: calls.append(args))
    assert updater.launch_installer("/tmp/Apipos-2.0.2-arm64.dmg") is True
    assert calls == [["open", "/tmp/Apipos-2.0.2-arm64.dmg"]]


def test_launch_installer_linux_opens_releases_page_and_returns_false(monkeypatch):
    calls = []
    _set_platform(monkeypatch, "linux")
    monkeypatch.setattr("webbrowser.open", calls.append)
    assert updater.launch_installer("/tmp/whatever") is False
    assert calls == [updater.RELEASES_PAGE]


def test_launch_installer_win32_startfile_oserror_propagates(monkeypatch):
    def declined(path):
        raise OSError("The operation was canceled by the user")
    _set_platform(monkeypatch, "win32")
    monkeypatch.setattr(updater.os, "startfile", declined, raising=False)
    with pytest.raises(OSError):
        updater.launch_installer(r"C:\tmp\Apipos-Setup.exe")
