# -*- mode: python ; coding: utf-8 -*-
# macOS build. Produces a .app bundle:
#   pyinstaller apipos-macos.spec
#
# Target architecture is taken from the APIPOS_TARGET_ARCH env var
# ('arm64', 'x86_64', 'universal2'); defaults to the host architecture.
import os

from PyInstaller.utils.hooks import collect_submodules

_target_arch = os.environ.get('APIPOS_TARGET_ARCH') or None
_app_name = os.environ.get('APP_NAME', 'Apipos')
_app_version = os.environ.get('APP_VERSION', '1.0.0')
_bundle_id = os.environ.get('APP_BUNDLE_ID', 'mx.tecsom.apipos')

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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=_target_arch,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/app-icon.png'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=_app_name,
)

app = BUNDLE(
    coll,
    name=_app_name + '.app',
    icon='assets/app-icon.png',
    bundle_identifier=_bundle_id,
    info_plist={
        'LSUIElement': True,  # menu-bar / tray app, no Dock icon
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': _app_version,
        'CFBundleVersion': _app_version,
    },
)
