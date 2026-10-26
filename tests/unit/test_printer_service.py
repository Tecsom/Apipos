"""Unit tests for printer_service: payload parsing, settings helpers, job routing
and the exact jobs each print path hands to the (fake) printer backend."""
import base64
import io

import pytest
from PIL import Image

import src.printers
from src.services import printer_service as svc
from tests.conftest import FakeBackend

# Literal oracle bytes (deliberately not imported from production code).
LINE_HEIGHT_TEXT = b"\x1b\x33\x42"
LINE_HEIGHT_IMAGE = b"\x1b\x33\x00"
FULL_CUT = b"\x1d\x56\x00"
FEED_AND_CUT = b"\n\n\n\n" + FULL_CUT
OPEN_DRAWER = b"\x1b\x70\x00\x19\xfa"
GS_V_0 = b"\x1d\x76\x30\x00"

LOAD_SELECTED = "src.services.printer_service.load_selected_printer"
SAVE_SELECTED = "src.services.printer_service.save_selected_printer"

TICKET_ITEMS = [
    {"type": "text", "data": "TIENDA ñandú", "align": "center"},
    {"type": "special_text", "data": {"text1": "TOTAL", "text2": "$20.00"}},
    {"type": "table", "data": {"rows": [[2, "Taco", "10.00", "20.00"]]}},
    {"type": "separator"},
]

# The driver path never parses the PDF: only the "%PDF" magic is checked.
STUB_PDF = b"%PDF-1.4\n% stub document for the driver path\n"


# ---------------------------------------------------------------------------
# Isolation and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def saved_printers(monkeypatch):
    """Record save_selected_printer calls instead of writing the pickle."""
    calls = []
    monkeypatch.setattr(SAVE_SELECTED, calls.append)
    return calls


@pytest.fixture(autouse=True)
def _isolate_io(fake_backend, no_selected_printer, saved_printers):
    """Safety net: no test here can reach a real printer or the user's pickle."""


@pytest.fixture
def default_printer(monkeypatch):
    """Simulate 'TestPrinter' as the stored default printer (no pickle read)."""
    monkeypatch.setattr(LOAD_SELECTED, lambda: "TestPrinter")


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def _png_b64(width=8, height=2, color=0):
    """Small synthetic PNG (black by default) as a base64 string."""
    buf = io.BytesIO()
    Image.new("L", (width, height), color).save(buf, format="PNG")
    return _b64(buf.getvalue())


def _real_pdf_bytes():
    """A real one-page PDF built in memory (needed by the rasterizing path)."""
    fitz = pytest.importorskip("fitz", reason="PyMuPDF is required to build a real PDF")
    doc = fitz.open()
    doc.new_page(width=200, height=100)
    try:
        return doc.tobytes()
    finally:
        doc.close()


def _raw_ticket(items, settings=None):
    payload = {"printer": "TestPrinter", "content": items}
    if settings is not None:
        payload["settings"] = settings
    return svc.print_job(payload)


def _pdf_job(data, settings=None, job_type="PDF"):
    payload = {"printer": "TestPrinter", "type": job_type, "data": data}
    if settings is not None:
        payload["settings"] = settings
    return svc.print_job(payload)


# ---------------------------------------------------------------------------
# _parse_print_payload
# ---------------------------------------------------------------------------

class TestParsePrintPayload:
    def test_parse_print_payload_full_dict_returns_tuple(self, monkeypatch):
        # An explicit printer must not consult the stored default.
        monkeypatch.setattr(LOAD_SELECTED, lambda: pytest.fail("default printer was read"))
        items = [{"type": "separator"}]
        payload = {
            "printer": "P1",
            "type": "PDF",
            "settings": {"pdf_mode": "driver"},
            "content": items,
            "data": "QUJD",
        }
        assert svc._parse_print_payload(payload) == (
            "P1", "PDF", {"pdf_mode": "driver"}, items, "QUJD",
        )

    def test_parse_print_payload_lowercase_type_is_uppercased(self):
        assert svc._parse_print_payload({"printer": "P1", "type": "pdf"})[1] == "PDF"
        assert svc._parse_print_payload({"printer": "P1", "type": "raw"})[1] == "RAW"

    def test_parse_print_payload_minimal_dict_applies_defaults(self):
        assert svc._parse_print_payload({"printer": "P1"}) == ("P1", "RAW", {}, [], None)

    def test_parse_print_payload_aliases_printer_name_and_items(self):
        items = [{"type": "text", "data": "x"}]
        assert svc._parse_print_payload({"printer_name": "P2", "items": items}) == (
            "P2", "RAW", {}, items, None,
        )

    def test_parse_print_payload_legacy_list_uses_selected_printer(self, default_printer):
        items = [{"type": "text", "data": "x"}]
        assert svc._parse_print_payload(items) == ("TestPrinter", "RAW", {}, items, None)

    def test_parse_print_payload_dict_without_printer_falls_back_to_selected(
        self, default_printer
    ):
        assert svc._parse_print_payload({"content": []})[0] == "TestPrinter"

    def test_parse_print_payload_without_printer_and_no_default_returns_none(self):
        assert svc._parse_print_payload([{"type": "separator"}])[0] is None

    @pytest.mark.parametrize("payload", ["not a payload", None, 42])
    def test_parse_print_payload_invalid_payload_raises_value_error(self, payload):
        with pytest.raises(ValueError) as exc:
            svc._parse_print_payload(payload)
        assert str(exc.value) == "Invalid payload: expected an object or a list of items"


# ---------------------------------------------------------------------------
# _truthy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value", [True, "true", 1, "1", "sí", "si", "on", "yes", " TRUE ", "Yes"]
)
def test_truthy_accepted_values_return_true(value):
    assert svc._truthy(value) is True


@pytest.mark.parametrize("value", [None, False, "no", 0, "0", "false", "off", ""])
def test_truthy_other_values_return_false(value):
    assert svc._truthy(value) is False


# ---------------------------------------------------------------------------
# _resolve_char_width
# ---------------------------------------------------------------------------

class TestResolveCharWidth:
    def test_resolve_char_width_char_width_wins_over_paper_size(self):
        assert svc._resolve_char_width("TestPrinter", {"char_width": 42, "paper_size": 80}) == 42

    @pytest.mark.parametrize(
        "settings, expected",
        [
            ({"paper_size": 80}, 48),
            ({"paper_size": 58}, 32),
            ({"paper_size": "80"}, 48),
            ({"paper_size_mm": 58}, 32),
        ],
    )
    def test_resolve_char_width_paper_size_maps_to_columns(self, settings, expected):
        assert svc._resolve_char_width("TestPrinter", settings) == expected

    def test_resolve_char_width_without_settings_queries_backend(self, monkeypatch):
        monkeypatch.setattr(src.printers, "_backend", FakeBackend(width=32))
        assert svc._resolve_char_width("TestPrinter", {}) == 32
        assert svc._resolve_char_width("TestPrinter", None) == 32


# ---------------------------------------------------------------------------
# _pdf_width_dots
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "settings, expected",
    [
        ({"width_dots": 512, "char_width": 48, "paper_size": 80}, 512),
        ({"char_width": 48, "paper_size": 58}, 576),
        ({"char_width": 32, "paper_size": 80}, 384),
        ({"paper_size": 80}, 576),
        ({"paper_size": 58}, 384),
        ({"paper_size_mm": 58}, 384),
        ({}, 576),
        (None, 576),
    ],
)
def test_pdf_width_dots_priority_resolves_expected_dots(settings, expected):
    assert svc._pdf_width_dots(settings) == expected


# ---------------------------------------------------------------------------
# _parse_label_size
# ---------------------------------------------------------------------------

class TestParseLabelSize:
    def test_parse_label_size_mm_default_unit_returns_mm_and_dots(self):
        assert svc._parse_label_size({"width": 60, "height": 30}) == {
            "width_mm": 60.0,
            "height_mm": 30.0,
            "width_dots": 480,
        }

    @pytest.mark.parametrize("unit", ["inch", "in", "inches", '"', "INCH"])
    def test_parse_label_size_inch_converts_to_mm(self, unit):
        label = svc._parse_label_size({"width": 2.36, "height": 1.18, "unit": unit})
        assert label["width_mm"] == pytest.approx(59.944)
        assert label["height_mm"] == pytest.approx(29.972)
        assert label["width_dots"] == 480  # round(59.944 * 8)

    def test_parse_label_size_without_height_returns_none_height(self):
        assert svc._parse_label_size({"width": 60})["height_mm"] is None

    @pytest.mark.parametrize("raw", [{"height": 30}, {"width": "abc", "height": 30}])
    def test_parse_label_size_missing_or_non_numeric_width_raises(self, raw):
        with pytest.raises(ValueError) as exc:
            svc._parse_label_size(raw)
        assert str(exc.value) == "label_settings requires a numeric 'width'."

    def test_parse_label_size_unsupported_unit_raises_lowercased_unit(self):
        with pytest.raises(ValueError) as exc:
            svc._parse_label_size({"width": 60, "height": 30, "unit": "CM"})
        assert str(exc.value) == "Unsupported unit 'cm'. Use 'mm' or 'inch'."

    @pytest.mark.parametrize("raw", [None, {}])
    def test_parse_label_size_empty_returns_none(self, raw):
        assert svc._parse_label_size(raw) is None


# ---------------------------------------------------------------------------
# print_job: routing and validation errors
# ---------------------------------------------------------------------------

class TestPrintJobErrors:
    def test_print_job_unknown_printer_returns_available_list(self, fake_backend):
        result = svc.print_job({"printer": "Nope", "content": TICKET_ITEMS})
        assert result == {
            "status": "error",
            "data": {"available": ["TestPrinter"]},
            "message": "Printer 'Nope' not found.",
        }
        assert fake_backend.raw_jobs == [] and fake_backend.pdf_jobs == []

    @pytest.mark.parametrize("payload", [{"content": TICKET_ITEMS}, TICKET_ITEMS])
    def test_print_job_no_printer_and_no_default_returns_error(self, fake_backend, payload):
        result = svc.print_job(payload)
        assert result == {"status": "error", "data": None, "message": "No printer selected."}
        assert fake_backend.raw_jobs == []

    def test_print_job_unsupported_type_returns_exact_message(self, fake_backend):
        result = svc.print_job({"printer": "TestPrinter", "type": "zpl", "content": TICKET_ITEMS})
        assert result["status"] == "error"
        assert result["message"] == "Unsupported job type 'ZPL'. Use 'RAW' or 'PDF'."
        assert fake_backend.raw_jobs == [] and fake_backend.pdf_jobs == []

    @pytest.mark.parametrize("payload", [{"printer": "TestPrinter"},
                                         {"printer": "TestPrinter", "content": []}])
    def test_print_job_raw_without_content_returns_error(self, fake_backend, payload):
        result = svc.print_job(payload)
        assert result == {"status": "error", "data": None, "message": "No content to print."}
        assert fake_backend.raw_jobs == []

    def test_print_job_invalid_payload_raises_value_error(self, fake_backend):
        # documents current behavior: the service RAISES instead of returning an
        # error_response (ARCHITECTURE.md §2.3); the controller turns it into a 500.
        with pytest.raises(ValueError):
            svc.print_job("not a payload")
        assert fake_backend.raw_jobs == []


# ---------------------------------------------------------------------------
# _print_raw_job (through print_job)
# ---------------------------------------------------------------------------

class TestPrintRawJob:
    def test_print_raw_job_multiple_items_send_exactly_one_job(self, fake_backend):
        result = _raw_ticket(TICKET_ITEMS)
        assert result["status"] == "success"
        assert result["message"] == "Print job completed."
        assert len(fake_backend.raw_jobs) == 1
        printer, data = fake_backend.raw_jobs[0]
        assert printer == "TestPrinter"
        assert data.startswith(LINE_HEIGHT_TEXT)
        assert "TIENDA ñandú".encode("latin1") in data
        assert b"TOTAL" in data and b"Taco" in data
        assert fake_backend.pdf_jobs == []

    def test_print_raw_job_stream_ends_with_single_feed_and_cut(self, fake_backend):
        _raw_ticket(TICKET_ITEMS)
        data = fake_backend.raw_jobs[0][1]
        assert data.endswith(FEED_AND_CUT)
        assert data.count(FULL_CUT) == 1
        assert OPEN_DRAWER not in data

    def test_print_raw_job_open_withdrawer_appends_drawer_after_cut(self, fake_backend):
        # Even when the item comes first, the drawer opens at the very end.
        _raw_ticket([{"type": "open_withdrawer"}] + TICKET_ITEMS)
        assert len(fake_backend.raw_jobs) == 1
        data = fake_backend.raw_jobs[0][1]
        assert data.endswith(FEED_AND_CUT + OPEN_DRAWER)
        assert data.count(OPEN_DRAWER) == 1

    def test_print_raw_job_unknown_item_types_are_ignored(self, fake_backend):
        unknown = [{"type": "barcode", "data": "123"}, {"data": "item without type"}]
        known_result = _raw_ticket(TICKET_ITEMS)
        mixed_result = _raw_ticket(TICKET_ITEMS[:2] + unknown + TICKET_ITEMS[2:])
        assert known_result["status"] == mixed_result["status"] == "success"
        assert len(fake_backend.raw_jobs) == 2
        assert fake_backend.raw_jobs[1][1] == fake_backend.raw_jobs[0][1]

    @pytest.mark.parametrize(
        "settings, expected_width",
        [({"paper_size": 58}, 32), ({"char_width": 42}, 42), ({"paper_size": 80}, 48), ({}, 48)],
    )
    def test_print_raw_job_char_width_reflects_settings(
        self, fake_backend, settings, expected_width
    ):
        result = _raw_ticket([{"type": "separator"}], settings)
        assert result["data"] == {"printer": "TestPrinter", "char_width": expected_width}
        data = fake_backend.raw_jobs[0][1]
        assert b"-" * expected_width + b"\n" in data
        assert b"-" * (expected_width + 1) not in data

    def test_print_raw_job_without_settings_uses_backend_width(self, monkeypatch):
        backend = FakeBackend(width=32)
        monkeypatch.setattr(src.printers, "_backend", backend)
        result = _raw_ticket([{"type": "separator"}])
        assert result["data"]["char_width"] == 32
        assert len(backend.raw_jobs) == 1

    def test_print_job_legacy_list_prints_on_selected_printer(
        self, fake_backend, default_printer
    ):
        result = svc.print_job(TICKET_ITEMS)
        assert result["status"] == "success"
        assert result["data"]["printer"] == "TestPrinter"
        assert [job[0] for job in fake_backend.raw_jobs] == ["TestPrinter"]

    def test_print_job_aliases_printer_name_and_items_print(self, fake_backend):
        result = svc.print_job({"printer_name": "TestPrinter", "items": TICKET_ITEMS})
        assert result["status"] == "success"
        assert len(fake_backend.raw_jobs) == 1


class TestPrintRawImage:
    def test_print_raw_job_image_emits_gs_v_0_in_single_job(self, fake_backend):
        result = _raw_ticket([{"type": "image", "data": _png_b64(), "width": 16},
                              {"type": "text", "data": "after"}])
        assert result["status"] == "success"
        assert len(fake_backend.raw_jobs) == 1
        data = fake_backend.raw_jobs[0][1]
        assert data.count(GS_V_0) == 1
        assert LINE_HEIGHT_IMAGE in data
        assert data.index(GS_V_0) < data.index(b"after")
        assert data.endswith(FEED_AND_CUT)

    @pytest.mark.parametrize("value", [0, -5, "x"])
    def test_print_raw_job_invalid_max_band_bytes_returns_error(self, fake_backend, value):
        result = _raw_ticket([{"type": "image", "data": _png_b64()}], {"max_band_bytes": value})
        assert result == {
            "status": "error",
            "data": None,
            "message": "'max_band_bytes' must be a positive integer.",
        }
        assert fake_backend.raw_jobs == []

    def test_print_raw_job_undecodable_image_returns_error_and_sends_nothing(
        self, fake_backend
    ):
        result = _raw_ticket(TICKET_ITEMS + [{"type": "image", "data": _b64(b"not an image")}])
        assert result["message"] == "Error converting image to black and white."
        assert fake_backend.raw_jobs == []


# ---------------------------------------------------------------------------
# PDF jobs
# ---------------------------------------------------------------------------

class TestPrintPdfJob:
    def test_pdf_job_without_data_returns_error(self, fake_backend):
        result = _pdf_job(None)
        assert result["message"] == "No PDF data provided. Send the PDF as base64 in 'data'."
        assert fake_backend.pdf_jobs == [] and fake_backend.raw_jobs == []

    def test_pdf_job_invalid_base64_returns_error(self, fake_backend):
        result = _pdf_job("abc")  # binascii.Error: incorrect padding
        assert result == {"status": "error", "data": None, "message": "Invalid base64 PDF data."}
        assert fake_backend.pdf_jobs == [] and fake_backend.raw_jobs == []

    def test_pdf_job_non_alphabet_base64_reports_not_a_pdf(self, fake_backend):
        # documents current behavior: b64decode() is non-strict and silently
        # drops non-alphabet characters, so "%%%" decodes to b"" and is reported
        # as "not a valid PDF" instead of "Invalid base64 PDF data.".
        result = _pdf_job("%%%")
        assert result["message"] == "Provided data is not a valid PDF."
        assert fake_backend.pdf_jobs == [] and fake_backend.raw_jobs == []

    def test_pdf_job_valid_base64_not_pdf_returns_error(self, fake_backend):
        result = _pdf_job(_b64(b"hello, this is not a pdf"))
        assert result == {
            "status": "error", "data": None, "message": "Provided data is not a valid PDF.",
        }
        assert fake_backend.pdf_jobs == [] and fake_backend.raw_jobs == []

    def test_pdf_job_data_uri_prefix_is_accepted(self, fake_backend):
        data_uri = "data:application/pdf;base64," + _b64(STUB_PDF)
        result = _pdf_job(data_uri, {"pdf_mode": "driver"})
        assert result["status"] == "success"
        assert len(fake_backend.pdf_jobs) == 1
        assert fake_backend.pdf_jobs[0][1] == STUB_PDF

    def test_pdf_job_driver_label_sends_custom_media(self, fake_backend):
        result = _pdf_job(_b64(STUB_PDF), {"label_settings": {"width": 60, "height": 30}},
                          job_type="pdf")
        assert result["status"] == "success"
        assert result["message"] == "PDF sent to the printer driver."
        assert result["data"] == {
            "printer": "TestPrinter",
            "type": "PDF",
            "strategy": "driver",
            "media": "Custom.60x30mm",
        }
        assert len(fake_backend.pdf_jobs) == 1
        printer, pdf_bytes, options = fake_backend.pdf_jobs[0]
        assert printer == "TestPrinter"
        assert pdf_bytes == STUB_PDF
        assert options["media_mm"] == (60.0, 30.0)
        assert fake_backend.raw_jobs == []

    def test_pdf_job_driver_label_in_inches_converts_media(self, fake_backend):
        settings = {"label_settings": {"width": 2.36, "height": 1.18, "unit": "inch"}}
        result = _pdf_job(_b64(STUB_PDF), settings)
        assert result["data"]["strategy"] == "driver"
        width_mm, height_mm = fake_backend.pdf_jobs[0][2]["media_mm"]
        assert width_mm == pytest.approx(59.944)
        assert height_mm == pytest.approx(29.972)

    def test_pdf_job_driver_without_label_sends_no_options(self, fake_backend):
        result = _pdf_job(_b64(STUB_PDF), {"pdf_mode": "document"})
        assert result["data"]["strategy"] == "driver"
        assert result["data"]["media"] is None
        assert fake_backend.pdf_jobs == [("TestPrinter", STUB_PDF, None)]

    def test_pdf_job_unsupported_pdf_mode_returns_error(self, fake_backend):
        result = _pdf_job(_b64(STUB_PDF), {"pdf_mode": "zzz"})
        assert result == {
            "status": "error",
            "data": None,
            "message": "Unsupported pdf_mode 'zzz'. Use 'driver' or 'raw'.",
        }
        assert fake_backend.pdf_jobs == [] and fake_backend.raw_jobs == []

    def test_pdf_job_invalid_label_unit_returns_error(self, fake_backend):
        settings = {"label_settings": {"width": 60, "height": 30, "unit": "cm"}}
        result = _pdf_job(_b64(STUB_PDF), settings)
        assert result["message"] == "Unsupported unit 'cm'. Use 'mm' or 'inch'."
        assert fake_backend.pdf_jobs == [] and fake_backend.raw_jobs == []

    def test_pdf_job_raw_mode_rasterizes_and_cuts(self, fake_backend):
        result = _pdf_job(_b64(_real_pdf_bytes()))  # no label -> raw by default
        assert result["status"] == "success"
        assert result["data"] == {
            "printer": "TestPrinter",
            "type": "PDF",
            "strategy": "raw",
            "width_dots": 576,
            "cut": True,
        }
        assert fake_backend.pdf_jobs == []
        assert len(fake_backend.raw_jobs) == 1
        printer, data = fake_backend.raw_jobs[0]
        assert printer == "TestPrinter"
        assert data.startswith(LINE_HEIGHT_IMAGE)
        assert GS_V_0 in data
        assert data.endswith(FEED_AND_CUT)

    def test_pdf_job_raw_label_uses_label_width_and_no_cut(self, fake_backend):
        settings = {"pdf_mode": "raster", "label_settings": {"width": 60, "height": 30}}
        result = _pdf_job(_b64(_real_pdf_bytes()), settings)
        assert result["data"]["strategy"] == "raw"
        assert result["data"]["width_dots"] == 480
        assert result["data"]["cut"] is False
        data = fake_backend.raw_jobs[0][1]
        assert not data.endswith(FULL_CUT)
        assert FEED_AND_CUT not in data


# ---------------------------------------------------------------------------
# open_drawer / set_selected_printer / get_printers / get_selected_printer
# ---------------------------------------------------------------------------

class TestOpenDrawer:
    def test_open_drawer_explicit_printer_sends_drawer_command(self, fake_backend):
        result = svc.open_drawer({"printer": "TestPrinter"})
        assert result == {
            "status": "success",
            "data": {"printer": "TestPrinter"},
            "message": "Cash drawer opened.",
        }
        # send_to_printer prepends the text line height and encodes as latin1.
        assert fake_backend.raw_jobs == [("TestPrinter", LINE_HEIGHT_TEXT + OPEN_DRAWER)]

    def test_open_drawer_without_printer_uses_selected_default(
        self, fake_backend, default_printer
    ):
        result = svc.open_drawer(None)
        assert result["status"] == "success"
        assert [job[0] for job in fake_backend.raw_jobs] == ["TestPrinter"]

    def test_open_drawer_unknown_printer_returns_available_list(self, fake_backend):
        result = svc.open_drawer({"printer": "Nope"})
        assert result == {
            "status": "error",
            "data": {"available": ["TestPrinter"]},
            "message": "Printer 'Nope' not found.",
        }
        assert fake_backend.raw_jobs == []

    @pytest.mark.parametrize("payload", [None, {}])
    def test_open_drawer_no_printer_and_no_default_returns_error(self, fake_backend, payload):
        result = svc.open_drawer(payload)
        assert result == {"status": "error", "data": None, "message": "No printer selected."}
        assert fake_backend.raw_jobs == []


class TestSelectedPrinter:
    @pytest.mark.parametrize("payload", [{}, None, {"printer": ""}])
    def test_set_selected_printer_missing_field_returns_error(self, saved_printers, payload):
        result = svc.set_selected_printer(payload)
        assert result == {
            "status": "error", "data": None, "message": "Field 'printer' is required.",
        }
        assert saved_printers == []

    def test_set_selected_printer_unknown_printer_does_not_save(self, saved_printers):
        result = svc.set_selected_printer({"printer": "Nope"})
        assert result == {
            "status": "error",
            "data": {"available": ["TestPrinter"]},
            "message": "Printer 'Nope' not found.",
        }
        assert saved_printers == []

    @pytest.mark.parametrize("key", ["printer", "printer_name"])
    def test_set_selected_printer_known_printer_saves_it(self, saved_printers, key):
        result = svc.set_selected_printer({key: "TestPrinter"})
        assert result == {
            "status": "success",
            "data": "TestPrinter",
            "message": "Selected printer updated.",
        }
        assert saved_printers == ["TestPrinter"]

    def test_get_selected_printer_returns_stored_default(self, default_printer):
        assert svc.get_selected_printer() == {
            "status": "success", "data": "TestPrinter", "message": "",
        }

    def test_get_selected_printer_without_default_returns_none(self):
        assert svc.get_selected_printer()["data"] is None


class TestGetPrinters:
    def test_get_printers_returns_backend_printers(self):
        assert svc.get_printers() == {
            "status": "success", "data": ["TestPrinter"], "message": "Printers listed.",
        }

    def test_get_printers_reflects_custom_backend(self, monkeypatch):
        monkeypatch.setattr(src.printers, "_backend", FakeBackend(printers=["A", "B"]))
        assert svc.get_printers()["data"] == ["A", "B"]


# ---------------------------------------------------------------------------
# TASK-005: spacer on the ESC/POS path
# ---------------------------------------------------------------------------

class TestSpacerLines:
    @pytest.mark.parametrize(
        "item, expected",
        [
            ({"lines": 3}, 3),
            ({"lines": "2"}, 2),
            ({"lines": 2.7}, 2),
            ({"lines": 0}, 1),
            ({"lines": -4}, 1),
            ({"lines": 2, "height_mm": 40}, 2),        # lines wins over height_mm
            ({"height_mm": 8}, 2),
            ({"height_mm": 12}, 3),
            ({"height_mm": "16"}, 4),
            ({"height_mm": 1}, 1),                     # round(0.25) = 0 -> minimum 1
            ({"lines": None, "height_mm": 8}, 2),      # null lines = absent
            ({}, 1),
        ],
    )
    def test_spacer_lines_resolves_lines_then_height_mm(self, item, expected):
        assert svc._spacer_lines({"type": "spacer", **item}) == expected

    @pytest.mark.parametrize(
        "item",
        [{"lines": "abc"}, {"lines": [2]}, {"lines": float("nan")}, {"lines": float("inf")},
         {"height_mm": "x"}, {"height_mm": float("nan")}, {"height_mm": float("inf")},
         {"lines": "abc", "height_mm": 40}],
    )
    def test_spacer_lines_garbage_returns_one(self, item):
        assert svc._spacer_lines({"type": "spacer", **item}) == 1

    @pytest.mark.parametrize("item", [{"lines": 10**9}, {"height_mm": 10**6},
                                      {"lines": 51}, {"height_mm": 204}])
    def test_spacer_lines_huge_values_are_capped_at_50(self, item):
        assert svc._spacer_lines({"type": "spacer", **item}) == 50

    def test_spacer_lines_cap_is_inclusive(self):
        assert svc._spacer_lines({"type": "spacer", "lines": 50}) == 50
        assert svc._spacer_lines({"type": "spacer", "height_mm": 200}) == 50


class TestEscposSpacerAndIgnoredFields:
    def test_print_raw_job_spacer_inserts_newlines_between_items(self, fake_backend):
        text_a, text_b = {"type": "text", "data": "A"}, {"type": "text", "data": "B"}
        _raw_ticket([text_a, text_b])
        _raw_ticket([text_a, {"type": "spacer", "lines": 2}, text_b])
        without, with_spacer = fake_backend.raw_jobs[0][1], fake_backend.raw_jobs[1][1]
        cut = without.index(b"\n") + 1            # right after the line of "A"
        assert with_spacer == without[:cut] + b"\n\n" + without[cut:]

    def test_print_raw_job_spacer_height_mm_uses_four_mm_per_line(self, fake_backend):
        _raw_ticket([{"type": "spacer", "height_mm": 12}])
        assert fake_backend.raw_jobs[0][1] == LINE_HEIGHT_TEXT + b"\n" * 3 + FEED_AND_CUT

    def test_print_raw_job_huge_spacer_is_capped_and_prints_one_job(self, fake_backend):
        # A web page can POST this to localhost: it must not exhaust memory.
        result = _raw_ticket([{"type": "spacer", "lines": 10**9}])
        assert result["status"] == "success"
        assert len(fake_backend.raw_jobs) == 1
        assert fake_backend.raw_jobs[0][1] == LINE_HEIGHT_TEXT + b"\n" * 50 + FEED_AND_CUT

    @pytest.mark.parametrize("item_type", ["text", "special_text"])
    def test_print_raw_job_numeric_font_size_prints_as_normal(self, fake_backend, item_type):
        data = "HOLA" if item_type == "text" else {"text1": "TOTAL", "text2": "$1.00"}
        _raw_ticket([{"type": item_type, "data": data, "font_size": "normal"}])
        _raw_ticket([{"type": item_type, "data": data, "font_size": 14}])
        assert fake_backend.raw_jobs[1][1] == fake_backend.raw_jobs[0][1]

    def test_print_raw_job_pdf_only_fields_are_ignored_byte_identical(self, fake_backend):
        image = _png_b64(width=16, height=4)
        plain = [
            {"type": "image", "data": image, "width": 16},
            {"type": "text", "data": "TIENDA", "align": "center", "font_weight": "bold"},
            {"type": "special_text", "data": {"text1": "TOTAL", "text2": "$1.00"}},
            {"type": "table", "data": {"rows": [[1, "Pan", "1.00", "1.00"]]}},
            {"type": "separator"},
        ]
        extended = [
            {**plain[0], "width_mm": 30, "align": "right"},
            {**plain[1], "font_family": "Arial", "font_style": "italic", "underline": True,
             "line_height": 2},
            {**plain[2], "font_family": "Courier New", "font_style": "italic",
             "underline": "yes", "line_height": 1.5},
            {"type": "table", "font_family": "Arial", "font_style": "italic", "line_height": 1.4,
             "data": {"rows": plain[3]["data"]["rows"],
                      "columns": [{"label": "Qty", "width": 50, "align": "right"},
                                  {"label": "Item", "width": 50}]}},
            {"type": "separator", "style": "double", "thickness": 2},
            {"type": "html", "data": "<p><b>solo PDF</b></p>"},
        ]
        assert _raw_ticket(plain)["status"] == _raw_ticket(extended)["status"] == "success"
        assert len(fake_backend.raw_jobs) == 2
        assert fake_backend.raw_jobs[1][1] == fake_backend.raw_jobs[0][1]


# ---------------------------------------------------------------------------
# TASK-005: settings.renderer routing
# ---------------------------------------------------------------------------

SIMPLE_TICKET = [
    {"type": "text", "data": "HOLA", "align": "center"},
    {"type": "special_text", "data": {"text1": "TOTAL", "text2": "$1.00"}},
]


class TestRendererRouting:
    @pytest.mark.parametrize("settings", [{}, {"renderer": "escpos"}, {"renderer": " ESCPOS "},
                                          {"renderer": None}, {"renderer": ""}])
    def test_print_job_escpos_renderer_keeps_escpos_path(self, fake_backend, settings):
        reference = _raw_ticket(TICKET_ITEMS)
        result = _raw_ticket(TICKET_ITEMS, settings)
        assert result == reference
        assert result["message"] == "Print job completed."
        assert len(fake_backend.raw_jobs) == 2
        assert fake_backend.raw_jobs[1][1] == fake_backend.raw_jobs[0][1]

    def test_print_job_renderer_is_normalized_strip_lower(self, fake_backend):
        result = _raw_ticket(SIMPLE_TICKET, {"renderer": " PDF "})
        assert result["status"] == "success"
        assert result["data"]["renderer"] == "pdf"

    def test_print_job_unsupported_renderer_returns_exact_error(self, fake_backend):
        result = _raw_ticket(SIMPLE_TICKET, {"renderer": " X "})
        assert result == {"status": "error", "data": None,
                          "message": "Unsupported renderer 'x'. Use 'escpos' or 'pdf'."}
        assert fake_backend.raw_jobs == [] and fake_backend.pdf_jobs == []

    def test_print_job_renderer_ignored_for_pdf_jobs(self, fake_backend):
        result = _pdf_job(_b64(STUB_PDF), {"pdf_mode": "driver", "renderer": "x"})
        assert result["status"] == "success"
        assert result["data"]["type"] == "PDF"
        assert "renderer" not in result["data"]

    def test_print_job_renderer_pdf_unknown_printer_fails_before_rendering(
        self, fake_backend, monkeypatch
    ):
        monkeypatch.setattr(svc.pdf_renderer, "render_ticket_pdf",
                            lambda *a, **k: pytest.fail("rendered before validating the printer"))
        result = svc.print_job({"printer": "Nope", "settings": {"renderer": "pdf"},
                                "content": SIMPLE_TICKET})
        assert result == {"status": "error", "data": {"available": ["TestPrinter"]},
                          "message": "Printer 'Nope' not found."}
        assert fake_backend.raw_jobs == [] and fake_backend.pdf_jobs == []


# ---------------------------------------------------------------------------
# TASK-005: _render_options (normalized renderer options)
# ---------------------------------------------------------------------------

class TestRenderOptions:
    def test_render_options_defaults(self):
        expected = {
            "width_mm": 72.0,
            "margins_mm": {"top": 1.0, "right": 1.0, "bottom": 3.0, "left": 1.0},
            "font": {"family": "sans-serif", "size": 9.0, "line_height": 1.25},
            "max_height_mm": 1000.0,
            "max_image_height_dots": 600,
        }
        assert svc._render_options({}) == expected
        assert svc._render_options(None) == expected

    @pytest.mark.parametrize(
        "settings, expected",
        [
            ({"width_mm": 50, "label_settings": {"width": 60}, "width_dots": 512,
              "paper_size": 58, "char_width": 32}, 50.0),
            ({"label_settings": {"width": 60, "height": 30}, "width_dots": 512,
              "paper_size": 58}, 60.0),
            ({"label_settings": {"width": 2, "unit": "inch"}}, 50.8),
            ({"width_dots": 512, "paper_size": 58, "char_width": 32}, 64.0),
            ({"paper_size": 58, "char_width": 48}, 48.0),
            ({"paper_size": 80, "char_width": 32}, 72.0),
            ({"paper_size": "80"}, 72.0),
            ({"paper_size_mm": 58}, 48.0),
            ({"char_width": 32}, 48.0),
            ({"char_width": 48}, 72.0),
            ({"width_mm": "abc", "width_dots": 0, "paper_size": None}, 72.0),
            ({}, 72.0),
        ],
    )
    def test_render_options_page_width_first_rule_wins(self, settings, expected):
        assert svc._render_options(settings)["width_mm"] == pytest.approx(expected)

    @pytest.mark.parametrize(
        "label, message",
        [({"width": 60, "unit": "cm"}, "Unsupported unit 'cm'. Use 'mm' or 'inch'."),
         ({"height": 30}, "label_settings requires a numeric 'width'.")],
    )
    def test_render_options_invalid_label_settings_raise_existing_message(self, label, message):
        with pytest.raises(ValueError) as exc:
            svc._render_options({"label_settings": label})
        assert str(exc.value) == message

    @pytest.mark.parametrize("size", [3, 73, 100, "abc", "", True, float("nan")])
    def test_render_options_invalid_font_size_raises_exact_message(self, size):
        with pytest.raises(ValueError) as exc:
            svc._render_options({"font": {"size": size}})
        assert str(exc.value) == "'font.size' must be a number between 4 and 72."

    def test_render_options_font_family_size_and_line_height(self):
        font = svc._render_options({"font": {"family": "  Arial ", "size": "12",
                                             "line_height": 2}})["font"]
        assert font == {"family": "Arial", "size": 12.0, "line_height": 2.0}

    @pytest.mark.parametrize("line_height", [0.5, 3.5, "x", True, None])
    def test_render_options_invalid_line_height_falls_back_silently(self, line_height):
        assert svc._render_options({"font": {"line_height": line_height}})["font"][
            "line_height"] == 1.25

    def test_render_options_margins_fall_back_per_key(self):
        margins = svc._render_options({"margins_mm": {"top": 2, "right": "x", "bottom": -1}})[
            "margins_mm"]
        assert margins == {"top": 2.0, "right": 1.0, "bottom": 3.0, "left": 1.0}
        assert svc._render_options({"margins_mm": "bad"})["margins_mm"] == {
            "top": 1.0, "right": 1.0, "bottom": 3.0, "left": 1.0}

    @pytest.mark.parametrize("raw, expected", [(500, 500.0), ("250", 250.0), (-3, 1000.0),
                                               ("x", 1000.0), (0, 1000.0)])
    def test_render_options_max_height_mm(self, raw, expected):
        assert svc._render_options({"max_height_mm": raw})["max_height_mm"] == expected

    def test_render_options_max_image_height_dots(self):
        assert svc._render_options({"max_image_height_dots": 300})["max_image_height_dots"] == 300
        with pytest.raises(ValueError) as exc:
            svc._render_options({"max_image_height_dots": "x"})
        assert str(exc.value) == "'max_image_height_dots' must be a positive integer."


# ---------------------------------------------------------------------------
# TASK-005: renderer "pdf" through print_job (FakeBackend)
# ---------------------------------------------------------------------------

def _pdf_ticket(items, **settings):
    return _raw_ticket(items, {"renderer": "pdf", **settings})


class TestRenderedPdfJob:
    def test_rendered_pdf_raw_mode_sends_one_raster_job(self, fake_backend):
        result = _pdf_ticket(SIMPLE_TICKET)
        assert result["status"] == "success"
        assert result["message"] == "Rendered ticket sent as PDF."
        data = result["data"]
        assert data["printer"] == "TestPrinter"
        assert data["type"] == "RAW"
        assert data["renderer"] == "pdf"
        assert data["strategy"] == "raw"
        assert data["width_dots"] == 576
        assert data["cut"] is True
        assert data["page_mm"]["width"] == 72
        assert data["page_mm"]["height"] > 0
        assert data["drawer_opened"] is False
        assert data["warnings"] == []
        assert data["fonts"] == [{"family": "sans-serif", "resolved": data["fonts"][0]["resolved"],
                                  "source": "builtin", "bold": False, "italic": False}]
        assert fake_backend.pdf_jobs == []
        assert len(fake_backend.raw_jobs) == 1
        printer, job = fake_backend.raw_jobs[0]
        assert printer == "TestPrinter"
        assert job.startswith(LINE_HEIGHT_IMAGE)       # raster from pdf_to_escpos
        assert GS_V_0 in job
        assert job.endswith(FEED_AND_CUT)

    def test_rendered_pdf_paper_size_58_uses_384_dots(self, fake_backend):
        data = _pdf_ticket(SIMPLE_TICKET, paper_size=58)["data"]
        assert data["width_dots"] == 384
        assert data["page_mm"]["width"] == 48

    def test_rendered_pdf_explicit_width_dots_is_kept(self, fake_backend):
        data = _pdf_ticket(SIMPLE_TICKET, width_dots=512)["data"]
        assert data["width_dots"] == 512
        assert data["page_mm"]["width"] == 64     # rule 3: width_dots / 8

    def test_rendered_pdf_raw_label_keeps_label_rules(self, fake_backend):
        data = _pdf_ticket(SIMPLE_TICKET, pdf_mode="raster",
                           label_settings={"width": 60, "height": 30})["data"]
        assert data["strategy"] == "raw"
        assert data["page_mm"]["width"] == 60
        assert data["width_dots"] == 480
        assert data["cut"] is False               # labels do not cut by default
        assert not fake_backend.raw_jobs[0][1].endswith(FULL_CUT)

    def test_rendered_pdf_driver_mode_media_is_exact_page_size(self, fake_backend):
        result = _pdf_ticket(SIMPLE_TICKET, pdf_mode="driver")
        assert result["status"] == "success"
        data = result["data"]
        assert data["strategy"] == "driver"
        assert data["type"] == "RAW"
        assert data["renderer"] == "pdf"
        assert "width_dots" not in data and "cut" not in data
        height = data["page_mm"]["height"]
        assert data["media"].startswith("Custom.72x")
        assert data["media"] == f"Custom.72x{height:g}mm"
        assert fake_backend.raw_jobs == []
        assert len(fake_backend.pdf_jobs) == 1
        printer, pdf_bytes, options = fake_backend.pdf_jobs[0]
        assert printer == "TestPrinter"
        assert pdf_bytes.startswith(b"%PDF")
        assert options["media_mm"] == (72, height)

    def test_rendered_pdf_label_settings_default_to_driver(self, fake_backend):
        data = _pdf_ticket(SIMPLE_TICKET, label_settings={"width": 60, "height": 30})["data"]
        assert data["strategy"] == "driver"
        assert data["page_mm"]["width"] == 60
        assert fake_backend.pdf_jobs[0][2]["media_mm"] == (60, data["page_mm"]["height"])

    def test_rendered_pdf_open_withdrawer_sends_drawer_as_second_raw_job(self, fake_backend):
        result = _pdf_ticket(SIMPLE_TICKET + [{"type": "open_withdrawer"}])
        assert result["data"]["drawer_opened"] is True
        assert len(fake_backend.raw_jobs) == 2
        assert fake_backend.raw_jobs[0][1].endswith(FEED_AND_CUT)
        assert fake_backend.raw_jobs[1] == ("TestPrinter", OPEN_DRAWER)

    def test_rendered_pdf_driver_open_withdrawer_sends_drawer_pulse(self, fake_backend):
        result = _pdf_ticket([{"type": "open_withdrawer"}] + SIMPLE_TICKET, pdf_mode="document")
        assert result["data"]["drawer_opened"] is True
        assert len(fake_backend.pdf_jobs) == 1
        assert fake_backend.raw_jobs == [("TestPrinter", OPEN_DRAWER)]

    @pytest.mark.parametrize("payload", [{"printer": "TestPrinter", "settings": {"renderer": "pdf"}},
                                         {"printer": "TestPrinter", "settings": {"renderer": "pdf"},
                                          "content": []}])
    def test_rendered_pdf_without_content_returns_error(self, fake_backend, payload):
        assert svc.print_job(payload) == {"status": "error", "data": None,
                                          "message": "No content to print."}
        assert fake_backend.raw_jobs == [] and fake_backend.pdf_jobs == []

    @pytest.mark.parametrize("size", [100, "abc"])
    def test_rendered_pdf_invalid_font_size_returns_exact_error(self, fake_backend, size):
        result = _pdf_ticket(SIMPLE_TICKET, font={"size": size})
        assert result == {"status": "error", "data": None,
                          "message": "'font.size' must be a number between 4 and 72."}
        assert fake_backend.raw_jobs == [] and fake_backend.pdf_jobs == []

    @pytest.mark.parametrize(
        "settings, message",
        [({"label_settings": {"width": 60, "height": 30, "unit": "cm"}},
          "Unsupported unit 'cm'. Use 'mm' or 'inch'."),
         ({"label_settings": {"height": 30}}, "label_settings requires a numeric 'width'."),
         ({"width_mm": 60, "label_settings": {"width": 60, "height": "x"}},
          "label_settings 'height' must be a number.")],
    )
    def test_rendered_pdf_invalid_label_settings_returns_existing_message(
        self, fake_backend, settings, message
    ):
        result = _pdf_ticket(SIMPLE_TICKET, **settings)
        assert result == {"status": "error", "data": None, "message": message}
        assert fake_backend.raw_jobs == [] and fake_backend.pdf_jobs == []

    def test_rendered_pdf_unsupported_pdf_mode_returns_existing_error(self, fake_backend):
        result = _pdf_ticket(SIMPLE_TICKET, pdf_mode="zzz")
        assert result == {"status": "error", "data": None,
                          "message": "Unsupported pdf_mode 'zzz'. Use 'driver' or 'raw'."}
        assert fake_backend.raw_jobs == [] and fake_backend.pdf_jobs == []

    def test_rendered_pdf_renderer_errors_become_error_responses(self, fake_backend):
        bad_image = _pdf_ticket([{"type": "text", "data": "x"},
                                 {"type": "image", "data": _b64(b"not an image")}])
        assert bad_image["message"] == "Invalid image data in item 1."
        too_tall = _pdf_ticket([{"type": "spacer", "height_mm": 30}], max_height_mm=20)
        assert too_tall["status"] == "error"
        assert too_tall["message"] == "Rendered ticket is too tall (34.0 mm > 20 mm)."
        assert fake_backend.raw_jobs == [] and fake_backend.pdf_jobs == []

    def test_rendered_pdf_invalid_max_image_height_returns_existing_error(self, fake_backend):
        result = _pdf_ticket(SIMPLE_TICKET, max_image_height_dots=0)
        assert result["message"] == "'max_image_height_dots' must be a positive integer."
        assert fake_backend.raw_jobs == []


# ---------------------------------------------------------------------------
# TASK-005: render_job (POST /render: preview, never prints)
# ---------------------------------------------------------------------------

class _NoPrinterBackend:
    """Any backend access fails the test: render_job must never touch printers."""

    def __getattr__(self, name):
        pytest.fail(f"render_job touched the printer backend ({name})")


@pytest.fixture
def no_backend(monkeypatch):
    monkeypatch.setattr(src.printers, "_backend", _NoPrinterBackend())


def _png_size(png):
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


class TestRenderJob:
    def test_render_job_default_format_returns_pdf_base64(self, no_backend):
        result = svc.render_job({"content": SIMPLE_TICKET})
        assert result["status"] == "success"
        assert result["message"] == "Ticket rendered."
        data = result["data"]
        assert set(data) == {"format", "dpi", "base64", "page_mm", "pages", "fonts", "warnings"}
        assert data["format"] == "pdf"
        assert data["dpi"] is None
        assert data["pages"] == 1
        assert data["page_mm"]["width"] == 72
        assert isinstance(data["base64"], str)
        assert data["base64"].startswith("JVBERi")
        assert base64.b64decode(data["base64"]).startswith(b"%PDF")

    def test_render_job_png_returns_png_at_default_203_dpi(self, no_backend):
        data = svc.render_job({"format": " PNG ", "content": SIMPLE_TICKET})["data"]
        assert data["format"] == "png"
        assert data["dpi"] == 203
        png = base64.b64decode(data["base64"])
        assert png.startswith(b"\x89PNG")
        assert abs(_png_size(png)[0] - 576) <= 2      # 72 mm at 203 DPI

    @pytest.mark.parametrize("dpi", [300, "300", " 300 ", 300.0])
    def test_render_job_png_accepts_integer_dpi(self, no_backend, dpi):
        data = svc.render_job({"format": "png", "dpi": dpi, "content": SIMPLE_TICKET})["data"]
        assert data["dpi"] == 300
        assert abs(_png_size(base64.b64decode(data["base64"]))[0] - 850) <= 2

    @pytest.mark.parametrize("dpi", [10, 71, 601, "abc", "", "300.5", 203.5, True, [203]])
    def test_render_job_invalid_dpi_returns_exact_error(self, no_backend, dpi):
        result = svc.render_job({"format": "png", "dpi": dpi, "content": SIMPLE_TICKET})
        assert result == {"status": "error", "data": None,
                          "message": "'dpi' must be an integer between 72 and 600."}

    def test_render_job_dpi_is_ignored_for_pdf(self, no_backend):
        data = svc.render_job({"format": "pdf", "dpi": 10, "content": SIMPLE_TICKET})["data"]
        assert data["format"] == "pdf" and data["dpi"] is None

    @pytest.mark.parametrize("fmt, shown", [("gif", "gif"), (" JPG ", "jpg")])
    def test_render_job_unsupported_format_returns_exact_error(self, no_backend, fmt, shown):
        result = svc.render_job({"format": fmt, "content": SIMPLE_TICKET})
        assert result == {"status": "error", "data": None,
                          "message": f"Unsupported format '{shown}'. Use 'pdf' or 'png'."}

    def test_render_job_legacy_list_renders_with_default_settings(self, no_backend):
        data = svc.render_job(SIMPLE_TICKET)["data"]
        assert data["format"] == "pdf"
        assert data["page_mm"]["width"] == 72
        assert base64.b64decode(data["base64"]).startswith(b"%PDF")

    def test_render_job_ignores_printer_and_type(self, no_backend):
        result = svc.render_job({"printer": "Nope", "type": "PDF",
                                 "settings": {"paper_size": 58}, "content": SIMPLE_TICKET})
        assert result["status"] == "success"
        assert result["data"]["page_mm"]["width"] == 48

    @pytest.mark.parametrize("payload", [{}, {"content": []}, [], {"format": "png"}])
    def test_render_job_without_content_returns_error(self, no_backend, payload):
        assert svc.render_job(payload) == {"status": "error", "data": None,
                                           "message": "No content to print."}

    def test_render_job_renderer_errors_use_print_messages(self, no_backend):
        font = svc.render_job({"settings": {"font": {"size": 100}}, "content": SIMPLE_TICKET})
        assert font["message"] == "'font.size' must be a number between 4 and 72."
        label = svc.render_job({"settings": {"label_settings": {"width": 60, "unit": "cm"}},
                                "content": SIMPLE_TICKET})
        assert label["message"] == "Unsupported unit 'cm'. Use 'mm' or 'inch'."
        image = svc.render_job({"content": [{"type": "image", "data": _b64(b"nope")}]})
        assert image["message"] == "Invalid image data in item 0."

    def test_render_job_open_withdrawer_does_not_print(self, no_backend):
        result = svc.render_job({"content": SIMPLE_TICKET + [{"type": "open_withdrawer"}]})
        assert result["status"] == "success"
        assert "drawer_opened" not in result["data"]

    def test_render_job_invalid_payload_raises_value_error(self, no_backend):
        # same contract as print_job: the controller maps it to a 500.
        with pytest.raises(ValueError):
            svc.render_job(None)
