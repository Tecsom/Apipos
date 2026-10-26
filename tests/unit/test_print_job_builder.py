"""Unit tests for PrintJobBuilder: exact ESC/POS bytes, padding and state resets."""
import pytest

from src.services import escpos_service
from src.services.print_job_builder import PrintJobBuilder

# Literal oracle bytes (deliberately not imported from production code).
LINE_HEIGHT_TEXT = b"\x1b\x33\x42"
LINE_HEIGHT_IMAGE = b"\x1b\x33\x00"
ALIGN_LEFT = b"\x1b\x61\x00"
ALIGN_CENTER = b"\x1b\x61\x01"
FONT_NORMAL = b"\x1d\x21\x00"
FONT_MD = b"\x1d\x21\x11"
FONT_LG = b"\x1d\x21\x22"
FULL_CUT = b"\x1d\x56\x00"
OPEN_DRAWER = b"\x1b\x70\x00\x19\xfa"
HC_ON = b"\x1d\x42\x01"
HC_OFF = b"\x1d\x42\x00"
BOLD_ON = b"\x1b\x45\x01"
BOLD_OFF = b"\x1b\x45\x00"
FONT_B = b"\x1b\x4d\x01"
FONT_C = b"\x1b\x4d\x02"
TYPEFACE_RESET = b"\x1b\x4d\x00"
ESC_M = b"\x1b\x4d"


def _between(data, start_marker, end_marker, start_at=0):
    """Bytes strictly between the first start_marker (from start_at) and the next end_marker."""
    start = data.index(start_marker, start_at) + len(start_marker)
    end = data.index(end_marker, start)
    return data[start:end]


def _body(builder):
    """Job bytes without the LINE_HEIGHT_TEXT prefix emitted by the constructor."""
    data = builder.to_bytes()
    assert data.startswith(LINE_HEIGHT_TEXT)
    return data[len(LINE_HEIGHT_TEXT):]


# ---------------------------------------------------------------------------
# Job start
# ---------------------------------------------------------------------------

def test_new_builder_stream_starts_with_text_line_height():
    assert PrintJobBuilder(48).to_bytes() == LINE_HEIGHT_TEXT
    b = PrintJobBuilder(48)
    b.add_text("HOLA")
    assert b.to_bytes().startswith(LINE_HEIGHT_TEXT)


# ---------------------------------------------------------------------------
# add_text: padding, font size, resets, latin1
# ---------------------------------------------------------------------------

class TestAddText:
    def test_add_text_default_item_exact_legacy_bytes(self):
        b = PrintJobBuilder(48)
        b.add_text("HOLA")
        assert b.to_bytes() == (
            LINE_HEIGHT_TEXT + FONT_NORMAL + b"HOLA" + b" " * 44 + FONT_NORMAL + b"\n"
        )

    @pytest.mark.parametrize(
        "align, expected",
        [
            ("left", b"HOLA" + b" " * 44),
            ("center", b" " * 22 + b"HOLA" + b" " * 22),
            ("right", b" " * 44 + b"HOLA"),
        ],
    )
    def test_add_text_align_pads_to_48_columns(self, align, expected):
        b = PrintJobBuilder(48)
        b.add_text("HOLA", align=align)
        text = _between(b.to_bytes(), FONT_NORMAL, FONT_NORMAL)
        assert text == expected
        assert len(text) == 48

    @pytest.mark.parametrize(
        "align, expected",
        [
            ("left", b"HOLA" + b" " * 28),
            ("center", b" " * 14 + b"HOLA" + b" " * 14),
            ("right", b" " * 28 + b"HOLA"),
        ],
    )
    def test_add_text_width_32_pads_to_32_columns(self, align, expected):
        b = PrintJobBuilder(32)
        b.add_text("HOLA", align=align)
        text = _between(b.to_bytes(), FONT_NORMAL, FONT_NORMAL)
        assert text == expected
        assert len(text) == 32

    @pytest.mark.parametrize(
        "font_size, size_cmd, cols",
        [("md", FONT_MD, 24), ("lg", FONT_LG, 16)],
    )
    def test_add_text_font_size_scales_width(self, font_size, size_cmd, cols):
        b = PrintJobBuilder(48)
        b.add_text("HI", align="right", font_size=font_size)
        data = b.to_bytes()
        assert data.count(size_cmd) == 1
        text = _between(data, size_cmd, FONT_NORMAL)
        assert text == b" " * (cols - 2) + b"HI"
        assert len(text) == cols

    def test_add_text_resets_font_normal_before_each_newline(self):
        b = PrintJobBuilder(48)
        b.add_text("UNO", font_size="md")
        b.add_text("DOS", font_size="lg")
        b.add_text("TRES")
        data = b.to_bytes()
        assert data.count(b"\n") == 3
        pos = 0
        for _ in range(3):
            nl = data.index(b"\n", pos)
            assert data[nl - len(FONT_NORMAL):nl] == FONT_NORMAL
            pos = nl + 1

    def test_add_text_accents_encoded_as_latin1(self):
        b = PrintJobBuilder(48)
        b.add_text("Año café")
        data = b.to_bytes()
        assert "ñ".encode("latin1") in data
        assert "é".encode("latin1") in data
        assert "ñ".encode("utf-8") not in data
        # latin1 = one byte per character, so padding still lands on 48 columns.
        text = _between(data, FONT_NORMAL, FONT_NORMAL)
        assert text == "Año café".ljust(48).encode("latin1")
        assert len(text) == 48


# ---------------------------------------------------------------------------
# high_contrast (GS B reverse video)
# ---------------------------------------------------------------------------

class TestHighContrast:
    def test_add_text_high_contrast_on_off_once_before_newline(self):
        b = PrintJobBuilder(48)
        b.add_text("X", high_contrast=True)
        data = b.to_bytes()
        assert data.count(HC_ON) == 1
        assert data.count(HC_OFF) == 1
        on, off = data.index(HC_ON), data.index(HC_OFF)
        assert on < off < data.index(b"\n", on)
        # The reversed block is the text plus a 1-space margin on each side.
        assert _between(data, HC_ON, HC_OFF) == b" X "

    @pytest.mark.parametrize(
        "align, left, right",
        [("left", 0, 42), ("center", 21, 21), ("right", 42, 0)],
    )
    def test_add_text_high_contrast_alignment_padding_outside_block(self, align, left, right):
        b = PrintJobBuilder(48)
        b.add_text("HOLA", align=align, high_contrast=True)
        data = b.to_bytes()
        assert _between(data, FONT_NORMAL, HC_ON) == b" " * left
        assert _between(data, HC_ON, HC_OFF) == b" HOLA "
        assert _between(data, HC_OFF, FONT_NORMAL) == b" " * right
        assert left + len(b" HOLA ") + right == 48

    def test_add_text_high_contrast_odd_padding_center_extra_space_on_left(self):
        # documents current behavior: with an odd pad the extra column goes to
        # the LEFT, while the non-inverted path (str.center on an even width)
        # puts it on the RIGHT, so "HOL" prints one column further right.
        b = PrintJobBuilder(48)
        b.add_text("HOL", align="center", high_contrast=True)
        data = b.to_bytes()
        assert _between(data, FONT_NORMAL, HC_ON) == b" " * 22
        assert _between(data, HC_OFF, FONT_NORMAL) == b" " * 21

    def test_add_text_high_contrast_text_fills_width_drops_margins(self):
        b = PrintJobBuilder(48)
        b.add_text("A" * 48, high_contrast=True)
        data = b.to_bytes()
        assert _between(data, HC_ON, HC_OFF) == b"A" * 48
        assert _between(data, FONT_NORMAL, HC_ON) == b""
        assert _between(data, HC_OFF, FONT_NORMAL) == b""

    def test_add_special_text_high_contrast_wraps_full_line(self):
        b = PrintJobBuilder(48)
        b.add_special_text("TOTAL", "$10.00", high_contrast=True)
        data = b.to_bytes()
        assert data.count(HC_ON) == 1
        assert data.count(HC_OFF) == 1
        on, off = data.index(HC_ON), data.index(HC_OFF)
        assert on < off < data.index(b"\n", on)
        line = _between(data, HC_ON, HC_OFF)
        assert line == b"TOTAL" + b" " * 37 + b"$10.00"
        assert len(line) == 48


# ---------------------------------------------------------------------------
# font_weight / font (ESC E, ESC M)
# ---------------------------------------------------------------------------

class TestFontWeightAndTypeface:
    def test_add_text_default_emits_no_bold_or_typeface_commands(self):
        b = PrintJobBuilder(48)
        b.add_text("HOLA")
        b.add_special_text("A", "B")
        data = b.to_bytes()
        assert BOLD_ON not in data
        assert BOLD_OFF not in data
        assert ESC_M not in data

    def test_add_text_bold_wraps_text_and_resets_before_newline(self):
        b = PrintJobBuilder(48)
        b.add_text("X", font_weight="bold")
        data = b.to_bytes()
        assert data.count(BOLD_ON) == 1
        assert data.count(BOLD_OFF) == 1
        on, off = data.index(BOLD_ON), data.index(BOLD_OFF)
        nl = data.index(b"\n", on)
        assert on < data.index(b"X") < off < nl
        assert data.rindex(FONT_NORMAL) < nl

    @pytest.mark.parametrize(
        "width, font, cmd, cols",
        [(48, "b", FONT_B, 64), (48, "c", FONT_C, 72), (32, "b", FONT_B, 42), (32, "c", FONT_C, 48)],
    )
    def test_add_text_narrow_typeface_recomputes_padding(self, width, font, cmd, cols):
        b = PrintJobBuilder(width)
        b.add_text("HOLA", align="right", font=font)
        data = b.to_bytes()
        assert data.count(cmd) == 1
        assert data.count(TYPEFACE_RESET) == 1
        # Measure the text itself (between the size command and its reset),
        # not the raw distance to the newline (which also holds the resets).
        text = _between(data, cmd + FONT_NORMAL, FONT_NORMAL)
        assert text == b" " * (cols - 4) + b"HOLA"
        assert len(text) == cols
        nl = data.index(b"\n")
        assert data.index(cmd) < data.index(b"HOLA") < data.index(TYPEFACE_RESET) < nl

    def test_add_text_narrow_typeface_with_font_size_md_halves_columns(self):
        b = PrintJobBuilder(48)
        b.add_text("HI", font="b", font_size="md")
        data = b.to_bytes()
        text = _between(data, FONT_B + FONT_MD, FONT_NORMAL)
        assert len(text) == 32  # 64 // 2
        assert text == b"HI" + b" " * 30

    def test_add_text_all_modes_reset_before_newline(self):
        b = PrintJobBuilder(48)
        b.add_text("X", font_size="lg", high_contrast=True, font_weight="bold", font="b")
        b.add_text("Y")
        data = b.to_bytes()
        nl = data.index(b"\n")
        for off in (HC_OFF, BOLD_OFF, FONT_NORMAL, TYPEFACE_RESET):
            assert data.rindex(off, 0, nl) < nl
        assert data.index(HC_OFF) < data.index(BOLD_OFF) < data.rindex(FONT_NORMAL, 0, nl) \
            < data.index(TYPEFACE_RESET) < nl
        # No mode leaks into the next item.
        after = data[nl + 1:]
        for on in (HC_ON, BOLD_ON, FONT_B, FONT_LG):
            assert on not in after
        assert after == FONT_NORMAL + b"Y" + b" " * 47 + FONT_NORMAL + b"\n"

    def test_add_text_uppercase_font_is_normalized(self):
        upper, lower = PrintJobBuilder(48), PrintJobBuilder(48)
        upper.add_text("HOLA", font=" B ")
        lower.add_text("HOLA", font="b")
        assert upper.to_bytes() == lower.to_bytes()

    def test_add_special_text_narrow_typeface_and_bold(self):
        b = PrintJobBuilder(48)
        b.add_special_text("TOTAL", "$10.00", font="b", font_weight="bold")
        data = b.to_bytes()
        line = _between(data, BOLD_ON, BOLD_OFF)
        assert line == b"TOTAL" + b" " * 53 + b"$10.00"
        assert len(line) == 64
        nl = data.index(b"\n")
        assert data.index(BOLD_OFF) < data.rindex(FONT_NORMAL) < data.index(TYPEFACE_RESET) < nl


# ---------------------------------------------------------------------------
# Default path must stay byte-identical
# ---------------------------------------------------------------------------

class TestDefaultPathIntact:
    def test_add_text_explicit_defaults_byte_identical(self):
        implicit, explicit = PrintJobBuilder(48), PrintJobBuilder(48)
        implicit.add_text("HOLA", align="center")
        explicit.add_text("HOLA", align="center", font_size="normal",
                          high_contrast=False, font_weight="normal", font="a")
        assert implicit.to_bytes() == explicit.to_bytes()

    def test_add_text_unknown_weight_and_font_byte_identical(self):
        default, unknown = PrintJobBuilder(48), PrintJobBuilder(48)
        default.add_text("HOLA", align="right")
        unknown.add_text("HOLA", align="right", font_weight="thin", font="z")
        assert unknown.to_bytes() == default.to_bytes()

    def test_add_text_none_font_byte_identical(self):
        default, none_font = PrintJobBuilder(48), PrintJobBuilder(48)
        default.add_text("HOLA")
        none_font.add_text("HOLA", font=None)
        assert none_font.to_bytes() == default.to_bytes()

    def test_add_special_text_unknown_weight_and_font_byte_identical(self):
        default, unknown = PrintJobBuilder(48), PrintJobBuilder(48)
        default.add_special_text("TOTAL", "$10.00")
        unknown.add_special_text("TOTAL", "$10.00", font_weight="thin", font="z")
        assert unknown.to_bytes() == default.to_bytes()
        assert _body(default) == (
            FONT_NORMAL + b"TOTAL" + b" " * 37 + b"$10.00" + FONT_NORMAL + b"\n"
        )


# ---------------------------------------------------------------------------
# Separator, table, cut, drawer, image
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("width", [48, 32])
def test_add_separator_emits_dashes_of_width(width):
    b = PrintJobBuilder(width)
    b.add_separator()
    assert _body(b) == b"-" * width + b"\n"


def test_add_table_emits_header_dashes_and_formatted_rows():
    b = PrintJobBuilder(48)
    b.add_table([[2, "Taco", "10.00", "20.00"], [1, "Agua", "15.00", "15.00"]])
    # 15/45/20/20 % of 48 columns, truncated: 7 / 21 / 9 / 9.
    header = "Cant.".ljust(7) + "Producto".ljust(21) + "Precio".rjust(9) + "Importe".rjust(9)
    row1 = "2".ljust(7) + "Taco".ljust(21) + "10.00".rjust(9) + "20.00".rjust(9)
    row2 = "1".ljust(7) + "Agua".ljust(21) + "15.00".rjust(9) + "15.00".rjust(9)
    expected = "\n" + header + "\n" + "-" * 48 + "\n" + row1 + "\n" + row2 + "\n" + "\n"
    body = _body(b)
    assert body == expected.encode("latin1")
    assert body.startswith(b"\n")  # leading blank line
    assert row1 == escpos_service.format_table_item(2, "Taco", "10.00", "20.00", 48)


def test_add_feed_and_cut_appends_four_newlines_and_full_cut_at_end():
    b = PrintJobBuilder(48)
    b.add_text("HOLA")
    b.add_feed_and_cut()
    data = b.to_bytes()
    assert data.endswith(b"\n\n\n\n" + FULL_CUT)
    assert data.count(FULL_CUT) == 1
    cut_only = PrintJobBuilder(48)
    cut_only.add_feed_and_cut()
    assert _body(cut_only) == b"\n\n\n\n" + FULL_CUT


def test_add_open_drawer_emits_drawer_pulse():
    b = PrintJobBuilder(48)
    b.add_open_drawer()
    assert _body(b) == OPEN_DRAWER


def test_add_image_switches_line_height_left_aligned_and_restores_text():
    from PIL import Image

    image = Image.new("1", (8, 1), 0)  # one all-black row
    image_data = escpos_service.convert_image_to_escpos_format(image)
    assert image_data == b"\x1d\x76\x30\x00" + bytes([1, 0, 1, 0]) + b"\xff"

    b = PrintJobBuilder(48)
    b.add_image(image_data)
    data = b.to_bytes()
    assert _body(b) == (
        LINE_HEIGHT_IMAGE + ALIGN_LEFT + image_data + b"\n" + LINE_HEIGHT_TEXT + ALIGN_LEFT
    )
    # Centering lives in the pixels (pad_left_to_center), never in ESC a 1.
    assert ALIGN_CENTER not in data
    img_pos = data.index(image_data)
    assert data.index(LINE_HEIGHT_IMAGE) < img_pos < data.rindex(LINE_HEIGHT_TEXT)


# ---------------------------------------------------------------------------
# add_spacer (TASK-005): blank lines, the only ESC/POS addition of the task
# ---------------------------------------------------------------------------

class TestAddSpacer:
    def test_add_spacer_three_lines_emits_exactly_three_newlines(self):
        b = PrintJobBuilder(48)
        b.add_spacer(3)
        assert _body(b) == b"\n\n\n"

    def test_add_spacer_default_emits_one_newline(self):
        b = PrintJobBuilder(48)
        b.add_spacer()
        assert _body(b) == b"\n"

    @pytest.mark.parametrize("lines", [0, -2, None, "abc", [], float("nan"), float("inf")])
    def test_add_spacer_unusable_lines_fall_back_to_one_newline(self, lines):
        b = PrintJobBuilder(48)
        b.add_spacer(lines)  # never raises
        assert _body(b) == b"\n"

    @pytest.mark.parametrize("lines, expected", [("2", b"\n\n"), (2.9, b"\n\n"), (True, b"\n")])
    def test_add_spacer_numeric_like_lines_are_truncated_to_int(self, lines, expected):
        b = PrintJobBuilder(48)
        b.add_spacer(lines)
        assert _body(b) == expected

    def test_add_spacer_emits_no_mode_commands(self):
        b = PrintJobBuilder(48)
        b.add_text("A")
        before = b.to_bytes()
        b.add_spacer(2)
        assert b.to_bytes() == before + b"\n\n"
