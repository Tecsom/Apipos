"""HTTP integration tests: every endpoint through Flask's test_client (no real
server), wired to the FakeBackend; asserts status codes and the
{status, data, message} envelope."""
import base64

import pytest

from src.config import APP_VERSION
from src.services import version_service

ENVELOPE_KEYS = {"status", "data", "message"}
LINE_HEIGHT_TEXT = b"\x1b\x33\x42"
OPEN_DRAWER = b"\x1b\x70\x00\x19\xfa"
FEED_AND_CUT = b"\n\n\n\n" + b"\x1d\x56\x00"

LOAD_SELECTED = "src.services.printer_service.load_selected_printer"
SAVE_SELECTED = "src.services.printer_service.save_selected_printer"

TICKET = {
    "printer": "TestPrinter",
    "settings": {"paper_size": 58},
    "content": [
        {"type": "text", "data": "Gracias", "align": "center"},
        {"type": "separator"},
    ],
}


@pytest.fixture
def saved_printers(monkeypatch):
    """Record save_selected_printer calls instead of writing the pickle."""
    calls = []
    monkeypatch.setattr(SAVE_SELECTED, calls.append)
    return calls


@pytest.fixture(autouse=True)
def _isolate_storage(no_selected_printer, saved_printers):
    """Safety net: no request here can read or write the user's pickle."""


@pytest.fixture
def default_printer(monkeypatch):
    """Simulate 'TestPrinter' as the stored default printer (no pickle read)."""
    monkeypatch.setattr(LOAD_SELECTED, lambda: "TestPrinter")


def _json(response):
    body = response.get_json()
    assert set(body) == ENVELOPE_KEYS
    return body


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

def test_health_returns_200_with_standard_envelope(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = _json(response)
    assert body["status"] == "success"
    assert body["message"] == "Service is running."
    assert body["data"]["status"] == "ok"
    assert body["data"]["backend"] == "FakeBackend"


# ---------------------------------------------------------------------------
# Version handshake (X-Apipos-Client / X-Apipos-Version)
# ---------------------------------------------------------------------------

ORIGIN = "http://localhost:3000"


@pytest.fixture
def fresh_warned(monkeypatch):
    """Empty the client-version log registry so no state leaks between tests."""
    monkeypatch.setattr(version_service, "_warned", set())


def _header_tokens(response, name):
    return [token.strip().lower() for token in response.headers.get(name, "").split(",")]


def test_health_without_client_header_has_version_header_and_null_client(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Apipos-Version") == APP_VERSION
    assert _json(response)["data"]["client"] is None


def test_health_with_old_client_header_reports_client_older(client, fresh_warned, capsys):
    response = client.get("/health", headers={"X-Apipos-Client": "apipos-js/0.0.1"})
    assert response.status_code == 200
    info = _json(response)["data"]["client"]
    assert info["status"] == "client_older"
    assert info["name"] == "apipos-js"
    assert info["version"] == "0.0.1"
    assert info["server"] == APP_VERSION
    client.get("/health", headers={"X-Apipos-Client": "apipos-js/0.0.1"})
    assert capsys.readouterr().out == "[apipos] " + info["message"] + "\n"


def test_preflight_print_allows_client_header_and_has_version_header(client):
    response = client.options("/print", headers={
        "Origin": ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type, x-apipos-client",
    })
    assert response.status_code == 200
    assert "x-apipos-client" in _header_tokens(response, "Access-Control-Allow-Headers")
    assert response.headers.get("X-Apipos-Version") == APP_VERSION


def test_health_with_origin_exposes_version_header(client):
    response = client.get("/health", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    assert "x-apipos-version" in _header_tokens(response, "Access-Control-Expose-Headers")
    assert response.headers.get("X-Apipos-Version") == APP_VERSION


def test_error_response_also_has_version_header(client):
    response = client.post("/printers/selected", json={})
    assert response.status_code == 400
    assert _json(response)["status"] == "error"
    assert response.headers.get("X-Apipos-Version") == APP_VERSION


# ---------------------------------------------------------------------------
# Printers
# ---------------------------------------------------------------------------

def test_list_printers_returns_fake_printers(client):
    response = client.get("/printers")
    assert response.status_code == 200
    body = _json(response)
    assert body["status"] == "success"
    assert body["data"] == ["TestPrinter"]


def test_list_printers_cors_echoes_allowed_origin(client):
    origin = "http://pos.example.test"
    response = client.get("/printers", headers={"Origin": origin})
    assert response.headers.get("Access-Control-Allow-Origin") in ("*", origin)


def test_get_selected_printer_returns_stored_default(client, default_printer):
    response = client.get("/printers/selected")
    assert response.status_code == 200
    assert _json(response)["data"] == "TestPrinter"


def test_get_selected_printer_without_default_returns_null(client):
    response = client.get("/printers/selected")
    assert response.status_code == 200
    body = _json(response)
    assert body["status"] == "success"
    assert body["data"] is None


def test_set_selected_printer_without_field_returns_400(client, saved_printers):
    response = client.post("/printers/selected", json={})
    assert response.status_code == 400
    body = _json(response)
    assert body["status"] == "error"
    assert body["message"] == "Field 'printer' is required."
    assert saved_printers == []


def test_set_selected_printer_unknown_printer_returns_400_with_available(
    client, saved_printers
):
    response = client.post("/printers/selected", json={"printer": "Nope"})
    assert response.status_code == 400
    assert _json(response)["data"] == {"available": ["TestPrinter"]}
    assert saved_printers == []


def test_set_selected_printer_known_printer_returns_200_and_saves(client, saved_printers):
    response = client.post("/printers/selected", json={"printer": "TestPrinter"})
    assert response.status_code == 200
    body = _json(response)
    assert body["status"] == "success"
    assert body["data"] == "TestPrinter"
    assert saved_printers == ["TestPrinter"]


# ---------------------------------------------------------------------------
# POST /print
# ---------------------------------------------------------------------------

def test_print_unknown_printer_returns_400_with_available(client, fake_backend):
    response = client.post("/print", json={**TICKET, "printer": "Nope"})
    assert response.status_code == 400
    body = _json(response)
    assert body["status"] == "error"
    assert body["message"] == "Printer 'Nope' not found."
    assert body["data"]["available"] == ["TestPrinter"]
    assert fake_backend.raw_jobs == []


def test_print_valid_raw_job_returns_200_and_sends_one_job(client, fake_backend):
    response = client.post("/print", json=TICKET)
    assert response.status_code == 200
    body = _json(response)
    assert body["status"] == "success"
    assert body["data"] == {"printer": "TestPrinter", "char_width": 32}
    assert len(fake_backend.raw_jobs) == 1
    printer, data = fake_backend.raw_jobs[0]
    assert printer == "TestPrinter"
    assert data.endswith(FEED_AND_CUT)


def test_print_legacy_list_returns_200_on_selected_printer(
    client, fake_backend, default_printer
):
    response = client.post("/print", json=TICKET["content"])
    assert response.status_code == 200
    assert _json(response)["data"]["printer"] == "TestPrinter"
    assert [job[0] for job in fake_backend.raw_jobs] == ["TestPrinter"]


def test_print_without_printer_and_no_default_returns_400(client, fake_backend):
    response = client.post("/print", json={"content": TICKET["content"]})
    assert response.status_code == 400
    assert _json(response)["message"] == "No printer selected."
    assert fake_backend.raw_jobs == []


def test_print_label_in_driver_mode_returns_200_and_sends_document(client, fake_backend):
    pdf = b"%PDF-1.4\n% stub document for the driver path\n"
    response = client.post("/print", json={
        "printer": "TestPrinter",
        "type": "PDF",
        "settings": {"label_settings": {"width": 60, "height": 30}},
        "data": base64.b64encode(pdf).decode("ascii"),
    })
    assert response.status_code == 200
    body = _json(response)
    assert body["data"]["strategy"] == "driver"
    assert body["data"]["media"] == "Custom.60x30mm"
    assert fake_backend.pdf_jobs == [("TestPrinter", pdf, {"media_mm": (60.0, 30.0)})]


def test_print_non_json_body_returns_500(client, fake_backend):
    # documents current behavior: get_json(silent=True) yields None, the service
    # raises ValueError (instead of returning error_response) and the controller
    # maps it to a 500 rather than a 400.
    response = client.post("/print", data="not json", content_type="text/plain")
    assert response.status_code == 500
    body = _json(response)
    assert body["status"] == "error"
    assert body["message"] == "Invalid payload: expected an object or a list of items"
    assert fake_backend.raw_jobs == []


# ---------------------------------------------------------------------------
# Test prints (error paths only: they never reach the bundled assets)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/print/test", "/print/test-label"])
def test_print_test_endpoints_unknown_printer_return_400(client, fake_backend, path):
    response = client.get(path, query_string={"printer": "Nope"})
    assert response.status_code == 400
    body = _json(response)
    assert body["message"] == "Printer 'Nope' not found."
    assert body["data"]["available"] == ["TestPrinter"]
    assert fake_backend.raw_jobs == [] and fake_backend.pdf_jobs == []


@pytest.mark.parametrize("path", ["/print/test", "/print/test-label"])
def test_print_test_endpoints_without_printer_return_400(client, path):
    response = client.post(path)
    assert response.status_code == 400
    assert _json(response)["message"] == "No printer selected."


# ---------------------------------------------------------------------------
# POST /open-withdrawer
# ---------------------------------------------------------------------------

def test_open_withdrawer_known_printer_returns_200_and_sends_job(client, fake_backend):
    response = client.post("/open-withdrawer", json={"printer": "TestPrinter"})
    assert response.status_code == 200
    body = _json(response)
    assert body["status"] == "success"
    assert body["data"] == {"printer": "TestPrinter"}
    assert fake_backend.raw_jobs == [("TestPrinter", LINE_HEIGHT_TEXT + OPEN_DRAWER)]


def test_open_withdrawer_without_body_and_no_default_returns_400(client, fake_backend):
    response = client.post("/open-withdrawer")
    assert response.status_code == 400
    assert _json(response)["message"] == "No printer selected."
    assert fake_backend.raw_jobs == []


def test_open_withdrawer_unknown_printer_returns_400_with_available(client, fake_backend):
    response = client.post("/open-withdrawer", json={"printer": "Nope"})
    assert response.status_code == 400
    assert _json(response)["data"] == {"available": ["TestPrinter"]}
    assert fake_backend.raw_jobs == []


# ---------------------------------------------------------------------------
# GET /fonts (system font catalog over the isolated fake_font_dir)
# ---------------------------------------------------------------------------

def test_fonts_returns_200_with_catalog_sorted_by_family(client, fake_font_dir):
    response = client.get("/fonts")
    assert response.status_code == 200
    body = _json(response)
    assert body["status"] == "success"
    assert body["message"] == "Fonts listed."
    data = body["data"]
    assert data["families"][0]["family"] == "Test Mono"
    assert data["count"] == 2
    assert data["builtin"] == ["sans-serif", "serif", "monospace"]
    assert response.headers.get("X-Apipos-Version") == APP_VERSION


def test_fonts_refresh_returns_200_and_rescans(client, fake_font_dir):
    from tests.conftest import build_test_font
    assert _json(client.get("/fonts"))["data"]["count"] == 2
    build_test_font(str(fake_font_dir / "Zeta.ttf"), family="Zeta Serif")
    assert _json(client.get("/fonts"))["data"]["count"] == 2          # cached
    response = client.get("/fonts?refresh=1")
    assert response.status_code == 200
    data = _json(response)["data"]
    assert data["count"] == 3
    assert data["families"][-1]["family"] == "Zeta Serif"


def test_fonts_unexpected_exception_returns_500_envelope(client, monkeypatch):
    from src.services import font_service

    def boom(refresh=False):
        raise RuntimeError("scan failed")

    monkeypatch.setattr(font_service, "get_font_catalog", boom)
    response = client.get("/fonts")
    assert response.status_code == 500
    body = _json(response)
    assert body["status"] == "error"
    assert body["message"] == "scan failed"


# ---------------------------------------------------------------------------
# TASK-005: POST /print with settings.renderer "pdf" and POST /render
# ---------------------------------------------------------------------------

RENDER_CONTENT = [
    {"type": "text", "data": "HOLA", "align": "center", "font_size": "lg"},
    {"type": "special_text", "data": {"text1": "TOTAL", "text2": "$1.00"}},
]


def test_render_returns_200_with_pdf_base64_and_prints_nothing(client, fake_backend):
    response = client.post("/render", json={"settings": {"paper_size": 80},
                                            "content": RENDER_CONTENT})
    assert response.status_code == 200
    body = _json(response)
    assert body["status"] == "success"
    assert body["message"] == "Ticket rendered."
    data = body["data"]
    assert data["format"] == "pdf"
    assert data["base64"].startswith("JVBERi")
    assert data["pages"] == 1
    assert data["page_mm"]["width"] == 72
    assert response.headers.get("X-Apipos-Version") == APP_VERSION
    assert fake_backend.raw_jobs == [] and fake_backend.pdf_jobs == []


def test_render_png_returns_200_with_png_base64(client, fake_backend):
    response = client.post("/render", json={"format": "png", "content": RENDER_CONTENT})
    assert response.status_code == 200
    data = _json(response)["data"]
    assert data["dpi"] == 203
    assert base64.b64decode(data["base64"]).startswith(b"\x89PNG")


def test_render_unsupported_format_returns_400(client, fake_backend):
    response = client.post("/render", json={"format": "gif", "content": RENDER_CONTENT})
    assert response.status_code == 400
    body = _json(response)
    assert body["status"] == "error"
    assert body["message"] == "Unsupported format 'gif'. Use 'pdf' or 'png'."


def test_render_non_json_body_returns_500(client, fake_backend):
    # same contract as POST /print: the service raises, the controller maps it to a 500.
    response = client.post("/render", data="not json", content_type="text/plain")
    assert response.status_code == 500
    assert _json(response)["message"] == "Invalid payload: expected an object or a list of items"


def test_render_preflight_allows_client_header(client):
    response = client.options("/render", headers={
        "Origin": ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type, x-apipos-client",
    })
    assert response.status_code == 200
    assert "x-apipos-client" in _header_tokens(response, "Access-Control-Allow-Headers")


def test_print_with_pdf_renderer_returns_200_and_sends_raster_job(client, fake_backend):
    response = client.post("/print", json={
        "printer": "TestPrinter",
        "type": "RAW",
        "settings": {"renderer": "pdf", "paper_size": 80},
        "content": RENDER_CONTENT + [{"type": "open_withdrawer"}],
    })
    assert response.status_code == 200
    body = _json(response)
    assert body["message"] == "Rendered ticket sent as PDF."
    data = body["data"]
    assert data["renderer"] == "pdf"
    assert data["type"] == "RAW"
    assert data["strategy"] == "raw"
    assert data["width_dots"] == 576
    assert data["drawer_opened"] is True
    assert len(fake_backend.raw_jobs) == 2
    assert fake_backend.raw_jobs[0][1].endswith(FEED_AND_CUT)
    assert fake_backend.raw_jobs[1] == ("TestPrinter", OPEN_DRAWER)


def test_print_with_pdf_renderer_unknown_printer_returns_400(client, fake_backend):
    response = client.post("/print", json={"printer": "NoSuchPrinter", "type": "RAW",
                                           "settings": {"renderer": "pdf"},
                                           "content": [{"type": "text", "data": "x"}]})
    assert response.status_code == 400
    body = _json(response)
    assert body["message"] == "Printer 'NoSuchPrinter' not found."
    assert body["data"]["available"] == ["TestPrinter"]
    assert fake_backend.raw_jobs == [] and fake_backend.pdf_jobs == []


def test_print_with_unsupported_renderer_returns_400(client, fake_backend):
    response = client.post("/print", json={**TICKET, "settings": {"renderer": "svg"}})
    assert response.status_code == 400
    assert _json(response)["message"] == "Unsupported renderer 'svg'. Use 'escpos' or 'pdf'."
    assert fake_backend.raw_jobs == []
