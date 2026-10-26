"""font_service: system font catalog over an isolated temp font directory
(`fake_font_dir`: 'Test Sans' Regular/Bold TTFs, a 'Test Mono' TTC with Regular
+ Italic, and a garbage .ttf), face resolution and face-bytes extraction."""
import os
import re
from collections import OrderedDict

import fitz
import pytest

from src.services import font_service
from src.services import printer_service
from src.utils import coerce
from tests.conftest import build_test_font

CATALOG_FACE_KEYS = {"style", "bold", "italic", "weight", "full_name",
                     "postscript_name", "path", "index", "format"}


@pytest.fixture
def fresh_face_bytes_cache(monkeypatch):
    """Empty face-bytes LRU cache so no bytes leak between tests."""
    cache = OrderedDict()
    monkeypatch.setattr(font_service, "_face_bytes_cache", cache)
    return cache


def _faces_by(faces, family):
    return [face for face in faces if face["family"] == family]


def _family(catalog, name):
    return next(f for f in catalog["data"]["families"] if f["family"] == name)


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

def test_scan_fonts_finds_four_faces_in_two_families(fake_font_dir):
    faces = font_service.scan_fonts()
    assert len(faces) == 4
    assert {face["family"] for face in faces} == {"Test Sans", "Test Mono"}


def test_scan_fonts_skips_unreadable_file_without_error(fake_font_dir):
    faces = font_service.scan_fonts()
    assert (fake_font_dir / "not-a-font.ttf").exists()
    assert not any(face["path"].endswith("not-a-font.ttf") for face in faces)


def test_scan_fonts_test_sans_has_regular_400_and_bold_700(fake_font_dir):
    faces = {face["style"]: face for face in _faces_by(font_service.scan_fonts(), "Test Sans")}
    assert set(faces) == {"Regular", "Bold"}
    assert (faces["Regular"]["weight"], faces["Regular"]["bold"]) == (400, False)
    assert (faces["Bold"]["weight"], faces["Bold"]["bold"]) == (700, True)
    assert faces["Regular"]["format"] == "ttf" and faces["Regular"]["index"] == 0


def test_scan_fonts_test_mono_comes_from_ttc_with_indices_and_italic(fake_font_dir):
    faces = sorted(_faces_by(font_service.scan_fonts(), "Test Mono"), key=lambda f: f["index"])
    assert [face["index"] for face in faces] == [0, 1]
    assert all(face["format"] == "ttc" for face in faces)
    assert all(face["path"] == str(fake_font_dir / "TestMono.ttc") for face in faces)
    assert (faces[0]["style"], faces[0]["italic"]) == ("Regular", False)
    assert (faces[1]["style"], faces[1]["italic"]) == ("Italic", True)


def test_scan_fonts_explicit_dirs_override_platform_dirs(fake_font_dir, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert font_service.scan_fonts([str(empty)]) == []


# ---------------------------------------------------------------------------
# Catalog (GET /fonts payload)
# ---------------------------------------------------------------------------

def test_get_font_catalog_has_standard_shape(fake_font_dir):
    result = font_service.get_font_catalog()
    assert result["status"] == "success"
    assert result["message"] == "Fonts listed."
    data = result["data"]
    assert set(data) == {"families", "count", "builtin", "dirs", "scanned_at"}
    assert data["builtin"] == ["sans-serif", "serif", "monospace"]
    assert data["count"] == 2
    assert data["dirs"] == [str(fake_font_dir)]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", data["scanned_at"])
    for family in data["families"]:
        assert set(family) == {"family", "monospace", "faces"}
        for face in family["faces"]:
            assert set(face) == CATALOG_FACE_KEYS


def test_get_font_catalog_sorts_families_and_faces(fake_font_dir):
    data = font_service.get_font_catalog()["data"]
    assert [f["family"] for f in data["families"]] == ["Test Mono", "Test Sans"]
    assert [face["style"] for face in _family({"data": data}, "Test Sans")["faces"]] == ["Regular", "Bold"]
    assert [face["style"] for face in _family({"data": data}, "Test Mono")["faces"]] == ["Regular", "Italic"]


def test_get_font_catalog_family_monospace_true_when_all_faces_fixed_pitch(fake_font_dir):
    catalog = font_service.get_font_catalog()
    assert _family(catalog, "Test Sans")["monospace"] is True
    assert _family(catalog, "Test Mono")["monospace"] is True


def test_get_font_catalog_family_monospace_false_when_one_face_proportional(fake_font_dir):
    from fontTools.ttLib import TTFont
    path = str(fake_font_dir / "TestSans-Italic.ttf")
    build_test_font(path, style="Italic", italic=True)
    font = TTFont(path)
    font["post"].isFixedPitch = 0
    font.save(path)
    catalog = font_service.get_font_catalog()
    assert _family(catalog, "Test Sans")["monospace"] is False
    assert _family(catalog, "Test Mono")["monospace"] is True


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def test_get_faces_scans_once_and_refresh_rescans(fake_font_dir, monkeypatch):
    calls = []
    real_scan = font_service.scan_fonts

    def counting_scan(*args, **kwargs):
        calls.append(1)
        return real_scan(*args, **kwargs)

    monkeypatch.setattr(font_service, "scan_fonts", counting_scan)
    first = font_service.get_faces()
    second = font_service.get_faces()
    assert len(calls) == 1
    assert second == first
    font_service.get_faces(refresh=True)
    assert len(calls) == 2


def test_get_font_catalog_refresh_picks_up_new_font(fake_font_dir):
    assert font_service.get_font_catalog()["data"]["count"] == 2
    build_test_font(str(fake_font_dir / "Zeta.ttf"), family="Zeta Serif")
    assert font_service.get_font_catalog()["data"]["count"] == 2
    assert font_service.get_font_catalog(refresh=True)["data"]["count"] == 3


# ---------------------------------------------------------------------------
# resolve_face
# ---------------------------------------------------------------------------

def test_resolve_face_case_insensitive_exact_bold_has_no_note(fake_font_dir):
    face, note = font_service.resolve_face("test sans", bold=True)
    assert (face["family"], face["style"], face["bold"]) == ("Test Sans", "Bold", True)
    assert note is None


def test_resolve_face_strips_name_and_matches_ttc_italic(fake_font_dir):
    face, note = font_service.resolve_face("  TEST MONO ", italic=True)
    assert (face["style"], face["index"], face["italic"]) == ("Italic", 1, True)
    assert note is None


def test_resolve_face_missing_italic_uses_regular_with_note(fake_font_dir):
    face, note = font_service.resolve_face("Test Sans", italic=True)
    assert face["style"] == "Regular"
    assert note == "Font family 'Test Sans' has no italic face; using Regular."


def test_resolve_face_missing_bold_uses_regular_with_note(fake_font_dir):
    face, note = font_service.resolve_face("Test Mono", bold=True)
    assert face["style"] == "Regular"
    assert note == "Font family 'Test Mono' has no bold face; using Regular."


def test_resolve_face_missing_bold_italic_prefers_bold_with_note(fake_font_dir):
    face, note = font_service.resolve_face("Test Sans", bold=True, italic=True)
    assert face["style"] == "Bold"
    assert note == "Font family 'Test Sans' has no bold italic face; using Bold."


@pytest.mark.parametrize("family", ["Nope", "", None, "   "])
def test_resolve_face_unknown_family_returns_none_pair(fake_font_dir, family):
    assert font_service.resolve_face(family) == (None, None)


# ---------------------------------------------------------------------------
# load_face_bytes
# ---------------------------------------------------------------------------

def test_load_face_bytes_extracts_ttc_face_loadable_by_mupdf(fake_font_dir, fresh_face_bytes_cache):
    face, _ = font_service.resolve_face("Test Mono", italic=True)
    assert face["index"] == 1
    data = font_service.load_face_bytes(face)
    assert data != (fake_font_dir / "TestMono.ttc").read_bytes()
    font = fitz.Font(fontbuffer=data)
    assert "Test Mono" in font.name
    assert font.is_italic


def test_load_face_bytes_ttf_returns_file_bytes_and_caches(fake_font_dir, fresh_face_bytes_cache):
    face, _ = font_service.resolve_face("Test Sans")
    data = font_service.load_face_bytes(face)
    assert data == (fake_font_dir / "TestSans-Regular.ttf").read_bytes()
    os.remove(face["path"])
    assert font_service.load_face_bytes(face) is data   # served from the cache


def test_load_face_bytes_cache_is_bounded(fake_font_dir, fresh_face_bytes_cache, monkeypatch):
    monkeypatch.setattr(font_service, "_MAX_FACE_BYTES_CACHE", 2)
    faces = font_service.get_faces()
    for face in faces:
        font_service.load_face_bytes(face)
    assert list(fresh_face_bytes_cache) == [(f["path"], f["index"]) for f in faces[-2:]]


# ---------------------------------------------------------------------------
# font_dirs / shared coercion
# ---------------------------------------------------------------------------

def test_font_dirs_returns_only_existing_directories():
    dirs = font_service.font_dirs()
    assert isinstance(dirs, list)
    assert all(os.path.isdir(d) for d in dirs)


def test_printer_service_truthy_is_shared_coerce_truthy():
    assert printer_service._truthy is coerce.truthy
    assert coerce.truthy("Sí") is True and coerce.truthy("0") is False
