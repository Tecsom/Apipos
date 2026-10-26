"""System font catalog (fontTools) for the PDF ticket renderer and GET /fonts.

Scans the platform font directories once per process (in-memory cache, forced
re-scan with `refresh=True`) and exposes:

  * get_font_catalog()  -> standardized response for GET /fonts (families + faces)
  * resolve_face()      -> closest installed face for (family, bold, italic)
  * load_face_bytes()   -> font program bytes for one face (TTC/OTC faces extracted)

A face dict looks like:

    {"family": "Arial", "style": "Bold", "bold": True, "italic": False,
     "weight": 700, "full_name": "Arial Bold", "postscript_name": "Arial-BoldMT",
     "path": "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "index": 0,
     "format": "ttf", "monospace": False}

`monospace` (post.isFixedPitch) is kept internally to derive the family flag;
GET /fonts reports it per family, not per face.
"""
import io
import logging
import os
import sys
import time
from collections import OrderedDict

from fontTools.ttLib import TTFont, TTCollection

from src.utils.response import success_response

# Some system fonts make fontTools log harmless warnings (e.g. "1 extra bytes in
# post.stringData array"); keep the server output clean.
logging.getLogger('fontTools').setLevel(logging.ERROR)

FONT_EXTENSIONS = ('.ttf', '.otf', '.ttc', '.otc')
BUILTIN_FAMILIES = ['sans-serif', 'serif', 'monospace']
_MAX_FACE_BYTES_CACHE = 32

# Name-table record preference: Windows/Unicode BMP/English (US), then Mac/Roman/English.
_NAME_PREFERENCE = ((3, 1, 0x409), (1, 0, 0))
_COLLECTION_FORMATS = ('ttc', 'otc')
# Keys of each face in the GET /fonts response (section 5.2): no `family`, no `monospace`.
_CATALOG_FACE_KEYS = ('style', 'bold', 'italic', 'weight', 'full_name',
                      'postscript_name', 'path', 'index', 'format')
# Style names that best represent each (bold, italic) request; used as a tie-breaker.
_CANONICAL_STYLES = {
    (False, False): ('regular', 'normal', 'roman', 'book'),
    (True, False): ('bold',),
    (False, True): ('italic', 'oblique'),
    (True, True): ('bold italic', 'bold oblique'),
}
_STYLE_LABELS = {(True, False): 'bold', (False, True): 'italic', (True, True): 'bold italic'}

_cache = None                       # None = not scanned yet; else {'faces': [...], 'scanned_at': str}
_face_bytes_cache = OrderedDict()   # (path, index) -> bytes; most recently used last


def font_dirs():
    """Platform font directories (existing ones only), in scan order."""
    if sys.platform == 'win32':
        windir = os.environ.get('WINDIR') or r'C:\Windows'
        candidates = [os.path.join(windir, 'Fonts')]
        local_app_data = os.environ.get('LOCALAPPDATA')
        if local_app_data:
            candidates.append(os.path.join(local_app_data, 'Microsoft', 'Windows', 'Fonts'))
    elif sys.platform == 'darwin':
        candidates = ['/System/Library/Fonts', '/Library/Fonts',
                      os.path.expanduser('~/Library/Fonts')]
    else:
        candidates = ['/usr/share/fonts', '/usr/local/share/fonts',
                      os.path.expanduser('~/.fonts'), os.path.expanduser('~/.local/share/fonts')]
    return [d for d in candidates if os.path.isdir(d)]


def _decode_name(record):
    try:
        text = record.toUnicode(errors='replace')
    except Exception:
        return None
    text = text.replace('\x00', '').strip()
    return text or None


def _name(tt, *name_ids):
    """First non-empty string for the given name IDs (in order), honoring _NAME_PREFERENCE."""
    if 'name' not in tt:
        return None
    table = tt['name']
    for name_id in name_ids:
        for platform_id, enc_id, lang_id in _NAME_PREFERENCE:
            record = table.getName(name_id, platform_id, enc_id, lang_id)
            text = _decode_name(record) if record is not None else None
            if text:
                return text
        for record in table.names:
            if record.nameID == name_id:
                text = _decode_name(record)
                if text:
                    return text
    return None


def _read_face(tt, path, index, fmt):
    """Build one face dict from an open TTFont (section 5.2 shape). Returns None if no family name."""
    family = _name(tt, 16, 1)
    if not family:
        return None
    style = _name(tt, 17, 2) or 'Regular'
    style_lower = style.lower()

    os2 = tt['OS/2'] if 'OS/2' in tt else None
    weight = int(os2.usWeightClass) if os2 is not None else 400
    fs_italic = bool(os2.fsSelection & 1) if os2 is not None else False
    mac_italic = bool(tt['head'].macStyle & 2) if 'head' in tt else False

    return {
        'family': family,
        'style': style,
        'bold': weight >= 600 or 'bold' in style_lower,
        'italic': fs_italic or mac_italic or 'italic' in style_lower or 'oblique' in style_lower,
        'weight': weight,
        'full_name': _name(tt, 4) or f'{family} {style}',
        'postscript_name': _name(tt, 6),
        'path': path,
        'index': index,
        'format': fmt,
        'monospace': bool(tt['post'].isFixedPitch) if 'post' in tt else False,
    }


def _font_files(dirs):
    """Font file paths under `dirs` (recursive, deterministic order, no duplicates)."""
    seen = set()
    for top in dirs:
        for root, subdirs, files in os.walk(top):
            subdirs.sort()
            for name in sorted(files):
                if not name.lower().endswith(FONT_EXTENSIONS):
                    continue
                path = os.path.join(root, name)
                key = os.path.normcase(os.path.abspath(path))
                if key not in seen:
                    seen.add(key)
                    yield path


def _safe_read_face(tt, path, index, fmt):
    try:
        return _read_face(tt, path, index, fmt)
    except Exception:
        return None


def _read_file(path):
    """All readable faces of one font file ([] when the file cannot be opened)."""
    fmt = os.path.splitext(path)[1].lower().lstrip('.')
    faces = []
    try:
        with open(path, 'rb') as fh:
            if fmt in _COLLECTION_FORMATS:
                collection = TTCollection(fh, lazy=True)
                try:
                    for index, tt in enumerate(collection.fonts):
                        faces.append(_safe_read_face(tt, path, index, fmt))
                finally:
                    collection.close()
            else:
                tt = TTFont(fh, lazy=True)
                try:
                    faces.append(_safe_read_face(tt, path, 0, fmt))
                finally:
                    tt.close()
    except Exception:
        pass
    return [face for face in faces if face]


def scan_fonts(dirs=None):
    """Walk the dirs recursively and return a list of face dicts. Unreadable files are skipped."""
    faces = []
    for path in _font_files(font_dirs() if dirs is None else dirs):
        faces.extend(_read_file(path))
    return faces


def get_faces(refresh=False):
    """Cached scan (module-level cache: faces list + scanned_at)."""
    global _cache
    if refresh or _cache is None:
        faces = scan_fonts()
        _cache = {'faces': faces, 'scanned_at': time.strftime('%Y-%m-%dT%H:%M:%S')}
        if refresh:
            _face_bytes_cache.clear()
    return _cache['faces']


def _face_order(face):
    return (face['weight'], face['italic'])


def get_font_catalog(refresh=False):
    """-> success_response(data={families, count, builtin, dirs, scanned_at}, message='Fonts listed.')"""
    faces = get_faces(refresh=refresh)
    by_family = {}
    for face in faces:
        by_family.setdefault(face['family'], []).append(face)

    families = []
    for family in sorted(by_family, key=str.lower):
        members = sorted(by_family[family], key=_face_order)
        families.append({
            'family': family,
            'monospace': all(face['monospace'] for face in members),
            'faces': [{key: face[key] for key in _CATALOG_FACE_KEYS} for face in members],
        })

    return success_response(data={
        'families': families,
        'count': len(families),
        'builtin': list(BUILTIN_FAMILIES),
        'dirs': font_dirs(),
        'scanned_at': _cache['scanned_at'],
    }, message='Fonts listed.')


def _best_match(faces, bold, italic):
    """Closest face with exactly (bold, italic): nearest weight to 700/400, canonical style name."""
    matches = [face for face in faces if face['bold'] == bold and face['italic'] == italic]
    if not matches:
        return None
    target = 700 if bold else 400
    canonical = _CANONICAL_STYLES[(bold, italic)]
    return min(matches, key=lambda face: (abs(face['weight'] - target),
                                          face['style'].lower() not in canonical))


def resolve_face(family, bold=False, italic=False):
    """Return (face_dict | None, note | None) for the closest installed face.

    Match family case-insensitively after strip(). Preference order:
    (bold, italic) exact -> (bold, False) -> (False, italic) -> (False, False) -> first face.
    `note` is a human message when the requested style is missing, e.g.
    "Font family 'Verdana' has no italic face; using Regular." None = exact.
    Unknown family -> (None, None)."""
    key = (family or '').strip().lower()
    if not key:
        return None, None
    candidates = sorted((face for face in get_faces() if face['family'].lower() == key),
                        key=_face_order)
    if not candidates:
        return None, None

    bold, italic = bool(bold), bool(italic)
    face = None
    for want in ((bold, italic), (bold, False), (False, italic), (False, False)):
        face = _best_match(candidates, *want)
        if face:
            break
    face = face or candidates[0]

    note = None
    if (bold and not face['bold']) or (italic and not face['italic']):
        note = (f"Font family '{face['family']}' has no {_STYLE_LABELS[(bold, italic)]} face; "
                f"using {face['style']}.")
    return face, note


def load_face_bytes(face):
    """Bytes of the font program for `face` (TTF/OTF: file bytes; TTC/OTC: extracted single face). LRU-ish cache of _MAX_FACE_BYTES_CACHE entries keyed by (path, index)."""
    path, index = face['path'], int(face.get('index') or 0)
    key = (path, index)
    data = _face_bytes_cache.get(key)
    if data is not None:
        _face_bytes_cache.move_to_end(key)
        return data

    fmt = face.get('format') or os.path.splitext(path)[1].lower().lstrip('.')
    with open(path, 'rb') as fh:
        if fmt in _COLLECTION_FORMATS:
            collection = TTCollection(fh, lazy=True)
            try:
                buf = io.BytesIO()
                collection.fonts[index].save(buf)
                data = buf.getvalue()
            finally:
                collection.close()
        else:
            data = fh.read()

    _face_bytes_cache[key] = data
    while len(_face_bytes_cache) > _MAX_FACE_BYTES_CACHE:
        _face_bytes_cache.popitem(last=False)
    return data
