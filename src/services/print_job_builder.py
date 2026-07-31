"""Intermediate layer that assembles a whole ticket into a single ESC/POS byte
stream, so the entire job is sent to the printer in ONE call (one spooler job).

Text/tables/separators are appended as latin1 bytes; images are appended as raw
ESC/POS bytes. Each piece carries its own control commands inline, which is
harmless mid-stream. Call `to_bytes()` once and send it with a single send_raw.
"""
from src.services import escpos_service as escpos

# Control commands
LINE_HEIGHT_TEXT = b'\x1b\x33\x42'   # ESC 3 n -> line height for text
LINE_HEIGHT_IMAGE = b'\x1b\x33\x00'  # ESC 3 0 -> tight line height for images
ALIGN_LEFT = b'\x1b\x61\x00'
ALIGN_CENTER = b'\x1b\x61\x01'
FONT_NORMAL = b'\x1D\x21\x00'
FONT_MD = b'\x1D\x21\x11'  # double width and height
FONT_LG = b'\x1D\x21\x22'  # triple width and height
FULL_CUT = b'\x1d\x56\x00'
OPEN_DRAWER = b'\x1B\x70\x00\x19\xFA'
HIGH_CONTRAST_ON = b'\x1D\x42\x01'   # GS B 1 -> reverse (black background, white text)
HIGH_CONTRAST_OFF = b'\x1D\x42\x00'  # GS B 0 -> normal
BOLD_ON = b'\x1B\x45\x01'    # ESC E 1 -> emphasized (bold)
BOLD_OFF = b'\x1B\x45\x00'   # ESC E 0 -> normal weight

# ESC M n selects the printer's built-in typeface. Narrower typefaces fit more
# columns on the same physical line; the ratio rescales self.width (Font A base).
TYPEFACES = {
    'a': (b'\x1B\x4D\x00', (1, 1)),   # Font A 12x24 (default) -> 48/32 cols
    'b': (b'\x1B\x4D\x01', (4, 3)),   # Font B 9x17  -> 64/42 cols
    'c': (b'\x1B\x4D\x02', (3, 2)),   # Font C 8x16  -> 72/48 cols (limited firmware support)
}
TYPEFACE_RESET = b'\x1B\x4D\x00'      # back to Font A


class PrintJobBuilder:
    def __init__(self, width):
        self.width = width
        self._buf = bytearray()
        # Set the text line height once at the start of the job.
        self._buf += LINE_HEIGHT_TEXT

    # -- low level -------------------------------------------------------
    def _add_str(self, text):
        # latin1 preserves accented characters / ñ
        self._buf += text.encode('latin1')

    # -- content pieces --------------------------------------------------
    def _typeface(self, font):
        """Normalize the requested font; unknown values fall back to Font A."""
        font = str(font or 'a').strip().lower()
        return font if font in TYPEFACES else 'a'

    def _base_width(self, font):
        """Columns available on a line for the given typeface (narrower = more)."""
        num, den = TYPEFACES[font][1]
        return (self.width * num) // den

    def add_text(self, text, align='left', font_size='normal', high_contrast=False,
                 font_weight='normal', font='a'):
        # Mode commands are emitted ONLY when they differ from the default, so
        # existing payloads keep producing byte-identical output.
        bold = font_weight == 'bold'
        font = self._typeface(font)
        if font != 'a':
            self._buf += TYPEFACES[font][0]

        if font_size == 'md':
            self._buf += FONT_MD
            scale = 2  # 'md' = doble ancho: cada carácter ocupa 2 columnas
        elif font_size == 'lg':
            self._buf += FONT_LG
            scale = 3  # 'lg' = triple ancho
        else:
            self._buf += FONT_NORMAL
            scale = 1

        if bold:
            self._buf += BOLD_ON

        # El ancho efectivo en caracteres se reduce según el tamaño de fuente,
        # porque el relleno (espacios) también se imprime a ese ancho. Si se
        # usara self.width sin escalar, el texto en 'md'/'lg' se desborda y salta
        # de línea (aparece corrido a la derecha y parte se va al renglón de abajo).
        # Las fuentes B/C son más angostas: amplían la base de columnas antes de escalar.
        width = max(1, self._base_width(font) // scale)

        if high_contrast:
            # Reverse-video (GS B) only wraps the text plus a 1-space margin on
            # each side; the alignment padding stays outside the block so it
            # prints white. GS B is a print mode: it emits no columns, so the
            # column count is computed exactly as in the normal path.
            block = ' ' + text + ' '
            if len(block) > width:  # no room for margins: don't truncate the text
                block = text
            pad_total = max(0, width - len(block))
            if align == 'center':
                left, right = pad_total // 2 + pad_total % 2, pad_total // 2
            elif align == 'right':
                left, right = pad_total, 0
            else:
                left, right = 0, pad_total
            self._add_str(' ' * left)
            self._buf += HIGH_CONTRAST_ON
            self._add_str(block)
            self._buf += HIGH_CONTRAST_OFF  # always OFF before the newline: no leak
            self._add_str(' ' * right)
        else:
            if align == 'center':
                text = text.center(width)
            elif align == 'right':
                text = text.rjust(width)
            else:
                text = text.ljust(width)
            self._add_str(text)

        if bold:
            self._buf += BOLD_OFF
        self._buf += FONT_NORMAL  # reset font size to normal
        if font != 'a':
            self._buf += TYPEFACE_RESET  # back to Font A: no mode leaks past the item
        self._add_str('\n')

    def add_special_text(self, text1, text2, high_contrast=False, font_weight='normal',
                         font='a', font_size='normal'):
        bold = font_weight == 'bold'
        font = self._typeface(font)
        if font != 'a':
            self._buf += TYPEFACES[font][0]

        if font_size == 'md':
            self._buf += FONT_MD
            scale = 2
        elif font_size == 'lg':
            self._buf += FONT_LG
            scale = 3
        else:
            self._buf += FONT_NORMAL
            scale = 1

        width = max(1, self._base_width(font) // scale)
        line = escpos.format_special_text(text1, text2, width)

        if bold:
            self._buf += BOLD_ON
        if high_contrast:
            # Reverse-video wraps the whole formatted line (full 48/32 columns);
            # OFF is emitted before the newline so no state leaks to the next item.
            self._buf += HIGH_CONTRAST_ON
            self._add_str(line)
            self._buf += HIGH_CONTRAST_OFF
        else:
            self._add_str(line)
        if bold:
            self._buf += BOLD_OFF
        self._buf += FONT_NORMAL
        if font != 'a':
            self._buf += TYPEFACE_RESET
        self._add_str('\n')

    def add_table(self, rows):
        width = self.width
        header = (
            "Cant.".ljust(int(width * 0.15))
            + "Producto".ljust(int(width * 0.45))
            + "Precio".rjust(int(width * 0.20))
            + "Importe".rjust(int(width * 0.20))
            + "\n"
            + "-" * width + "\n"
        )
        table_string = "\n" + header
        for row in rows:
            table_string += escpos.format_table_item(row[0], row[1], row[2], row[3], width) + "\n"
        self._add_str(table_string + "\n")

    def add_separator(self):
        self._add_str(escpos.get_separator(self.width))

    def add_image(self, image_data):
        # Switch to image mode (tight line height, centered), then restore text.
        self._buf += LINE_HEIGHT_IMAGE + ALIGN_CENTER
        self._buf += image_data
        self._add_str('\n')
        self._buf += LINE_HEIGHT_TEXT + ALIGN_LEFT

    def add_feed_and_cut(self):
        self._add_str("\n\n\n\n")  # advance paper before cutting
        self._buf += FULL_CUT

    def add_open_drawer(self):
        self._buf += OPEN_DRAWER

    # -- output ----------------------------------------------------------
    def to_bytes(self):
        return bytes(self._buf)
