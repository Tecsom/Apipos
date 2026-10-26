"""ticket_pdf_renderer: the PDF layout engine, asserted on the PDF it produces
(page size, span positions/fonts/colors, drawings, images, warnings, errors).

Fonts are the `fake_font_dir` faces ('Test Sans' Regular/Bold TTFs and a
'Test Mono' TTC with Regular + Italic, all with a fixed 600/1000 em advance and
a 300/1000 em space) plus PyMuPDF's Base-14 builtins. Strings rendered with the
test fonts only use A-Z a-z 0-9 and space (their only glyphs); accents and
symbols use 'sans-serif'.
"""
import base64
import io
import re

import fitz
import pytest
from fontTools.ttLib import TTCollection, TTFont
from PIL import Image

from src.services import ticket_pdf_renderer as r

MM = 72.0 / 25.4
PAGE_W = 72 * MM                 # default width_mm
LEFT = RIGHT = 1 * MM            # default side margins
AVAIL = PAGE_W - LEFT - RIGHT
PAD = r.CELL_PADDING_MM * MM     # table cell padding
BASE_LH = 9 * 1.25               # default font size × line height (pt)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_options(**overrides):
    """Normalized options of section 6.4.1 with `overrides` (font keys merge)."""
    options = {
        "width_mm": 72.0,
        "margins_mm": {"top": 1.0, "right": 1.0, "bottom": 3.0, "left": 1.0},
        "font": {"family": "sans-serif", "size": 9.0, "line_height": 1.25},
        "max_height_mm": 1000.0,
        "max_image_height_dots": 600,
    }
    font = overrides.pop("font", None)
    options.update(overrides)
    if font:
        options["font"] = dict(options["font"], **font)
    return options


def render(content, **overrides):
    """-> (result dict, opened fitz.Document of result['pdf_bytes'])."""
    result = r.render_ticket_pdf(content, make_options(**overrides))
    return result, fitz.open("pdf", result["pdf_bytes"])


def spans(page):
    return [s for block in page.get_text("dict")["blocks"]
            for line in block.get("lines", []) for s in line["spans"]]


def span(page, text):
    return next(s for s in spans(page) if s["text"].strip() == text)


def words(page, text):
    """Bounding boxes (x0, y0, x1, y1) of every extracted word equal to `text`."""
    return [tuple(w[:4]) for w in page.get_text("words") if w[4] == text]


def word(page, text):
    found = words(page, text)
    assert len(found) == 1, f"{text!r} found {len(found)} times"
    return found[0]


def baseline(page, text):
    return span(page, text)["origin"][1]


def line_drawings(page):
    return [d for d in page.get_drawings() if d["items"] and d["items"][0][0] == "l"]


def builtin_span_font(fontname):
    """Font name MuPDF reports in text spans for a Base-14 builtin.

    (`fitz.Font('helv').name` is 'Helvetica', but spans report the embedded
    program's name, e.g. 'NimbusSans-Regular'.)"""
    doc = fitz.open()
    page = doc.new_page()
    writer = fitz.TextWriter(page.rect)
    writer.append((50, 50), "Ab", font=fitz.Font(fontname), fontsize=10)
    writer.write_text(page)
    return spans(page)[0]["font"]


def png_base64(width, height, mode="RGB", color="white"):
    buf = io.BytesIO()
    Image.new(mode, (width, height), color).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def text_item(data, **fields):
    return dict({"type": "text", "data": data}, **fields)


MARK = text_item("MARK")


@pytest.fixture
def exact_fonts(fake_font_dir):
    """fake_font_dir with `post.isFixedPitch` cleared in every face.

    The fixture fonts claim fixed pitch while their space is half as wide as the
    other glyphs. For fixed-pitch fonts MuPDF writes ONE width for every glyph
    into the PDF (`/W [0 65535 300]`, the space width), so extracted bboxes, and
    the TJ offsets TextWriter uses for later text on the same baseline, would
    assume 3 pt per glyph at 10 pt instead of the real 6 pt. Real fonts are not
    affected (Arial, Courier New, Menlo extract at their true widths); clearing
    the flag lets positions be asserted on the PDF exactly."""
    for path in sorted(fake_font_dir.iterdir()):
        if path.name == "not-a-font.ttf":
            continue
        data = io.BytesIO(path.read_bytes())
        if path.suffix == ".ttc":
            font = TTCollection(data)
            faces = font.fonts
        else:
            font = TTFont(data)
            faces = [font]
        for face in faces:
            face["post"].isFixedPitch = 0
        font.save(str(path))
    return fake_font_dir


# ---------------------------------------------------------------------------
# Text measurement and wrapping
# ---------------------------------------------------------------------------

class TestWrapText:
    @pytest.fixture
    def face(self, fake_font_dir):
        return r.FontSet("Test Sans").resolve("Test Sans")

    def test_text_width_uses_font_metrics(self, face):
        assert r.text_width(face, 10, "AAAA BBBB") == pytest.approx(51.0, abs=0.01)

    def test_wrap_text_long_word_is_split_by_characters(self, face):
        lines = r.wrap_text("A" * 25, face, 10, 60)
        assert [len(line) for line in lines] == [10, 10, 5]

    def test_wrap_text_breaks_at_spaces(self, face):
        assert r.wrap_text("AAAA BBBB CCCC", face, 10, 54) == ["AAAA BBBB", "CCCC"]

    def test_wrap_text_honors_newlines(self, face):
        assert r.wrap_text("AB\nCD", face, 10, 100) == ["AB", "CD"]
        assert r.wrap_text("AB\n\nCD", face, 10, 100) == ["AB", "", "CD"]

    def test_wrap_text_empty_text_returns_one_empty_line(self, face):
        assert r.wrap_text("", face, 10, 60) == [""]
        assert r.wrap_text(None, face, 10, 60) == [""]

    def test_wrap_text_fitting_text_is_kept_verbatim(self, face):
        assert r.wrap_text("AB  CD", face, 10, 100) == ["AB  CD"]


# ---------------------------------------------------------------------------
# Page geometry
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("width_mm, width_pt", [(72, 204.09), (48, 136.06)])
def test_page_width_follows_width_mm(width_mm, width_pt):
    result, doc = render([text_item("x")], width_mm=width_mm)
    assert doc[0].rect.width == pytest.approx(width_pt, abs=0.05)
    assert result["page_mm"]["width"] == width_mm


def test_page_height_is_margins_plus_content():
    result, doc = render([text_item("Hola")])
    assert doc[0].rect.height == pytest.approx(4 * MM + BASE_LH, abs=0.1)
    assert result["page_mm"]["height"] == round((4 * MM + BASE_LH) / MM, 1)
    assert len(doc) == 1


def test_missing_options_use_defaults():
    result = r.render_ticket_pdf([text_item("Hola")], {})
    doc = fitz.open("pdf", result["pdf_bytes"])
    assert doc[0].rect.width == pytest.approx(PAGE_W, abs=0.05)
    assert doc[0].rect.height == pytest.approx(4 * MM + BASE_LH, abs=0.1)
    assert span(doc[0], "Hola")["size"] == pytest.approx(9)


def test_left_margin_is_applied(exact_fonts):
    _, doc = render([text_item("ABCD", font_family="Test Sans")],
                    margins_mm={"top": 1, "right": 1, "bottom": 3, "left": 5})
    assert word(doc[0], "ABCD")[0] == pytest.approx(5 * MM, abs=0.5)


# ---------------------------------------------------------------------------
# text: alignment, wrapping, high contrast, underline
# ---------------------------------------------------------------------------

class TestTextAlignment:
    def test_align_left_starts_at_left_margin(self, exact_fonts):
        _, doc = render([text_item("ABCD", font_family="Test Sans")])
        assert word(doc[0], "ABCD")[0] == pytest.approx(LEFT, abs=0.5)

    def test_align_right_ends_at_right_margin(self, exact_fonts):
        _, doc = render([text_item("ABCD", font_family="Test Sans", align="right")])
        bbox = span(doc[0], "ABCD")["bbox"]
        assert bbox[2] == pytest.approx(PAGE_W - RIGHT, abs=0.5)

    def test_align_center_is_centered(self, exact_fonts):
        _, doc = render([text_item("ABCD", font_family="Test Sans", align="center")])
        bbox = span(doc[0], "ABCD")["bbox"]
        assert (bbox[0] + bbox[2]) / 2 == pytest.approx(PAGE_W / 2, abs=0.5)


def test_long_text_wraps_within_available_width(exact_fonts):
    text = " ".join(["ABCD"] * 20)
    result, doc = render([text_item(text, font_family="Test Sans")])
    boxes = words(doc[0], "ABCD")
    lines = sorted({round(box[1], 1) for box in boxes})
    assert len(boxes) == 20 and len(lines) > 1
    assert max(box[2] for box in boxes) <= PAGE_W - RIGHT + 0.5
    assert doc[0].rect.height == pytest.approx(4 * MM + len(lines) * BASE_LH, abs=0.1)


def test_high_contrast_text_has_full_width_black_block_and_white_text():
    _, doc = render([text_item("PEDIDO 42", align="center", high_contrast=True)])
    page = doc[0]
    fills = [d for d in page.get_drawings() if d.get("fill") == (0.0, 0.0, 0.0)]
    assert len(fills) == 1
    rect = fills[0]["rect"]
    assert rect.x0 == pytest.approx(LEFT, abs=0.1)
    assert rect.x1 == pytest.approx(PAGE_W - RIGHT, abs=0.1)
    assert rect.height == pytest.approx(BASE_LH, abs=0.1)
    assert span(page, "PEDIDO 42")["color"] == 0xFFFFFF


def test_plain_text_is_black():
    _, doc = render([text_item("Hola")])
    assert span(doc[0], "Hola")["color"] == 0x000000
    assert doc[0].get_drawings() == []


def test_underline_line_is_as_wide_as_the_text(exact_fonts):
    _, doc = render([text_item("Hello", font_family="Test Sans", underline=True)])
    page = doc[0]
    lines = line_drawings(page)
    assert len(lines) == 1
    rect = lines[0]["rect"]
    assert rect.x1 - rect.x0 == pytest.approx(5 * 5.4, abs=1)     # 5 glyphs × 5.4 pt at 9 pt
    assert rect.y0 == pytest.approx(baseline(page, "Hello") + 9 * r.UNDERLINE_OFFSET, abs=0.1)
    assert lines[0]["width"] == pytest.approx(9 * r.UNDERLINE_WIDTH, abs=0.01)


def test_underline_accepts_truthy_strings():
    _, doc = render([text_item("Hola", underline="si")])
    assert len(line_drawings(doc[0])) == 1


# ---------------------------------------------------------------------------
# special_text
# ---------------------------------------------------------------------------

def test_special_text_text1_left_and_text2_right(exact_fonts):
    item = {"type": "special_text", "data": {"text1": "TOTAL", "text2": "8150"},
            "font_family": "Test Sans"}
    _, doc = render([item])
    assert word(doc[0], "TOTAL")[0] == pytest.approx(LEFT, abs=0.5)
    assert word(doc[0], "8150")[2] == pytest.approx(PAGE_W - RIGHT, abs=0.5)


def test_special_text_wide_text2_wraps_within_60_percent(exact_fonts):
    text2 = " ".join(["BBBB"] * 12)
    item = {"type": "special_text", "data": {"text1": "TOTAL", "text2": text2},
            "font_family": "Test Sans"}
    _, doc = render([item])
    boxes = words(doc[0], "BBBB")
    by_line = {}
    for box in boxes:
        by_line.setdefault(round(box[1], 1), []).append(box)
    assert len(boxes) == 12 and len(by_line) == 3
    for line in by_line.values():
        assert max(box[2] for box in line) == pytest.approx(PAGE_W - RIGHT, abs=0.5)
        assert min(box[0] for box in line) >= PAGE_W - RIGHT - AVAIL * r.SPECIAL_TEXT_RIGHT_MAX - 0.5
    assert word(doc[0], "TOTAL")[1] == pytest.approx(min(by_line), abs=0.5)


def test_special_text_high_contrast_inverts_the_whole_block():
    item = {"type": "special_text", "data": {"text1": "CAMBIO", "text2": "$18.50"},
            "high_contrast": True}
    _, doc = render([item])
    fills = [d for d in doc[0].get_drawings() if d.get("fill") == (0.0, 0.0, 0.0)]
    assert len(fills) == 1 and fills[0]["rect"].width == pytest.approx(AVAIL, abs=0.1)
    assert {s["color"] for s in spans(doc[0])} == {0xFFFFFF}


# ---------------------------------------------------------------------------
# table
# ---------------------------------------------------------------------------

def test_table_default_columns_bold_header_rule_and_right_aligned_amount():
    item = {"type": "table", "data": {"rows": [[2, "Coca", "$18.00", "$36.00"]]}}
    _, doc = render([item])
    page = doc[0]
    header_y = word(page, "Cant.")[1]
    for label in ("Cant.", "Producto", "Precio", "Importe"):
        assert word(page, label)[1] == pytest.approx(header_y, abs=0.1)
    header_spans = [s for s in spans(page) if abs(s["bbox"][1] - header_y) < 0.1]
    assert {s["font"] for s in header_spans} == {builtin_span_font("hebo")}

    rules = line_drawings(page)
    assert len(rules) >= 1
    assert rules[0]["width"] == pytest.approx(r.TABLE_RULE_WIDTH_PT, abs=0.01)
    assert rules[0]["rect"].x0 == pytest.approx(LEFT, abs=0.1)
    assert rules[0]["rect"].x1 == pytest.approx(PAGE_W - RIGHT, abs=0.1)
    assert word(page, "$36.00")[2] == pytest.approx(PAGE_W - RIGHT - PAD, abs=0.5)
    assert word(page, "2")[0] == pytest.approx(LEFT + PAD, abs=0.5)


def test_table_custom_columns_not_summing_100_are_normalized(exact_fonts):
    columns = [{"label": "Aa", "width": 1}, {"label": "Bb", "width": 1},
               {"label": "Cc", "width": 2, "align": "right"}]
    item = {"type": "table", "font_family": "Test Sans",
            "data": {"columns": columns, "rows": [["11", "22", "33"]]}}
    _, doc = render([item])
    page = doc[0]
    assert word(page, "22")[0] == pytest.approx(LEFT + AVAIL * 0.25 + PAD, abs=0.5)
    assert word(page, "33")[2] == pytest.approx(PAGE_W - RIGHT - PAD, abs=0.5)
    assert word(page, "Cc")[2] == pytest.approx(PAGE_W - RIGHT - PAD, abs=0.5)
    assert "Test Sans Bold" in span(page, "Aa")["font"]
    assert "Test Sans Regular" in span(page, "11")["font"]


def test_table_missing_widths_share_the_rest(exact_fonts):
    columns = [{"label": "Aa", "width": 50}, {"label": "Bb"}, {"label": "Cc"}]
    item = {"type": "table", "font_family": "Test Sans", "data": {"columns": columns, "rows": []}}
    _, doc = render([item])
    assert word(doc[0], "Bb")[0] == pytest.approx(LEFT + AVAIL * 0.50 + PAD, abs=0.5)
    assert word(doc[0], "Cc")[0] == pytest.approx(LEFT + AVAIL * 0.75 + PAD, abs=0.5)


def test_table_short_rows_pad_and_long_rows_are_truncated():
    rows = [["7"], [1, "Pan", "$1.00", "$1.00", "EXTRA", "MORE"]]
    _, doc = render([{"type": "table", "data": {"rows": rows}}])
    text = doc[0].get_text()
    assert "7" in text and "Pan" in text
    assert "EXTRA" not in text and "MORE" not in text


def test_table_wrapped_cell_grows_the_row():
    rows = [[1, "Coca Cola 600ml con nombre largo que envuelve", "$1", "$1"], [2, "Pan", "$2", "$2"]]
    _, doc = render([{"type": "table", "data": {"rows": rows}}])
    page = doc[0]
    rows_y = sorted({round(w[1], 1) for w in page.get_text("words") if w[4] in ("Coca", "Pan", "envuelve")})
    assert len(rows_y) >= 3   # 'Coca' line, 'envuelve' on a later line, then the 'Pan' row
    assert word(page, "Pan")[1] > word(page, "envuelve")[1]


def test_table_without_rows_renders_only_the_header():
    _, doc = render([{"type": "table", "data": {}}])
    page = doc[0]
    assert {"Cant.", "Producto", "Precio", "Importe"} <= {w[4] for w in page.get_text("words")}
    expected = 4 * MM + BASE_LH + r.TABLE_HEADER_GAP_MM * MM
    assert page.rect.height == pytest.approx(expected, abs=0.1)


# ---------------------------------------------------------------------------
# Fonts: system faces, builtins, fallback, synthetic bold
# ---------------------------------------------------------------------------

def test_font_weight_bold_uses_the_bold_face(fake_font_dir):
    result, doc = render([text_item("Hola", font_family="Test Sans", font_weight="bold")])
    assert "Bold" in span(doc[0], "Hola")["font"]
    assert result["fonts"] == [{"family": "Test Sans", "resolved": "Test Sans Bold",
                                "source": "system", "bold": True, "italic": False}]
    assert result["warnings"] == []


def test_font_style_italic_without_italic_face_warns_and_uses_regular(fake_font_dir):
    result, doc = render([text_item("Hola", font_family="Test Sans", font_style="italic")])
    assert "Test Sans Regular" in span(doc[0], "Hola")["font"]
    assert result["warnings"] == ["Font family 'Test Sans' has no italic face; using Regular."]


def test_italic_face_from_a_ttc_collection(fake_font_dir):
    _, doc = render([text_item("Hola", font_family="Test Mono", font_style="italic")])
    assert "Test Mono Italic" in span(doc[0], "Hola")["font"]


def test_unknown_family_falls_back_to_sans_serif_with_one_warning(fake_font_dir):
    content = [text_item("Hola", font_family="Nope"), text_item("Adios", font_family="Nope")]
    result, doc = render(content)
    assert result["warnings"] == ["Font family 'Nope' is not installed; using sans-serif."]
    assert span(doc[0], "Hola")["font"] == builtin_span_font("helv")
    assert result["fonts"] == [{"family": "Nope", "resolved": fitz.Font("helv").name,
                                "source": "fallback", "bold": False, "italic": False}]


def test_known_builtin_name_not_installed_uses_builtin_without_warning(fake_font_dir):
    result, doc = render([text_item("Folio", font_family="Courier")])
    assert span(doc[0], "Folio")["font"] == builtin_span_font("cour")
    assert result["warnings"] == []
    assert result["fonts"][0]["resolved"] == fitz.Font("cour").name
    assert result["fonts"][0]["source"] == "builtin"


@pytest.mark.parametrize("family, fontname", [("sans-serif", "helv"), ("serif", "tiro"),
                                              ("monospace", "cour"), ("SERIF", "tiro")])
def test_generic_families_use_base14_builtins(family, fontname):
    result, doc = render([text_item("Hola", font_family=family)])
    assert span(doc[0], "Hola")["font"] == builtin_span_font(fontname)
    assert result["fonts"][0]["source"] == "builtin"
    assert result["fonts"][0]["resolved"] == fitz.Font(fontname).name


def test_builtin_bold_italic_variant():
    _, doc = render([text_item("Hola", font_weight="bold", font_style="italic")])
    assert span(doc[0], "Hola")["font"] == builtin_span_font("hebi")


def test_missing_bold_face_is_synthesized_by_painting_twice(exact_fonts):
    result, doc = render([text_item("Hello", font_family="Test Mono", font_weight="bold")])
    origins = sorted(char[2][0] for trace in doc[0].get_texttrace()
                     for char in trace["chars"] if chr(char[0]) == "H")
    assert len(origins) == 2
    assert origins[0] == pytest.approx(LEFT, abs=0.01)
    assert origins[1] - origins[0] == pytest.approx(r.FAKE_BOLD_OFFSET * 9, abs=0.01)
    assert result["fonts"][0]["resolved"] == "Test Mono Regular"
    assert result["fonts"][0]["bold"] is True
    assert result["warnings"] == ["Font family 'Test Mono' has no bold face; using Regular."]


def test_font_set_used_is_unique_per_face(fake_font_dir):
    content = [text_item("A", font_family="Test Sans"), text_item("B", font_family="Test Sans"),
               text_item("C", font_family="Test Sans", font_weight="bold")]
    result, _ = render(content)
    assert [entry["resolved"] for entry in result["fonts"]] == ["Test Sans Regular", "Test Sans Bold"]
    assert all(set(entry) == {"family", "resolved", "source", "bold", "italic"} for entry in result["fonts"])


def test_default_family_from_options_applies_to_items(fake_font_dir):
    _, doc = render([text_item("Hola")], font={"family": "Test Sans"})
    assert "Test Sans" in span(doc[0], "Hola")["font"]


@pytest.fixture
def nbsp_font(exact_fonts):
    """'Test Sans' Regular whose cmap also maps U+00A0 to the space glyph (like Arial)."""
    path = exact_fonts / "TestSans-Regular.ttf"
    font = TTFont(io.BytesIO(path.read_bytes()))
    for table in font["cmap"].tables:
        table.cmap[0xA0] = "space"
    font.save(str(path))
    return exact_fonts


def test_extracted_text_keeps_plain_spaces_when_glyph_is_shared(nbsp_font):
    _, doc = render([text_item("AB CD", font_family="Test Sans")])
    assert doc[0].get_text() == "AB CD\n"


def test_to_unicode_fix_failure_never_blocks_the_ticket(monkeypatch):
    def broken_fix(*args, **kwargs):
        raise RuntimeError("boom")
    content = [text_item("Hola"), text_item("Adios", font_family="Nope")]
    expected_warnings = render(content)[0]["warnings"]
    monkeypatch.setattr(r, "_fix_to_unicode", broken_fix)
    result, doc = render(content)
    assert len(doc) == 1
    assert "Hola" in doc[0].get_text() and "Adios" in doc[0].get_text()
    assert result["warnings"] == expected_warnings


# ---------------------------------------------------------------------------
# font_size / line_height / options validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("font_size, expected", [("normal", 9), ("md", 18), ("lg", 27), (" MD ", 18)])
def test_font_size_keywords_scale_the_base_size(font_size, expected):
    _, doc = render([text_item("Hola", font_size=font_size)])
    assert span(doc[0], "Hola")["size"] == pytest.approx(expected)


@pytest.mark.parametrize("font_size, expected", [(14, 14), (10.5, 10.5), ("14", 14),
                                                 (100, 72), (2, 4), ("huge", 9), (None, 9)])
def test_font_size_numbers_are_points_clamped_4_to_72(font_size, expected):
    _, doc = render([text_item("Hola", font_size=font_size)])
    assert span(doc[0], "Hola")["size"] == pytest.approx(expected)


@pytest.mark.parametrize("size", [3, 73, "abc", True])
def test_font_size_option_out_of_range_raises(size):
    with pytest.raises(ValueError) as exc:
        r.render_ticket_pdf([text_item("Hola")], make_options(font={"size": size}))
    assert str(exc.value) == "'font.size' must be a number between 4 and 72."


@pytest.mark.parametrize("line_height, expected", [(2, 18.0), (5, BASE_LH), ("x", BASE_LH)])
def test_item_line_height_overrides_the_option(line_height, expected):
    _, doc = render([text_item("Hola", line_height=line_height)])
    assert doc[0].rect.height == pytest.approx(4 * MM + expected, abs=0.1)


def test_option_line_height_out_of_range_falls_back_to_default():
    _, doc = render([text_item("Hola")], font={"line_height": 9})
    assert doc[0].rect.height == pytest.approx(4 * MM + BASE_LH, abs=0.1)


# ---------------------------------------------------------------------------
# separator / image / spacer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("style, count, dashed", [("dashed", 1, True), ("solid", 1, False),
                                                  ("dotted", 1, True), ("double", 2, False),
                                                  ("wavy", 1, True), (None, 1, True)])
def test_separator_styles_draw_lines(style, count, dashed):
    _, doc = render([{"type": "separator", "style": style}])
    lines = line_drawings(doc[0])
    assert len(lines) == count
    for line in lines:
        assert (line["dashes"] != "[] 0") is dashed
        assert line["rect"].x0 == pytest.approx(LEFT, abs=0.1)
        assert line["rect"].x1 == pytest.approx(PAGE_W - RIGHT, abs=0.1)


def test_double_separator_lines_are_0_6_pt_from_the_middle():
    _, doc = render([{"type": "separator", "style": "double"}])
    ys = sorted(line["rect"].y0 for line in line_drawings(doc[0]))
    middle = 1 * MM + r.SEPARATOR_BLOCK_MM * MM / 2
    assert ys == pytest.approx([middle - 0.6, middle + 0.6], abs=0.01)


@pytest.mark.parametrize("thickness, width", [(None, 0.6), (10, 3.0), (0.01, 0.2), (1.5, 1.5)])
def test_separator_thickness_is_clamped(thickness, width):
    _, doc = render([{"type": "separator", "thickness": thickness}])
    assert line_drawings(doc[0])[0]["width"] == pytest.approx(width, abs=0.01)


def test_separator_occupies_a_2mm_block():
    _, plain = render([MARK])
    _, after = render([{"type": "separator"}, MARK])
    assert baseline(after[0], "MARK") - baseline(plain[0], "MARK") == pytest.approx(2 * MM, abs=0.2)


def test_image_width_mm_sets_size_and_advances_the_cursor():
    _, plain = render([MARK])
    _, doc = render([{"type": "image", "data": png_base64(300, 100), "width_mm": 30}, MARK])
    page = doc[0]
    assert len(page.get_images()) == 1
    bbox = fitz.Rect(page.get_image_info()[0]["bbox"])
    assert bbox.width == pytest.approx(30 * MM, abs=0.1)
    assert (bbox.x0 + bbox.x1) / 2 == pytest.approx(PAGE_W / 2, abs=0.1)   # default: centered
    assert baseline(page, "MARK") - baseline(plain[0], "MARK") == pytest.approx(10 * MM, abs=0.3)


@pytest.mark.parametrize("align", ["left", "right"])
def test_image_width_dots_and_align(align):
    item = {"type": "image", "data": png_base64(100, 100), "width_dots": 160, "align": align}
    _, doc = render([item])
    bbox = fitz.Rect(doc[0].get_image_info()[0]["bbox"])
    assert bbox.width == pytest.approx(20 * MM, abs=0.1)
    if align == "left":
        assert bbox.x0 == pytest.approx(LEFT, abs=0.1)
    else:
        assert bbox.x1 == pytest.approx(PAGE_W - RIGHT, abs=0.1)


def test_image_default_width_is_384_dots_capped_to_available_width():
    _, doc = render([{"type": "image", "data": png_base64(100, 100)}])
    assert fitz.Rect(doc[0].get_image_info()[0]["bbox"]).width == pytest.approx(48 * MM, abs=0.1)
    _, wide = render([{"type": "image", "data": png_base64(100, 100), "width_mm": 100}])
    assert fitz.Rect(wide[0].get_image_info()[0]["bbox"]).width == pytest.approx(AVAIL, abs=0.1)


def test_image_taller_than_the_ceiling_is_scaled_down_with_warning():
    item = {"type": "image", "data": png_base64(10, 100), "width_mm": 30}
    result, doc = render([item])
    bbox = fitz.Rect(doc[0].get_image_info()[0]["bbox"])
    assert bbox.height == pytest.approx(600 / 8 * MM, abs=0.1)
    assert bbox.width == pytest.approx(7.5 * MM, abs=0.1)
    assert result["warnings"] == ["Image in item 0 scaled down to fit 600 dots."]


def test_image_transparency_is_flattened_on_white():
    item = {"type": "image", "data": png_base64(20, 20, mode="RGBA", color=(0, 0, 0, 0))}
    _, doc = render([item])
    xref = doc[0].get_images()[0][0]
    pix = fitz.Pixmap(doc, xref)
    assert pix.n == 3 and not pix.alpha
    assert pix.pixel(10, 10) == (255, 255, 255)


@pytest.mark.parametrize("data", ["not base64 at all!!", base64.b64encode(b"garbage").decode(), 12])
def test_image_invalid_data_raises_with_item_index(data):
    content = [text_item("x"), MARK, {"type": "image", "data": data}]
    with pytest.raises(ValueError) as exc:
        r.render_ticket_pdf(content, make_options())
    assert str(exc.value) == "Invalid image data in item 2."
    with pytest.raises(ValueError, match=re.escape("Invalid image data in item 0.")):
        r.render_ticket_pdf([{"type": "image", "data": data}], make_options())


def test_image_without_data_is_ignored():
    result, doc = render([{"type": "image"}])
    assert doc[0].get_images() == [] and result["warnings"] == []


@pytest.mark.parametrize("item, advance", [
    ({"type": "spacer", "lines": 2}, 2 * BASE_LH),
    ({"type": "spacer"}, BASE_LH),
    ({"type": "spacer", "lines": "x"}, BASE_LH),
    ({"type": "spacer", "lines": 0}, BASE_LH),
    ({"type": "spacer", "height_mm": 5}, 5 * MM),
    ({"type": "spacer", "lines": 3, "height_mm": 5}, 5 * MM),
    ({"type": "spacer", "height_mm": 500}, 200 * MM),
])
def test_spacer_advances_the_cursor(item, advance):
    _, plain = render([MARK])
    _, doc = render([item, MARK])
    assert baseline(doc[0], "MARK") - baseline(plain[0], "MARK") == pytest.approx(advance, abs=0.1)


# ---------------------------------------------------------------------------
# html (fitz.Story)
# ---------------------------------------------------------------------------

HTML = "<p style='text-align:center'>Gracias por su <b>compra</b></p>"


def test_html_block_is_embedded_as_pdf():
    result, doc = render([{"type": "html", "data": HTML}])
    page = doc[0]
    assert "Gracias por su compra" in page.get_text()
    assert page.get_xobjects()                       # placed with show_pdf_page
    assert page.rect.height == pytest.approx(4 * MM + BASE_LH, abs=0.1)
    assert result["warnings"] == []


def test_html_block_uses_the_system_default_family(fake_font_dir):
    _, doc = render([{"type": "html", "data": HTML}], font={"family": "Test Sans"})
    page = doc[0]
    assert "Test Sans" in span(page, "Gracias por su")["font"]
    assert "Test Sans Bold" in span(page, "compra")["font"]


def test_html_block_failure_warns_and_skips_the_block(monkeypatch):
    def broken_story(*args, **kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(r.fitz, "Story", broken_story)
    result, doc = render([{"type": "html", "data": HTML}, MARK])
    assert result["warnings"] == ["HTML block in item 0 could not be rendered: boom"]
    assert doc[0].rect.height == pytest.approx(4 * MM + BASE_LH, abs=0.1)
    assert "MARK" in doc[0].get_text()


def test_empty_html_block_is_ignored():
    _, doc = render([{"type": "html", "data": "   "}, {"type": "html", "data": None}])
    assert doc[0].rect.height == pytest.approx(4 * MM, abs=0.1)


# ---------------------------------------------------------------------------
# Limits, drawer, ignored items, PNG, size
# ---------------------------------------------------------------------------

def test_ticket_taller_than_max_height_raises_exact_message():
    content = [text_item(f"Linea {i}") for i in range(60)]
    height_mm = (4 * MM + 60 * BASE_LH) / MM
    with pytest.raises(ValueError) as exc:
        r.render_ticket_pdf(content, make_options(max_height_mm=20))
    assert str(exc.value) == f"Rendered ticket is too tall ({height_mm:.1f} mm > 20 mm)."


def test_open_withdrawer_sets_the_flag_and_draws_nothing():
    result, doc = render([{"type": "open_withdrawer"}])
    assert result["open_drawer"] is True
    assert doc[0].get_text() == "" and doc[0].get_drawings() == []
    assert render([text_item("x")])[0]["open_drawer"] is False


def test_unknown_and_malformed_items_are_ignored():
    content = ["text", None, {"type": "bogus", "data": "X"}, {"type": ["text"]},
               {"type": "special_text", "data": "no dict"}, text_item("Hola")]
    result, doc = render(content)
    assert doc[0].get_text() == "Hola\n"
    assert result["warnings"] == []


def test_render_png_width_matches_dpi():
    result, _ = render([text_item("Hola")])
    png = r.render_png(result["pdf_bytes"], 203)
    assert png[:4] == b"\x89PNG"
    width = Image.open(io.BytesIO(png)).width
    assert width == pytest.approx(576, abs=2)


def test_ticket_with_system_font_is_subset_and_small(fake_font_dir):
    content = [
        text_item("MI TIENDA", align="center", font_size="lg", font_weight="bold"),
        text_item("Av Principal 123", align="center"),
        text_item("PEDIDO 42", align="center", high_contrast=True),
        {"type": "separator"},
        {"type": "table", "data": {"columns": [{"label": "Cant"}, {"label": "Producto"}],
                                   "rows": [[2, "Coca Cola"], [1, "Pan"]]}},
        {"type": "separator", "style": "solid"},
        {"type": "special_text", "data": {"text1": "TOTAL", "text2": "8150"}, "font_weight": "bold"},
        text_item("Gracias", underline=True),
        {"type": "spacer", "lines": 1},
        {"type": "html", "data": "<p>Vuelva pronto</p>"},
    ]
    result, doc = render(content, font={"family": "Test Sans"})
    assert len(result["pdf_bytes"]) < 60_000
    assert result["warnings"] == []
    descriptors = [doc.xref_get_key(xref, "FontName")[1] for xref in range(1, doc.xref_length())
                   if doc.xref_get_key(xref, "Type")[1] == "/FontDescriptor"]
    assert descriptors and all(re.match(r"^/[A-Z]{6}\+", name) for name in descriptors)


def test_subsetting_failure_is_reported_as_warning(monkeypatch):
    def broken_subset(self, *args, **kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(fitz.Document, "subset_fonts", broken_subset)
    result, doc = render([text_item("Hola")])
    assert result["warnings"] == ["Font subsetting skipped: boom"]
    assert "Hola" in doc[0].get_text()
