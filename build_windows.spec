# -*- mode: python ; coding: utf-8 -*-
# Build satu file .exe portable untuk Windows: pyinstaller build_windows.spec
# ffmpeg.exe & ffprobe.exe harus sudah ada di vendor/ffmpeg/ sebelum build
# (lihat README bagian "Desktop App (Windows)" atau .github/workflows/build-windows.yml).

import os

block_cipher = None

FFMPEG_DIR = os.path.join("vendor", "ffmpeg")
binaries = []
for name in ("ffmpeg.exe", "ffprobe.exe"):
    path = os.path.join(FFMPEG_DIR, name)
    if os.path.exists(path):
        binaries.append((path, "."))

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=binaries,
    datas=[("static", "static")],
    hiddenimports=[
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
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="VideoClipper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    runtime_tmpdir=None,
)
