# PyInstaller spec — build standalone desktop executable untuk macOS/Linux.
# (Windows pakai build_windows.spec, yang juga membundel ffmpeg.exe/ffprobe.exe.)
# Build: pyinstaller desktop.spec
# Hasil ada di dist/VideoClipper/ (satu folder, berisi executable + dependencies).
# FFmpeg tidak dibundel di sini — harus terinstall terpisah di sistem (lihat README).

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=[("static", "static")],
    hiddenimports=[
        "clipper",
        "clipper.ffmpeg",
        "clipper.jobs",
        "clipper.projects",
        "clipper.thumbnails",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VideoClipper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="VideoClipper",
)
