# -*- mode: python ; coding: utf-8 -*-
# Windows build. Produces a single-file .exe:
#   pyinstaller apipos.spec
import os

from PyInstaller.utils.hooks import collect_submodules

_app_name = os.environ.get('APP_NAME', 'Apipos')

a = Analysis(
    ['apipos.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('./assets/app-icon.png', 'assets'),
        ('./assets/APIPOS.pdf', 'assets'),
        ('./assets/APIPOS_LABEL.pdf', 'assets'),
        ('./app-meta.env', '.'),  # read at runtime for name/version (updater)
    ],
    hiddenimports=['win32print', 'win32timezone'] + collect_submodules('fontTools'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['escpos'],  # macOS/Linux-only backend; not used on Windows
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=_app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX corrupts PyMuPDF's native MuPDF library: fitz imports and opens PDFs
    # fine, but get_pixmap() renders a BLANK raster (empty tickets on PDF jobs).
    # Disabled so the native binaries ship intact. Do not re-enable without
    # excluding pymupdf/_mupdf/libmupdf from UPX.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/app-icon.png'],
)
