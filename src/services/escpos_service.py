"""Platform-independent ESC/POS helpers.

This module only builds ESC/POS byte streams and formats text/images. All
OS-specific I/O (discovering printers, writing raw bytes) is delegated to the
platform backend in `src.printers`, so the same code runs on Windows and macOS.
"""
import base64
import io

from PIL import Image

from src.printers import get_backend


# ---------------------------------------------------------------------------
# Platform I/O (delegated to the active backend)
# ---------------------------------------------------------------------------

def list_printers():
    """Return the names of the available printers on this machine."""
    return get_backend().list_printers()


def get_printer_width(printer_name):
    """Resolve the printer width in characters for the current platform."""
    return get_backend().get_printer_width(printer_name)


def send_raw(printer_name, data):
    """Send a pre-built ESC/POS byte stream as a single RAW job."""
    get_backend().send_raw(printer_name, data)


def print_pdf(printer_name, pdf_bytes, options=None):
    """Print a PDF document via the OS print system."""
    get_backend().print_pdf(printer_name, pdf_bytes, options)


def native_pdf_supported():
    """True if the current platform's print system renders PDFs natively."""
    return get_backend().native_pdf


def send_to_printer(printer_name, data):
    """Send text (str) to the printer as a RAW ESC/POS job."""
    line_height_command = b'\x1b\x33\x42'  # ESC 3 -> set line height
    # latin1 encoding preserves accented characters
    payload = line_height_command + data.encode('latin1')
    get_backend().send_raw(printer_name, payload)


def send_image_to_printer(printer_name, image_data):
    """Send an ESC/POS image byte stream to the printer as a RAW job."""
    line_height_command = b'\x1b\x33\x00'
    center_command = b'\x1b\x61\x01'
    payload = line_height_command + center_command + image_data
    get_backend().send_raw(printer_name, payload)


# ---------------------------------------------------------------------------
# ESC/POS control commands
# ---------------------------------------------------------------------------

CUT_FEED = b'\n\n\n\n'      # advance the paper so the content clears the cutter
FULL_CUT = b'\x1d\x56\x00'  # GS V 0 -> full paper cut


def feed_and_cut():
    """Return the ESC/POS bytes that advance the paper and perform a full cut."""
    return CUT_FEED + FULL_CUT


# ---------------------------------------------------------------------------
# Image conversion (pure)
# ---------------------------------------------------------------------------

def image_to_bw(image, threshold=200):
    """Flatten transparency and threshold a PIL image to a 1-bit bitmap ('1')."""
    # Handle transparency by flattening it onto a white background
    if image.mode == 'RGBA':
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, (0, 0), image)
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')

    image_gray = image.convert('L')
    image_bw = image_gray.point(lambda p: 255 if p > threshold else 0)
    return image_bw.convert('1')


def image_base64_to_bitmap(image_base64, threshold=200):
    try:
        image_data = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_data))
        return image_to_bw(image, threshold)
    except Exception as e:
        print(f"Error al convertir la imagen base64: {e}")
        return None


def pdf_to_escpos(pdf_bytes, width_dots=576, threshold=200):
    """Rasterize a PDF into an ESC/POS image byte stream (one block per page).

    Used on platforms without native PDF printing (Windows): each page is
    rendered to `width_dots` wide, converted to black & white and emitted as an
    ESC/POS raster image. Requires PyMuPDF (`pip install PyMuPDF`).
    """
    try:
        import fitz  # PyMuPDF (optional dependency)
    except ImportError as e:
        raise ImportError(
            "PDF rasterization requires PyMuPDF. Install it with: pip install PyMuPDF"
        ) from e

    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    try:
        out = bytearray()
        out += b'\x1b\x33\x00'  # tight line height
        out += b'\x1b\x61\x01'  # center
        for page in doc:
            zoom = width_dots / page.rect.width if page.rect.width else 1
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            image_bw = image_to_bw(image, threshold)
            if image_bw.width != width_dots:
                image_bw = resize_image(image_bw, width_dots)
            out += convert_image_to_escpos_format(image_bw)
            out += b'\n'
        return bytes(out)
    finally:
        doc.close()


def resize_image(image, target_width):
    aspect_ratio = image.height / image.width
    target_height = int(target_width * aspect_ratio)
    return image.resize((target_width, target_height), Image.NEAREST)


# Font A is 12 x 24 dots, so the text columns times the character width give the
# printable dots: 48 cols -> 576 (80 mm paper) and 32 -> 384 (58 mm).
DOTS_PER_CHAR = 12

# Data cap per GS v 0 command. Measured, not guessed: on a POS80 a single command
# carrying 2 304 bytes derails the printer (it stops counting the bytes the
# command declared and spits the rest out as text), while 1 152 bytes print fine.
# The cap leaves margin and slices by BYTES rather than rows because the limit is
# the buffer: a wider image needs shorter bands than a narrow one.
MAX_BAND_BYTES = 1024


def pad_left_to_center(image_bw, printable_dots):
    """Pad the image on the LEFT with white so it prints centered.

    Image centering is NOT delegated to `ESC a 1`: on the POS80 we tested, the
    same image came out centered when it was short and flush left when it was
    tall — the alignment is lost as soon as the printer runs tight on buffer.
    Baking the margin into the pixels makes the position independent of whatever
    the firmware remembers.

    Only the LEFT side is padded: trailing white adds nothing and every dot is
    more bytes to travel and for the printer to swallow.
    """
    if not printable_dots or image_bw.width >= printable_dots:
        return image_bw

    offset = (printable_dots - image_bw.width) // 2
    # 255 = white. In mode '1' Pillow accepts both 1 and 255 as white but keeps
    # the raw value in the pixels: with 1, any later convert('L') or comparison
    # against 255 would surprise the reader. With 255 the margin is white no
    # matter who looks at it.
    canvas = Image.new('1', (image_bw.width + offset, image_bw.height), 255)
    canvas.paste(image_bw, (offset, 0))
    return canvas


def convert_image_to_escpos_format(image_bw, band_height=None, max_band_bytes=None):
    """Encode a 1-bit PIL image as a GS v 0 raster bit image (ESC/POS standard).

    GS v 0 is the modern raster command supported across ESC/POS printers
    (Epson, BIXOLON, etc.). We used to emit the legacy `ESC *` bit-image mode,
    but some firmware (e.g. BIXOLON SRP-330II) silently ignores it — the paper
    feeds and cuts but no dots are printed. GS v 0 renders reliably everywhere.

    The image is emitted in horizontal bands so a tall receipt stays within the
    printer's raster buffer. A set bit means "print a dot"; in a mode '1' image
    a pixel value of 0 is black, so black pixels become set bits.

    BAND SIZE — why ~1 KB per command and not the 255 rows the command allows:
    the printer must hold the WHOLE band before it prints anything, and a cheap
    80 mm head has a few KB of buffer. A 384 x 240 logo in one band is a single
    command carrying 11 520 bytes; when the buffer fills, the printer drops what
    it cannot take, loses count of the bytes the command declared and prints the
    REST OF THE RASTER AS TEXT — a wall of `y` characters instead of a logo (and
    it fails intermittently, which is worse). Measured on a POS80: 2 304 bytes in
    one command fail, 1 152 print fine. The band is computed from the row width
    so a wider image gets fewer rows per command; the extra cost is 8 bytes of
    header per band.
    """
    width, height = image_bw.size
    pixels = image_bw.load()
    bytes_per_row = (width + 7) // 8
    xL, xH = bytes_per_row & 0xFF, (bytes_per_row >> 8) & 0xFF

    if band_height is None:
        budget = max_band_bytes or MAX_BAND_BYTES
        band_height = max(1, min(255, budget // max(1, bytes_per_row)))

    out = bytearray()
    for band_start in range(0, height, band_height):
        band = min(band_height, height - band_start)
        out += b'\x1d\x76\x30\x00'  # GS v 0, m=0 (normal density)
        out += bytes([xL, xH, band & 0xFF, (band >> 8) & 0xFF])
        for y in range(band_start, band_start + band):
            for byte_index in range(bytes_per_row):
                byte = 0
                for bit in range(8):
                    x = byte_index * 8 + bit
                    if x < width and pixels[x, y] == 0:
                        byte |= 1 << (7 - bit)
                out.append(byte)
    return bytes(out)


def image_to_base64(image_path):
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except FileNotFoundError:
        print(f"Archivo no encontrado: {image_path}")
        return None
    except Exception as e:
        print(f"Error al leer la imagen: {e}")
        return None


# ---------------------------------------------------------------------------
# Text formatting (pure)
# ---------------------------------------------------------------------------

def format_table_item(qty, item, price, importe, width):
    qty = str(qty)
    item = str(item)
    price = str(price)
    importe = str(importe)

    qty_col_width = int(width * 0.15)
    item_col_width = int(width * 0.45)
    price_col_width = int(width * 0.20)
    importe_col_width = int(width * 0.20)

    qty_col = qty.ljust(qty_col_width)
    item_col = item.ljust(item_col_width)
    price_col = price.rjust(price_col_width)
    importe_col = importe.rjust(importe_col_width)

    return f"{qty_col}{item_col}{price_col}{importe_col}"


def format_special_text(text1, text2, width):
    total_length = len(text1) + len(text2)
    if total_length > width:
        text2 = text2[:width - len(text1)]

    space_between = width - len(text1) - len(text2)
    return text1 + (' ' * space_between) + text2


def get_separator(width):
    return "-" * width + "\n"
