"""Unit tests for the version handshake (X-Apipos-Client / X-Apipos-Version)."""
import pytest

from src.services import version_service

SERVER = "1.0.6"
CLIENT_KEYS = {"name", "version", "server", "status", "message"}


@pytest.fixture
def server_version(monkeypatch):
    """Pin the server version so the tests do not depend on app-meta.env."""
    monkeypatch.setattr(version_service, "APP_VERSION", SERVER)
    return SERVER


@pytest.fixture
def fresh_warned(monkeypatch):
    """Empty dedupe registry per test (no state leaks between tests)."""
    warned = set()
    monkeypatch.setattr(version_service, "_warned", warned)
    return warned


# ---------------------------------------------------------------------------
# parse_version
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("1.2.3", (1, 2, 3)),
    ("v1.2.3", (1, 2, 3)),
    ("v1.2", (1, 2, 0)),
    ("7", (7, 0, 0)),
])
def test_parse_version_valid_text_returns_tuple(text, expected):
    assert version_service.parse_version(text) == expected


@pytest.mark.parametrize("text", [None, "", "abc"])
def test_parse_version_missing_or_invalid_returns_none(text):
    assert version_service.parse_version(text) is None


# ---------------------------------------------------------------------------
# parse_client_header
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["apipos-js/1.0.6", "  apipos-js/1.0.6  "])
def test_parse_client_header_valid_returns_name_and_version(value):
    assert version_service.parse_client_header(value) == ("apipos-js", "1.0.6")


@pytest.mark.parametrize("value", [
    "apipos-js", "apipos-js/1.0", "a b/1.0.0", "apipos-js/v1.0.6", "", None,
])
def test_parse_client_header_invalid_returns_none(value):
    assert version_service.parse_client_header(value) is None


# ---------------------------------------------------------------------------
# describe_client
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("header", [None, "", "   "])
def test_describe_client_without_header_returns_none(server_version, header):
    assert version_service.describe_client(header) is None


def test_describe_client_same_version_returns_equal(server_version):
    info = version_service.describe_client("apipos-js/1.0.6")
    assert set(info) == CLIENT_KEYS
    assert info == {
        "name": "apipos-js",
        "version": "1.0.6",
        "server": "1.0.6",
        "status": "equal",
        "message": "Client and server versions match.",
    }


def test_describe_client_older_version_returns_client_older(server_version):
    info = version_service.describe_client("apipos-js/1.0.5")
    assert info == {
        "name": "apipos-js",
        "version": "1.0.5",
        "server": "1.0.6",
        "status": "client_older",
        "message": "Client apipos-js 1.0.5 is older than Apipos 1.0.6. "
                   "Update the client library; both must share the same version.",
    }


def test_describe_client_newer_version_returns_client_newer(server_version):
    info = version_service.describe_client("apipos-js/1.10.0")
    assert info == {
        "name": "apipos-js",
        "version": "1.10.0",
        "server": "1.0.6",
        "status": "client_newer",
        "message": "Client apipos-js 1.10.0 is newer than Apipos 1.0.6. "
                   "Update Apipos on this machine (tray menu > Buscar actualizaciones); "
                   "both must share the same version.",
    }


def test_describe_client_unparseable_header_returns_unknown(server_version):
    info = version_service.describe_client("apipos-js")
    assert info == {
        "name": None,
        "version": None,
        "server": "1.0.6",
        "status": "unknown",
        "message": "Unrecognized X-Apipos-Client header: 'apipos-js'. "
                   "Expected '<name>/<major.minor.patch>'.",
    }


def test_describe_client_compares_numerically_not_lexically(server_version, monkeypatch):
    monkeypatch.setattr(version_service, "APP_VERSION", "1.0.10")
    assert version_service.describe_client("apipos-js/1.0.9")["status"] == "client_older"


# ---------------------------------------------------------------------------
# log_client_once
# ---------------------------------------------------------------------------

def test_log_client_once_prints_once_per_name_and_version(
    server_version, fresh_warned, capsys
):
    info = version_service.describe_client("apipos-js/1.0.5")
    version_service.log_client_once(info)
    version_service.log_client_once(info)
    version_service.log_client_once(version_service.describe_client("apipos-js/1.0.5"))
    out = capsys.readouterr().out
    assert out == "[apipos] " + info["message"] + "\n"


def test_log_client_once_distinct_versions_print_each(server_version, fresh_warned, capsys):
    version_service.log_client_once(version_service.describe_client("apipos-js/1.0.5"))
    version_service.log_client_once(version_service.describe_client("apipos-js/1.0.7"))
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("[apipos] Client apipos-js 1.0.5 is older")
    assert lines[1].startswith("[apipos] Client apipos-js 1.0.7 is newer")


def test_log_client_once_equal_status_prints_nothing(server_version, fresh_warned, capsys):
    version_service.log_client_once(version_service.describe_client("apipos-js/1.0.6"))
    assert capsys.readouterr().out == ""
    assert fresh_warned == set()


def test_log_client_once_unknown_deduplicates_by_raw_value(
    server_version, fresh_warned, capsys
):
    for raw in ("apipos-js", "apipos-js", "other/1.0"):
        version_service.log_client_once(version_service.describe_client(raw))
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "[apipos] Unrecognized X-Apipos-Client header: 'apipos-js'. "
        "Expected '<name>/<major.minor.patch>'.",
        "[apipos] Unrecognized X-Apipos-Client header: 'other/1.0'. "
        "Expected '<name>/<major.minor.patch>'.",
    ]
