# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the aud_it desktop app.

One-folder build (faster startup than one-file). Run with:

    pyinstaller aud_it.spec

Output lands in ``dist/aud_it/`` (folder) with the launcher ``dist/aud_it/aud_it``.
"""

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    copy_metadata,
)

datas = []
binaries = []
hiddenimports = []


def _add(pkg):
    d, b, h = collect_all(pkg)
    datas.extend(d)
    binaries.extend(b)
    hiddenimports.extend(h)


# --- spaCy + the model package (en_core_web_lg, used by backend/presidio/registry.py)
_add("spacy")
_add("en_core_web_lg")

# --- Presidio
_add("presidio_analyzer")
_add("presidio_anonymizer")

# --- PyMuPDF (ships native binaries)
_add("pymupdf")
hiddenimports += ["fitz", "pymupdf"]

# --- usaddress (custom recognizer) ships model data
_add("usaddress")

for _meta in ("spacy", "presidio_analyzer", "presidio_anonymizer", "pymupdf"):
    try:
        datas += copy_metadata(_meta)
    except Exception:
        pass

# Ship the application source: backend package + frontend assets.
datas += [
    ("backend", "backend"),
    ("frontend", "frontend"),
]
datas += collect_data_files("backend")

# Bundled Windows Tesseract (run scripts/download_tesseract_win.ps1 first).
_tess_root = Path("vendor/tesseract/win64")
if _tess_root.is_dir():
    _tess_exe = _tess_root / "tesseract.exe"
    _tessdata = _tess_root / "tessdata"
    if _tess_exe.is_file():
        datas.append((str(_tess_exe), "tesseract"))
    if _tessdata.is_dir():
        datas.append((str(_tessdata), "tesseract/tessdata"))
    for _dll in _tess_root.glob("*.dll"):
        binaries.append((str(_dll), "tesseract"))

hiddenimports += [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "anyio",
    "backend.main",
    "backend.config",
    "backend.database",
]

block_cipher = None

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="aud_it",
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="aud_it",
)
