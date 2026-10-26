"""Ticket -> PDF renderer: lays out RAW ticket items with PyMuPDF (TextWriter +
page drawing primitives). Pure: returns bytes, never touches printers.

Two phases:

  1. measure: walk the items, compute absolute positions (points) and collect
     drawing operations;
  2. paint: create ONE page whose height is exactly the content height and
     replay the operations (shapes/images/embedded PDFs in order, then the text
     grouped by color, one TextWriter per color).

Drawing operations collected by the measuring phase:

    ('rect',  fitz.Rect, fill_rgb)                             # inverted blocks
    ('line',  (x0, y0), (x1, y1), width_pt, dashes|None, rgb)  # separators, rules, underlines
    ('text',  x, baseline_y, text, face, size, rgb)            # painted with TextWriter
    ('image', fitz.Rect, png_bytes)
    ('pdf',   fitz.Rect, pdf_bytes)                            # html blocks (fitz.Story)

Fonts come from the system catalog (`font_service`) or from PyMuPDF's Base-14
fonts (`sans-serif`, `serif`, `monospace`), which always exist.
"""
import base64
import io
import math

import fitz
from PIL import Image

from src.services import font_service
from src.utils.coerce import truthy

MM_PT = 72.0 / 25.4
DOTS_PER_MM = 8
KEYWORD_SIZE_SCALE = {'normal': 1, 'md': 2, 'lg': 3}
BUILTIN_GENERIC = {'sans-serif': 'helv', 'serif': 'tiro', 'monospace': 'cour'}
BUILTIN_BY_NAME = {'helvetica': 'helv', 'arial': 'helv', 'times': 'tiro',
                   'times new roman': 'tiro', 'courier': 'cour', 'courier new': 'cour'}
BUILTIN_VARIANTS = {   # base -> {(bold, italic): fitz fontname}
    'helv': {(False, False): 'helv', (True, False): 'hebo', (False, True): 'heit', (True, True): 'hebi'},
    'tiro': {(False, False): 'tiro', (True, False): 'tibo', (False, True): 'tiit', (True, True): 'tibi'},
    'cour': {(False, False): 'cour', (True, False): 'cobo', (False, True): 'coit', (True, True): 'cobi'},
}
DEFAULT_COLUMNS = [
    {'label': 'Cant.', 'width': 15, 'align': 'left'},
    {'label': 'Producto', 'width': 45, 'align': 'left'},
    {'label': 'Precio', 'width': 20, 'align': 'right'},
    {'label': 'Importe', 'width': 20, 'align': 'right'},
]
SEPARATOR_BLOCK_MM = 2.0          # vertical space a separator occupies (line in the middle)
SEPARATOR_DASHES = {'dashed': '[2 1.5] 0', 'dotted': '[0.6 1.2] 0', 'solid': None, 'double': None}
CELL_PADDING_MM = 0.5
SPECIAL_TEXT_GAP_MM = 2.0
SPECIAL_TEXT_RIGHT_MAX = 0.6      # text2 may use at most 60% of the width
FAKE_BOLD_OFFSET = 0.035          # × fontsize, in pt
UNDERLINE_OFFSET = 0.12           # × fontsize below the baseline
UNDERLINE_WIDTH = 0.06            # × fontsize
HTML_MAX_HEIGHT_PT = 20000

# Defaults of the normalized options (section 6.4.1 of TASK-005).
DEFAULT_WIDTH_MM = 72.0
DEFAULT_MARGINS_MM = {'top': 1.0, 'right': 1.0, 'bottom': 3.0, 'left': 1.0}
DEFAULT_FONT_FAMILY = 'sans-serif'
DEFAULT_FONT_SIZE = 9.0
DEFAULT_LINE_HEIGHT = 1.25
DEFAULT_MAX_HEIGHT_MM = 1000.0
DEFAULT_MAX_IMAGE_HEIGHT_DOTS = 600
DEFAULT_IMAGE_WIDTH_DOTS = 384

FONT_SIZE_RANGE = (4.0, 72.0)
LINE_HEIGHT_RANGE = (0.8, 3.0)
SEPARATOR_THICKNESS = 0.6
SEPARATOR_THICKNESS_RANGE = (0.2, 3.0)
SEPARATOR_DOUBLE_OFFSET_PT = 0.6  # each line of a 'double' separator, from the middle
TABLE_RULE_WIDTH_PT = 0.4         # line under the table header
TABLE_RULE_OFFSET_MM = 0.5        # ... drawn this far below the header row
TABLE_HEADER_GAP_MM = 1.0         # ... and the body starts this far below the header row
SPACER_MAX_MM = 200.0

BLACK = (0.0, 0.0, 0.0)
WHITE = (1.0, 1.0, 1.0)
FONT_SIZE_ERROR = "'font.size' must be a number between 4 and 72."

_FIT_EPSILON = 0.01               # pt; float noise in text_length must not force a wrap
_GENERIC_BY_BASE = {base: generic for generic, base in BUILTIN_GENERIC.items()}


# ---------------------------------------------------------------------------
# Value coercion (items come straight from the JSON payload)
# ---------------------------------------------------------------------------

def _number(value):
    """float(value) for numbers and numeric strings; None for anything else (bools included)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _in_range(value, bounds, default):
    """The number in `value` if it lies within `bounds` (inclusive), else `default`."""
    number = _number(value)
    return number if number is not None and bounds[0] <= number <= bounds[1] else default


def _non_negative(value, default):
    number = _number(value)
    return number if number is not None and number >= 0 else default


def _positive(value, default):
    number = _number(value)
    return number if number is not None and number > 0 else default


def _keyword(value):
    return str(value).strip().lower() if value is not None else ''


def _align(value, default='left'):
    align = _keyword(value)
    return align if align in ('left', 'center', 'right') else default


def _add_warning(warnings, message):
    if message not in warnings:
        warnings.append(message)


def _normalize_options(options):
    """Fill the defaults of section 6.4.1 and validate `font.size` (ValueError)."""
    options = options if isinstance(options, dict) else {}
    font = options.get('font') if isinstance(options.get('font'), dict) else {}

    size = DEFAULT_FONT_SIZE
    if font.get('size') is not None:
        size = _number(font.get('size'))
        if size is None or not FONT_SIZE_RANGE[0] <= size <= FONT_SIZE_RANGE[1]:
            raise ValueError(FONT_SIZE_ERROR)

    raw_margins = options.get('margins_mm') if isinstance(options.get('margins_mm'), dict) else {}
    margins = {side: _non_negative(raw_margins.get(side), default)
               for side, default in DEFAULT_MARGINS_MM.items()}

    return {
        'width_mm': _positive(options.get('width_mm'), DEFAULT_WIDTH_MM),
        'margins_mm': margins,
        'font': {
            'family': str(font.get('family') or '').strip() or DEFAULT_FONT_FAMILY,
            'size': size,
            'line_height': _in_range(font.get('line_height'), LINE_HEIGHT_RANGE, DEFAULT_LINE_HEIGHT),
        },
        'max_height_mm': _positive(options.get('max_height_mm'), DEFAULT_MAX_HEIGHT_MM),
        'max_image_height_dots': int(_positive(options.get('max_image_height_dots'),
                                               DEFAULT_MAX_IMAGE_HEIGHT_DOTS)),
    }


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

class Face:
    """A resolved typeface: the fitz.Font used for layout and painting, plus its provenance.

    `family`, `bold` and `italic` are what the item asked for; `resolved` is the
    face actually used and `source` is 'system' | 'builtin' | 'fallback'.
    `fake_bold` means bold was requested but the family has no bold face (the
    text is painted twice, slightly offset). `font_bytes` and `system_face`
    (the font_service face dict) only exist for system faces; `css_family` is
    the family name an html block uses to refer to this face.
    """

    def __init__(self, font, family, resolved, source, bold=False, italic=False,
                 fake_bold=False, font_bytes=None, system_face=None, css_family=None):
        self.font = font
        self.family = family
        self.resolved = resolved
        self.source = source
        self.bold = bold
        self.italic = italic
        self.fake_bold = fake_bold
        self.font_bytes = font_bytes
        self.system_face = system_face
        self.css_family = css_family

    def __repr__(self):
        return f"Face({self.family!r} -> {self.resolved!r}, {self.source}, bold={self.bold}, italic={self.italic})"


class FontSet:
    """Resolves and caches faces by (family_key, bold, italic) for one ticket.

    `warnings` collects user-facing notes (missing styles, fallbacks) and
    `used` lists every distinct face requested (-> `data.fonts`).
    """

    def __init__(self, default_family, warnings=None):
        self.default_family = str(default_family or '').strip() or DEFAULT_FONT_FAMILY
        self.warnings = [] if warnings is None else warnings
        self.used = []
        self._faces = {}
        self._builtin_fonts = {}

    def resolve(self, family=None, bold=False, italic=False):
        """Face for `family` (the default family when empty) in the requested style."""
        name = str(family).strip() if family is not None else ''
        name = name or self.default_family
        bold, italic = bool(bold), bool(italic)
        key = (name.lower(), bold, italic)
        face = self._faces.get(key)
        if face is None:
            face = self._load(name, bold, italic)
            self._faces[key] = face
            self._register(face)
        return face

    def system_faces(self):
        """Resolved system faces, unique by (installed family, bold, italic) of the font program."""
        seen, faces = set(), []
        for face in self._faces.values():
            if face.source != 'system':
                continue
            key = (face.css_family, face.system_face['bold'], face.system_face['italic'])
            if key not in seen:
                seen.add(key)
                faces.append(face)
        return faces

    def _load(self, name, bold, italic):
        key = name.lower()
        if key in BUILTIN_GENERIC:
            return self._builtin(name, BUILTIN_GENERIC[key], bold, italic, 'builtin')

        face, note = font_service.resolve_face(name, bold, italic)
        if face is not None:
            try:
                data = font_service.load_face_bytes(face)
                font = fitz.Font(fontbuffer=data)
            except Exception:
                face = None   # vanished or unreadable since the scan: treat as not installed
            else:
                if note:
                    _add_warning(self.warnings, note)
                return Face(font, name, face['full_name'], 'system', bold, italic,
                            fake_bold=bold and not face['bold'], font_bytes=data,
                            system_face=face, css_family=face['family'])

        if key in BUILTIN_BY_NAME:
            return self._builtin(name, BUILTIN_BY_NAME[key], bold, italic, 'builtin')
        _add_warning(self.warnings, f"Font family '{name}' is not installed; using sans-serif.")
        return self._builtin(name, 'helv', bold, italic, 'fallback')

    def _builtin(self, name, base, bold, italic, source):
        fontname = BUILTIN_VARIANTS[base][(bold, italic)]
        font = self._builtin_fonts.get(fontname)
        if font is None:
            font = self._builtin_fonts[fontname] = fitz.Font(fontname)
        return Face(font, name, font.name, source, bold, italic, css_family=_GENERIC_BY_BASE[base])

    def _register(self, face):
        entry = {'family': face.family, 'resolved': face.resolved, 'source': face.source,
                 'bold': face.bold, 'italic': face.italic}
        if entry not in self.used:
            self.used.append(entry)


# ---------------------------------------------------------------------------
# Text measurement
# ---------------------------------------------------------------------------

def line_height_pt(size, line_height):
    return size * line_height


def baseline_offset(face, size, lh_pt):
    """Distance from the top of a line box to the baseline (centers the glyph box)."""
    glyph_box = size * (face.font.ascender - face.font.descender)   # descender < 0
    return size * face.font.ascender + max(0.0, (lh_pt - glyph_box) / 2.0)


def text_width(face, size, text):
    return face.font.text_length(text, fontsize=size)


def _fits(face, size, text, max_width):
    return text_width(face, size, text) <= max_width + _FIT_EPSILON


def _longest_fitting_prefix(word, face, size, max_width):
    """Length of the longest prefix of `word` that fits (at least 1 char)."""
    lo, hi = 1, len(word)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _fits(face, size, word[:mid], max_width):
            lo = mid
        else:
            hi = mid - 1
    return lo


def _wrap_paragraph(paragraph, face, size, max_width):
    if _fits(face, size, paragraph, max_width):
        return [paragraph]
    lines, line = [], ''
    for word in paragraph.split(' '):
        candidate = f'{line} {word}' if line else word
        if _fits(face, size, candidate, max_width):
            line = candidate
            continue
        if line:
            lines.append(line.rstrip(' '))
        while word and not _fits(face, size, word, max_width):
            cut = _longest_fitting_prefix(word, face, size, max_width)
            lines.append(word[:cut])
            word = word[cut:]
        line = word
    if line or not lines:
        lines.append(line)
    return lines


def wrap_text(text, face, size, max_width):
    """Greedy word wrap honoring '\n'. Words wider than max_width are split by
    characters (largest prefix that fits, at least 1 char). Returns list[str]
    (an empty paragraph yields ['']). Never returns [] ."""
    text = '' if text is None else str(text)
    lines = []
    for paragraph in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        lines.extend(_wrap_paragraph(paragraph, face, size, max_width))
    return lines


def _aligned_x(left, width, text_w, align):
    if align == 'right':
        return left + width - text_w
    if align == 'center':
        return left + (width - text_w) / 2.0
    return left


# ---------------------------------------------------------------------------
# Layout (measuring phase)
# ---------------------------------------------------------------------------

class _Layout:
    """Mutable state of the measuring phase: cursor, geometry and collected ops."""

    def __init__(self, options, fonts):
        margins = options['margins_mm']
        self.width = options['width_mm'] * MM_PT
        self.x0 = margins['left'] * MM_PT
        self.avail = max(1.0, self.width - (margins['left'] + margins['right']) * MM_PT)
        self.y = margins['top'] * MM_PT
        self.bottom = margins['bottom'] * MM_PT
        self.base_size = options['font']['size']
        self.base_line_height = options['font']['line_height']
        self.max_image_height_dots = options['max_image_height_dots']
        self.fonts = fonts
        self.warnings = fonts.warnings
        self.ops = []
        self.open_drawer = False


def _item_font_size(value, base):
    """Keyword -> base × 1/2/3; number (or numeric string) -> pt clamped to 4-72; else base."""
    keyword = _keyword(value)
    if keyword in KEYWORD_SIZE_SCALE:
        return base * KEYWORD_SIZE_SCALE[keyword]
    number = _number(value)
    if number is None:
        return base
    return min(max(number, FONT_SIZE_RANGE[0]), FONT_SIZE_RANGE[1])


def _item_line_height(layout, item, size):
    return line_height_pt(size, _in_range(item.get('line_height'), LINE_HEIGHT_RANGE,
                                          layout.base_line_height))


def _text_style(layout, item):
    """(face, size, line height in pt) for a text / special_text item."""
    size = _item_font_size(item.get('font_size'), layout.base_size)
    face = layout.fonts.resolve(item.get('font_family'),
                                _keyword(item.get('font_weight')) == 'bold',
                                _keyword(item.get('font_style')) == 'italic')
    return face, size, _item_line_height(layout, item, size)


def _block_color(layout, item, height):
    """Text color of a block; a high_contrast block first gets a full-width black rect."""
    if not truthy(item.get('high_contrast')):
        return BLACK
    rect = fitz.Rect(layout.x0, layout.y, layout.x0 + layout.avail, layout.y + height)
    layout.ops.append(('rect', rect, BLACK))
    return WHITE


def _emit_text(layout, x, baseline, text, face, size, color, underline=False):
    if not text:
        return
    layout.ops.append(('text', x, baseline, text, face, size, color))
    if face.fake_bold:
        layout.ops.append(('text', x + FAKE_BOLD_OFFSET * size, baseline, text, face, size, color))
    if underline:
        y = baseline + size * UNDERLINE_OFFSET
        width = text_width(face, size, text)
        layout.ops.append(('line', (x, y), (x + width, y), size * UNDERLINE_WIDTH, None, color))


def _layout_text(layout, item, n):
    face, size, lh = _text_style(layout, item)
    lines = wrap_text(item.get('data'), face, size, layout.avail)
    height = len(lines) * lh
    color = _block_color(layout, item, height)
    align = _align(item.get('align'))
    underline = truthy(item.get('underline'))
    offset = baseline_offset(face, size, lh)
    for i, line in enumerate(lines):
        x = _aligned_x(layout.x0, layout.avail, text_width(face, size, line), align)
        _emit_text(layout, x, layout.y + i * lh + offset, line, face, size, color, underline)
    layout.y += height


def _layout_special_text(layout, item, n):
    data = item.get('data')
    if not isinstance(data, dict):
        return
    face, size, lh = _text_style(layout, item)
    lines2 = wrap_text(data.get('text2'), face, size, layout.avail * SPECIAL_TEXT_RIGHT_MAX)
    w2 = max(text_width(face, size, line) for line in lines2)
    width1 = max(1.0, layout.avail - w2 - SPECIAL_TEXT_GAP_MM * MM_PT)
    lines1 = wrap_text(data.get('text1'), face, size, width1)

    height = max(len(lines1), len(lines2)) * lh
    color = _block_color(layout, item, height)
    underline = truthy(item.get('underline'))
    offset = baseline_offset(face, size, lh)
    right = layout.x0 + layout.avail
    for i, line in enumerate(lines1):
        _emit_text(layout, layout.x0, layout.y + i * lh + offset, line, face, size, color, underline)
    for i, line in enumerate(lines2):
        x = right - text_width(face, size, line)
        _emit_text(layout, x, layout.y + i * lh + offset, line, face, size, color, underline)
    layout.y += height


def _table_columns(raw):
    """Normalized columns: labels as str, widths as percentages summing 100, valid aligns."""
    if not isinstance(raw, list) or not raw:
        raw = DEFAULT_COLUMNS
    columns = []
    for col in raw:
        if not isinstance(col, dict):
            col = {'label': col}
        label = col.get('label')
        columns.append({'label': '' if label is None else str(label),
                        'width': _positive(col.get('width'), None),
                        'align': _align(col.get('align'))})

    given = [col['width'] for col in columns if col['width']]
    missing = [col for col in columns if not col['width']]
    if missing:
        rest = 100.0 - sum(given)
        share = rest / len(missing) if rest > 0 else sum(given) / len(given)
        for col in missing:
            col['width'] = share
    total = sum(col['width'] for col in columns)
    for col in columns:
        col['width'] = col['width'] * 100.0 / total
    return columns


def _cell_text(row, index):
    if index >= len(row) or row[index] is None:
        return ''
    return str(row[index])


def _layout_table_row(layout, texts, columns, face, size, lh):
    pad = CELL_PADDING_MM * MM_PT
    cells, left = [], layout.x0
    for text, col in zip(texts, columns):
        col_width = layout.avail * col['width'] / 100.0
        inner = max(1.0, col_width - 2 * pad)
        cells.append((wrap_text(text, face, size, inner), col['align'], left + pad, inner))
        left += col_width

    offset = baseline_offset(face, size, lh)
    for lines, align, cell_x, inner in cells:
        for i, line in enumerate(lines):
            x = _aligned_x(cell_x, inner, text_width(face, size, line), align)
            _emit_text(layout, x, layout.y + i * lh + offset, line, face, size, BLACK)
    layout.y += max(len(lines) for lines, _, _, _ in cells) * lh


def _layout_table(layout, item, n):
    data = item.get('data') if isinstance(item.get('data'), dict) else {}
    columns = _table_columns(data.get('columns'))
    family = item.get('font_family')
    italic = _keyword(item.get('font_style')) == 'italic'
    size = layout.base_size
    lh = _item_line_height(layout, item, size)

    labels = [col['label'] for col in columns]
    if any(labels):
        header_face = layout.fonts.resolve(family, True, italic)
        _layout_table_row(layout, labels, columns, header_face, size, lh)
        rule_y = layout.y + TABLE_RULE_OFFSET_MM * MM_PT
        layout.ops.append(('line', (layout.x0, rule_y), (layout.x0 + layout.avail, rule_y),
                           TABLE_RULE_WIDTH_PT, None, BLACK))
        layout.y += TABLE_HEADER_GAP_MM * MM_PT

    rows = data.get('rows') if isinstance(data.get('rows'), list) else []
    body_face = layout.fonts.resolve(family, False, italic)
    for row in rows:
        if isinstance(row, (list, tuple)):
            texts = [_cell_text(row, i) for i in range(len(columns))]
            _layout_table_row(layout, texts, columns, body_face, size, lh)


def _layout_separator(layout, item, n):
    block = SEPARATOR_BLOCK_MM * MM_PT
    style = _keyword(item.get('style')) or 'dashed'
    if style not in SEPARATOR_DASHES:
        style = 'dashed'
    thickness = _number(item.get('thickness'))
    thickness = SEPARATOR_THICKNESS if thickness is None else min(
        max(thickness, SEPARATOR_THICKNESS_RANGE[0]), SEPARATOR_THICKNESS_RANGE[1])
    middle = layout.y + block / 2.0
    offsets = (-SEPARATOR_DOUBLE_OFFSET_PT, SEPARATOR_DOUBLE_OFFSET_PT) if style == 'double' else (0.0,)
    for dy in offsets:
        layout.ops.append(('line', (layout.x0, middle + dy), (layout.x0 + layout.avail, middle + dy),
                           thickness, SEPARATOR_DASHES[style], BLACK))
    layout.y += block


def _flatten_on_white(image):
    """RGB copy of `image` with any transparency composited over white (no thresholding)."""
    if image.mode in ('RGBA', 'LA', 'PA') or (image.mode == 'P' and 'transparency' in image.info):
        rgba = image.convert('RGBA')
        background = Image.new('RGB', rgba.size, (255, 255, 255))
        background.paste(rgba, (0, 0), rgba)
        return background
    return image if image.mode == 'RGB' else image.convert('RGB')


def _image_png(data, n):
    """(png_bytes, (width_px, height_px)) of a base64 image; ValueError when unreadable."""
    try:
        image = Image.open(io.BytesIO(base64.b64decode(data)))
        image.load()
        rgb = _flatten_on_white(image)
        if not rgb.width or not rgb.height:
            raise ValueError('empty image')
        buf = io.BytesIO()
        rgb.save(buf, 'PNG')
    except Exception:
        raise ValueError(f"Invalid image data in item {n}.")
    return buf.getvalue(), rgb.size


def _image_width_pt(item, avail):
    width_mm = _positive(item.get('width_mm'), None)
    if width_mm:
        width = width_mm * MM_PT
    else:
        dots = _positive(item.get('width_dots', item.get('width')), DEFAULT_IMAGE_WIDTH_DOTS)
        width = dots / DOTS_PER_MM * MM_PT
    return min(width, avail)


def _layout_image(layout, item, n):
    data = item.get('data')
    if not data:
        return
    png, (px_width, px_height) = _image_png(data, n)
    width = _image_width_pt(item, layout.avail)
    height = width * px_height / px_width
    max_height = layout.max_image_height_dots / DOTS_PER_MM * MM_PT
    if height > max_height:
        width *= max_height / height
        height = max_height
        _add_warning(layout.warnings,
                     f"Image in item {n} scaled down to fit {layout.max_image_height_dots} dots.")
    x = _aligned_x(layout.x0, layout.avail, width, _align(item.get('align'), 'center'))
    layout.ops.append(('image', fitz.Rect(x, layout.y, x + width, layout.y + height), png))
    layout.y += height


def _layout_spacer(layout, item, n):
    height_mm = _number(item.get('height_mm'))
    if height_mm is not None:
        layout.y += min(max(height_mm, 0.0), SPACER_MAX_MM) * MM_PT
        return
    lines = _number(item.get('lines'))
    lines = max(1, int(lines)) if lines is not None else 1
    layout.y += lines * line_height_pt(layout.base_size, layout.base_line_height)


def _css_name(name):
    return str(name).replace('"', '').replace('\\', '')


def render_html_block(html, width_pt, fontset, base_size, line_height):
    """Render an HTML fragment with fitz.Story into a one-page PDF exactly as tall as its content.

    Returns (pdf_bytes, height_pt). Fonts: every system face the ticket already
    resolved is declared with @font-face (bytes served from a fitz.Archive),
    plus the bold/italic faces of the default family when it is a system font,
    so <b>/<i> work (those extra faces are not reported in `used`). Generic
    families (sans-serif, serif, monospace) are resolved by MuPDF itself.
    <img> is not supported (the archive only holds fonts).
    """
    default = fontset.resolve(fontset.default_family)
    archive = fitz.Archive()
    css, declared = [], set()

    def declare(family, bold, italic, data):
        if (family, bold, italic) in declared:
            return
        declared.add((family, bold, italic))
        name = f"f{len(declared)}{'.otf' if data[:4] == b'OTTO' else '.ttf'}"
        archive.add(data, name)
        css.append(f'@font-face {{ font-family: "{_css_name(family)}"; src: url({name}); '
                   f'font-weight: {"bold" if bold else "normal"}; '
                   f'font-style: {"italic" if italic else "normal"}; }}')

    for face in fontset.system_faces():
        declare(face.css_family, face.system_face['bold'], face.system_face['italic'], face.font_bytes)
    if default.source == 'system':
        for bold, italic in ((True, False), (False, True), (True, True)):
            extra, note = font_service.resolve_face(default.css_family, bold, italic)
            if extra is not None and note is None:
                declare(extra['family'], extra['bold'], extra['italic'],
                        font_service.load_face_bytes(extra))
        body_family = f'"{_css_name(default.css_family)}"'
    else:
        body_family = default.css_family
    css.append(f'body {{ font-family: {body_family}; font-size: {base_size}pt; '
               f'line-height: {line_height}; margin: 0; }} p {{ margin: 0; }}')

    story = fitz.Story(html=f"<body>{html}</body>", user_css="\n".join(css), archive=archive)
    # place() MUST run before draw(): Story.draw() on an unplaced story segfaults
    # the whole process in PyMuPDF 1.26 (no Python exception to catch).
    _more, filled = story.place(fitz.Rect(0, 0, width_pt, HTML_MAX_HEIGHT_PT))
    height = filled[3]
    if height <= 0:
        return b'', 0.0
    story.reset()
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    device = writer.begin_page(fitz.Rect(0, 0, width_pt, height))
    story.draw(device)
    writer.end_page()
    writer.close()
    return buf.getvalue(), height


def _layout_html(layout, item, n):
    html = item.get('data')
    if not isinstance(html, str) or not html.strip():
        return
    try:
        pdf_bytes, height = render_html_block(html, layout.avail, layout.fonts,
                                              layout.base_size, layout.base_line_height)
    except Exception as e:
        _add_warning(layout.warnings, f"HTML block in item {n} could not be rendered: {e}")
        return
    if height <= 0:
        return
    rect = fitz.Rect(layout.x0, layout.y, layout.x0 + layout.avail, layout.y + height)
    layout.ops.append(('pdf', rect, pdf_bytes))
    layout.y += height


def _layout_open_withdrawer(layout, item, n):
    layout.open_drawer = True


_ITEM_LAYOUTS = {
    'text': _layout_text,
    'special_text': _layout_special_text,
    'table': _layout_table,
    'separator': _layout_separator,
    'image': _layout_image,
    'spacer': _layout_spacer,
    'html': _layout_html,
    'open_withdrawer': _layout_open_withdrawer,
}


# ---------------------------------------------------------------------------
# Painting and public API
# ---------------------------------------------------------------------------

def _to_unicode_cmap(glyphs):
    """ToUnicode CMap (bytes) mapping each glyph id of `glyphs` ({gid: char}) to its char."""
    lines = ['/CIDInit /ProcSet findresource begin', '12 dict begin', 'begincmap',
             '/CIDSystemInfo <</Registry(Adobe)/Ordering(UCS)/Supplement 0>> def',
             '/CMapName /Adobe-Identity-UCS def', '/CMapType 2 def',
             '1 begincodespacerange', '<0000> <FFFF>', 'endcodespacerange']
    entries = sorted(glyphs.items())
    for start in range(0, len(entries), 100):   # at most 100 entries per bfchar block
        chunk = entries[start:start + 100]
        lines.append(f'{len(chunk)} beginbfchar')
        lines.extend(f'<{gid:04X}> <{char.encode("utf-16-be").hex().upper()}>' for gid, char in chunk)
        lines.append('endbfchar')
    lines += ['endcmap', 'CMapName currentdict /CMap defineresource pop', 'end', 'end']
    return '\n'.join(lines).encode('ascii')


def _fix_to_unicode(doc, page, ops):
    """Make the text extracted from the PDF match the text that was laid out.

    MuPDF builds the ToUnicode CMap of an embedded font by walking the font's
    cmap, so when several code points share one glyph the highest one wins:
    with Arial a space extracts as U+00A0 and '-' as U+00AD (soft hyphen). The
    ToUnicode of every font TextWriter embedded is rewritten from the glyphs
    this ticket actually drew (fonts are subset to exactly those glyphs anyway).
    Fonts whose name is shared by two different typefaces are left untouched.
    """
    glyphs, owners = {}, {}
    for op in ops:
        if op[0] != 'text':
            continue
        face, name = op[4], op[4].font.name
        owners.setdefault(name, set()).add((face.source, face.resolved))
        mapping = glyphs.setdefault(name, {})
        for char in op[3]:
            gid = face.font.has_glyph(ord(char))
            if gid:
                mapping.setdefault(gid, char)
    for xref, _ext, _type, basefont, _ref, _enc, referencer in page.get_fonts(full=True):
        if referencer or len(owners.get(basefont, ())) != 1 or not glyphs[basefont]:
            continue
        kind, value = doc.xref_get_key(xref, 'ToUnicode')
        if kind == 'xref':
            doc.update_stream(int(value.split()[0]), _to_unicode_cmap(glyphs[basefont]))


def _paint(ops, width, height, warnings):
    """Create the single page, replay the ops and return the subset, compressed PDF bytes."""
    doc = fitz.open()
    sources = []
    try:
        page = doc.new_page(width=width, height=height)
        for op in ops:
            kind = op[0]
            if kind == 'rect':
                page.draw_rect(op[1], color=None, fill=op[2], width=0)
            elif kind == 'line':
                page.draw_line(op[1], op[2], color=op[5], width=op[3], dashes=op[4])
            elif kind == 'image':
                page.insert_image(op[1], stream=op[2])
            elif kind == 'pdf':
                source = fitz.open('pdf', op[2])
                sources.append(source)
                page.show_pdf_page(op[1], source, 0)

        writers = {}
        for op in ops:
            if op[0] == 'text':
                _, x, baseline, text, face, size, rgb = op
                writer = writers.setdefault(rgb, fitz.TextWriter(page.rect))
                writer.append((x, baseline), text, font=face.font, fontsize=size)
        for rgb, writer in writers.items():
            writer.write_text(page, color=rgb)
        try:
            _fix_to_unicode(doc, page, ops)
        except Exception:
            pass   # text extraction only: never block a ticket over it

        try:
            doc.subset_fonts()
        except Exception as e:
            _add_warning(warnings, f"Font subsetting skipped: {e}")
        return doc.tobytes(garbage=4, deflate=True)
    finally:
        for source in sources:
            source.close()
        doc.close()


def render_ticket_pdf(content, options):
    """Lay out RAW ticket items on a single PDF page sized to the content.

    `options` is the normalized dict of section 6.4.1 (missing keys take the
    defaults). Returns {'pdf_bytes', 'page_mm': {'width', 'height'}, 'fonts',
    'warnings', 'open_drawer'}. Raises ValueError with a user-facing message
    for an invalid `font.size`, an unreadable image or a ticket taller than
    `max_height_mm`. Items that are not dicts or have an unknown type are ignored.
    """
    opts = _normalize_options(options)
    fonts = FontSet(opts['font']['family'])
    layout = _Layout(opts, fonts)

    for n, item in enumerate(content or []):
        if not isinstance(item, dict):
            continue
        item_type = item.get('type')
        handler = _ITEM_LAYOUTS.get(item_type) if isinstance(item_type, str) else None
        if handler:
            handler(layout, item, n)

    height = layout.y + layout.bottom
    height_mm = height / MM_PT
    if height_mm > opts['max_height_mm']:
        raise ValueError(f"Rendered ticket is too tall ({height_mm:.1f} mm > {opts['max_height_mm']:g} mm).")

    pdf_bytes = _paint(layout.ops, layout.width, height, layout.warnings)
    return {
        'pdf_bytes': pdf_bytes,
        'page_mm': {'width': round(layout.width / MM_PT, 2), 'height': round(height_mm, 1)},
        'fonts': fonts.used,
        'warnings': layout.warnings,
        'open_drawer': layout.open_drawer,
    }


def render_png(pdf_bytes, dpi):
    """PNG bytes of the first page of `pdf_bytes` rendered at `dpi` (no alpha)."""
    doc = fitz.open('pdf', pdf_bytes)
    try:
        zoom = float(dpi) / 72.0
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes('png')
    finally:
        doc.close()
