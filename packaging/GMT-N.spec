# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


SPEC_DIR = Path(SPECPATH).resolve()
if SPEC_DIR.is_file():
    SPEC_DIR = SPEC_DIR.parent
ROOT = SPEC_DIR.parent

hiddenimports = [
    "Plan_SIFT.sift_tracker",
    "tools.annotation_converters.base",
    "tools.annotation_converters.legacy_coordinate_convert",
    "tools.annotation_converters.registry",
    "tools.annotation_format_converter",
    "tools.fetch_17173_all_points",
    "tools.fetch_17173_icons",
    "tools.fetch_17173_points",
    "tools.route_format_converter",
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
]
hiddenimports += collect_submodules("tools.annotation_converters.outside_convert")


a = Analysis(
    [str(ROOT / "main_island.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GMT-N",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name="GMT-N",
)
