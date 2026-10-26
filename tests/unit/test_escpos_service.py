"""Unit tests for the pure escpos_service helpers (text formatting and images)."""
import pytest
from PIL import Image

from src.services import escpos_service as escpos

GS_V_0 = b"\x1d\x76\x30\x00"
WHITE = 255
BLACK = 0


# ---------------------------------------------------------------------------
# Text formatting
# ---------------------------------------------------------------------------

class TestFormatSpecialText:
    def test_format_special_text_fits_pads_exactly_to_width(self):
        line = escpos.format_special_text("TOTAL", "$10.00", 48)
        assert line == "TOTAL" + " " * 37 + "$10.00"
        assert len(line) == 48

    def test_format_special_text_exact_fit_has_no_gap(self):
        assert escpos.format_special_text("AB", "CD", 4) == "ABCD"

    def test_format_special_text_too_long_truncates_text2(self):
        line = escpos.format_special_text("A" * 40, "B" * 20, 48)
        assert line == "A" * 40 + "B" * 8
        assert len(line) == 48

    def test_format_special_text_text1_wider_than_width_keeps_text2_fragment(self):
        # documents current behavior: when text1 alone exceeds the width,
        # `text2[:width - len(text1)]` slices with a NEGATIVE index, so a
        # fragment of text2 survives and the line overflows (expected: text2
        # dropped, i.e. "A" * 50). See escpos_service.py format_special_text.
        line = escpos.format_special_text("A" * 50, "XYZ", 48)
        assert line == "A" * 50 + "X"
        assert len(line) == 51


class TestFormatTableItem:
    @pytest.mark.parametrize(
        "width, cols",
        [(100, (15, 45, 20, 20)), (48, (7, 21, 9, 9)), (32, (4, 14, 6, 6))],
    )
    def test_format_table_item_column_widths_and_justification(self, width, cols):
        qty_w, item_w, price_w, imp_w = cols
        line = escpos.format_table_item(2, "Taco", "10.00", "20.00", width)
        assert len(line) == sum(cols)
        a, b, c = qty_w, qty_w + item_w, qty_w + item_w + price_w
        assert line[:a] == "2".ljust(qty_w)          # qty: left
        assert line[a:b] == "Taco".ljust(item_w)     # product: left
        assert line[b:c] == "10.00".rjust(price_w)   # price: right
        assert line[c:] == "20.00".rjust(imp_w)      # amount: right

    def test_format_table_item_non_string_values_are_stringified(self):
        line = escpos.format_table_item(3, 101, 10.5, 31.5, 100)
        assert line == "3".ljust(15) + "101".ljust(45) + "10.5".rjust(20) + "31.5".rjust(20)

    def test_format_table_item_long_product_is_not_truncated(self):
        # documents current behavior: ljust never truncates, so a product name
        # wider than its column pushes the price/amount columns to the right.
        line = escpos.format_table_item(1, "P" * 30, "1.00", "1.00", 48)
        assert line == "1".ljust(7) + "P" * 30 + "1.00".rjust(9) + "1.00".rjust(9)
        assert len(line) > 48


@pytest.mark.parametrize("width", [48, 32, 1])
def test_get_separator_returns_dashes_and_newline(width):
    assert escpos.get_separator(width) == "-" * width + "\n"


def test_feed_and_cut_returns_four_newlines_and_full_cut():
    assert escpos.feed_and_cut() == b"\n\n\n\n" + b"\x1d\x56\x00"


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

class TestImageToBw:
    def test_image_to_bw_rgba_transparency_becomes_white(self):
        image = Image.new("RGBA", (2, 1))
        image.putpixel((0, 0), (0, 0, 0, 0))      # fully transparent black
        image.putpixel((1, 0), (0, 0, 0, 255))    # opaque black
        bw = escpos.image_to_bw(image)
        assert bw.mode == "1"
        assert bw.size == (2, 1)
        assert bw.getpixel((0, 0)) == WHITE
        assert bw.getpixel((1, 0)) == BLACK

    def test_image_to_bw_rgb_threshold_is_strictly_greater(self):
        image = Image.new("RGB", (3, 1))
        image.putpixel((0, 0), (199, 199, 199))
        image.putpixel((1, 0), (200, 200, 200))
        image.putpixel((2, 0), (201, 201, 201))
        bw = escpos.image_to_bw(image, threshold=200)
        assert bw.mode == "1"
        assert [bw.getpixel((x, 0)) for x in range(3)] == [BLACK, BLACK, WHITE]

    def test_image_to_bw_custom_threshold_and_non_rgb_mode(self):
        image = Image.new("L", (2, 1))
        image.putpixel((0, 0), 90)
        image.putpixel((1, 0), 150)
        bw = escpos.image_to_bw(image, threshold=100)
        assert bw.mode == "1"
        assert [bw.getpixel((x, 0)) for x in range(2)] == [BLACK, WHITE]


@pytest.mark.parametrize(
    "size, target_width, expected",
    [((100, 50), 40, (40, 20)), ((30, 10), 576, (576, 192)), ((8, 8), 16, (16, 16))],
)
def test_resize_image_preserves_aspect_ratio(size, target_width, expected):
    image = Image.new("1", size, WHITE)
    resized = escpos.resize_image(image, target_width)
    assert resized.size == expected
    assert resized.mode == "1"


class TestPadLeftToCenter:
    def test_pad_left_to_center_adds_white_left_margin_only(self):
        image = Image.new("1", (8, 2), BLACK)
        padded = escpos.pad_left_to_center(image, 24)
        assert padded.size == (8 + 8, 2)  # offset (24 - 8) // 2, no right margin
        assert padded.getpixel((0, 0)) == WHITE
        assert padded.getpixel((7, 1)) == WHITE
        assert padded.getpixel((8, 0)) == BLACK
        assert padded.getpixel((15, 1)) == BLACK

    def test_pad_left_to_center_wide_image_returned_unchanged(self):
        image = Image.new("1", (24, 1), BLACK)
        assert escpos.pad_left_to_center(image, 24) is image
        assert escpos.pad_left_to_center(image, None) is image


class TestConvertImageToEscpos:
    def test_convert_single_band_header_and_bits(self):
        image = Image.new("1", (8, 2), WHITE)
        image.putpixel((0, 0), BLACK)   # MSB of row 0
        image.putpixel((7, 1), BLACK)   # LSB of row 1
        data = escpos.convert_image_to_escpos_format(image)
        assert data[:4] == GS_V_0
        assert data[4:8] == bytes([1, 0, 2, 0])  # xL=1 byte/row, xH=0, yL=2 rows, yH=0
        assert data[8:] == bytes([0x80, 0x01])
        assert len(data) == 8 + 1 * 2
        assert data.count(GS_V_0) == 1

    def test_convert_partial_byte_row_pads_with_unset_bits(self):
        image = Image.new("1", (10, 1), BLACK)
        data = escpos.convert_image_to_escpos_format(image)
        assert data[4:8] == bytes([2, 0, 1, 0])  # (10 + 7) // 8 = 2 bytes per row
        assert data[8:] == bytes([0xFF, 0xC0])
        assert len(data) == 8 + 2

    def test_convert_wide_row_sets_xh(self):
        image = Image.new("1", (2056, 1), WHITE)  # 257 bytes per row
        data = escpos.convert_image_to_escpos_format(image)
        assert data[4:8] == bytes([1, 1, 1, 0])   # 257 = 0x0101 -> xL=1, xH=1
        assert len(data) == 8 + 257

    def test_convert_small_max_band_bytes_splits_into_bands(self):
        image = Image.new("1", (8, 4), WHITE)
        data = escpos.convert_image_to_escpos_format(image, max_band_bytes=2)
        assert data.count(GS_V_0) == 2
        first = data.index(GS_V_0)
        second = data.index(GS_V_0, first + 1)
        assert data[first + 4:first + 8] == bytes([1, 0, 2, 0])
        assert data[second + 4:second + 8] == bytes([1, 0, 2, 0])
        assert len(data) == 2 * 8 + 1 * 4

    def test_convert_explicit_band_height_last_band_is_remainder(self):
        image = Image.new("1", (8, 4), WHITE)
        data = escpos.convert_image_to_escpos_format(image, band_height=3)
        assert data.count(GS_V_0) == 2
        second = data.index(GS_V_0, 1)
        assert data[4:8] == bytes([1, 0, 3, 0])
        assert data[second + 4:second + 8] == bytes([1, 0, 1, 0])
        assert len(data) == 2 * 8 + 4

    def test_convert_default_bands_stay_within_max_band_bytes(self):
        image = Image.new("1", (576, 30), WHITE)  # 72 bytes/row -> 1024 // 72 = 14 rows
        data = escpos.convert_image_to_escpos_format(image)
        assert data.count(GS_V_0) == 3            # 14 + 14 + 2 rows
        assert len(data) == 3 * 8 + 72 * 30
        assert 72 * 14 <= escpos.MAX_BAND_BYTES
