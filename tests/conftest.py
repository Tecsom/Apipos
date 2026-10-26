"""Shared fixtures: fake printer backend and storage isolation."""
import pytest

import src.printers
from src.printers.base import PrinterBackend


class FakeBackend(PrinterBackend):
    """In-memory PrinterBackend: records every job instead of printing."""
    native_pdf = True

    def __init__(self, printers=None, width=48):
        self.printers = printers if printers is not None else ["TestPrinter"]
        self.width = width
        self.raw_jobs = []   # list of (printer_name, bytes)
        self.pdf_jobs = []   # list of (printer_name, bytes, options)

    def list_printers(self):
        return list(self.printers)

    def get_printer_width(self, printer_name):
        return self.width

    def send_raw(self, printer_name, data):
        self.raw_jobs.append((printer_name, bytes(data)))

    def print_pdf(self, printer_name, pdf_bytes, options=None):
        self.pdf_jobs.append((printer_name, bytes(pdf_bytes), options))


@pytest.fixture
def fake_backend(monkeypatch):
    """Replace the platform backend singleton with an in-memory fake."""
    backend = FakeBackend()
    monkeypatch.setattr(src.printers, "_backend", backend)
    return backend


@pytest.fixture
def no_selected_printer(monkeypatch):
    """Simulate 'no default printer configured' without touching the pickle."""
    monkeypatch.setattr(
        "src.services.printer_service.load_selected_printer", lambda: None
    )


@pytest.fixture
def client(fake_backend):
    """Flask test client wired to the fake backend (no real server)."""
    from src.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# System fonts (TASK-005 Etapa 2): license-free test fonts + isolated font dir
# ---------------------------------------------------------------------------

def build_test_font(path, family="Test Sans", style="Regular", bold=False, italic=False, advance=600):
    """Write a minimal, license-free TTF: box glyphs for A-Z a-z 0-9 and a space.
    Fixed advance (600/1000 em) makes text widths exact in tests: at 10 pt each
    glyph is 6 pt wide and a space is 3 pt."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    names = [".notdef", "space"] + [chr(c) for c in range(0x41, 0x5B)] + [chr(c) for c in range(0x61, 0x7B)] + [str(i) for i in range(10)]
    cmap = {0x20: "space"}
    cmap.update({c: chr(c) for c in range(0x41, 0x5B)})
    cmap.update({c: chr(c) for c in range(0x61, 0x7B)})
    cmap.update({0x30 + i: str(i) for i in range(10)})

    def box():
        pen = TTGlyphPen(None)
        pen.moveTo((50, 0)); pen.lineTo((50, 700)); pen.lineTo((550, 700)); pen.lineTo((550, 0)); pen.closePath()
        return pen.glyph()

    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf({n: (TTGlyphPen(None).glyph() if n == "space" else box()) for n in names})
    fb.setupHorizontalMetrics({n: ((300 if n == "space" else advance), 50) for n in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": style})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200,
                usWeightClass=700 if bold else 400,
                fsSelection=(0x20 if bold else 0x40) | (1 if italic else 0))
    fb.setupPost(isFixedPitch=1)
    fb.font["head"].macStyle = (1 if bold else 0) | (2 if italic else 0)
    fb.save(path)


@pytest.fixture
def fake_font_dir(tmp_path, monkeypatch):
    """A temp font directory with 'Test Sans' Regular + Bold and a TTC with two faces of 'Test Mono';
    font_service is pointed at it and its cache is cleared."""
    from fontTools.ttLib import TTCollection, TTFont
    import src.services.font_service as font_service

    d = tmp_path / "fonts"; d.mkdir()
    build_test_font(str(d / "TestSans-Regular.ttf"))
    build_test_font(str(d / "TestSans-Bold.ttf"), style="Bold", bold=True)
    build_test_font(str(d / "_a.ttf"), family="Test Mono", style="Regular")
    build_test_font(str(d / "_b.ttf"), family="Test Mono", style="Italic", italic=True)
    col = TTCollection(); col.fonts = [TTFont(str(d / "_a.ttf")), TTFont(str(d / "_b.ttf"))]
    col.save(str(d / "TestMono.ttc")); (d / "_a.ttf").unlink(); (d / "_b.ttf").unlink()
    (d / "not-a-font.ttf").write_bytes(b"garbage")

    monkeypatch.setattr(font_service, "font_dirs", lambda: [str(d)])
    monkeypatch.setattr(font_service, "_cache", None)
    return d
