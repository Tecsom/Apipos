# -*- mode: python ; coding: utf-8 -*-
# Linux build. Produces a one-folder bundle (dist/Apipos/Apipos):
#   pyinstaller apipos-linux.spec
#
# One-folder (not one-file) so the app starts fast and sys.executable is a
# stable path for the desktop / autostart entries written by install.sh.
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
    hiddenimports=[] + collect_submodules('fontTools'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['win32print'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=_app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # Same reason as apipos.spec: UPX breaks PyMuPDF's native library
    # (blank rasters on PDF jobs).
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=_app_name,
)
