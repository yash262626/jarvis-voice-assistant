# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for JARVIS.

    pyinstaller jarvis.spec --noconfirm --clean

Produces dist/JARVIS/JARVIS.exe. A one-folder build is used on purpose:
one-file builds unpack Whisper and onnxruntime to a temp folder on every
launch, which adds 10-20 seconds to start-up.
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(os.getcwd())

# --- data files ------------------------------------------------------------
datas = [
    (str(ROOT / "config" / "config.json"), "config"),
    (str(ROOT / "config" / "applications.json"), "config"),
    (str(ROOT / "config" / "websites.json"), "config"),
]

icon_path = ROOT / "assets" / "jarvis.ico"
if icon_path.exists():
    datas.append((str(icon_path), "assets"))

# Bundle the pre-downloaded models so the .exe works offline on day one.
for package in ("openwakeword", "faster_whisper", "sounddevice"):
    try:
        datas += collect_data_files(package)
    except Exception:
        pass

binaries = []
for package in ("onnxruntime", "sounddevice", "ctranslate2"):
    try:
        binaries += collect_dynamic_libs(package)
    except Exception:
        pass

# --- imports PyInstaller cannot see ----------------------------------------
hiddenimports = [
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    "comtypes",
    "comtypes.stream",
    "win32com",
    "win32com.client",
    "sounddevice",
    "numpy",
    "onnxruntime",
    "openwakeword",
    "openwakeword.model",
    "openwakeword.utils",
    "faster_whisper",
    "ctranslate2",
    "speech_recognition",
    "dotenv",
    # action plugins are imported dynamically by the router
    "actions.typing_actions",
    "actions.keyboard_actions",
    "actions.browser_actions",
    "actions.application_actions",
    "actions.file_actions",
    "actions.system_actions",
]

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "PyQt5", "PyQt6"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JARVIS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                    # no terminal window; logs go to logs/
    disable_windowed_traceback=False,
    icon=str(icon_path) if icon_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="JARVIS",
)
