# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


SPEC_DIR = Path(SPECPATH).resolve()
if SPEC_DIR.is_file():
    SPEC_DIR = SPEC_DIR.parent
ROOT = SPEC_DIR.parent

a = Analysis(
    [str(ROOT / "scripts" / "updater_main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PySide6", "cv2", "PIL", "numpy", "pynput"],
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
    name="updater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
