# PyInstaller spec — build standalone desktop executable untuk macOS/Linux.
# (Windows pakai build_windows.spec, yang juga membundel ffmpeg.exe/ffprobe.exe.)
# Build: pyinstaller desktop.spec
# Hasil ada di dist/VideoClipper/ (satu folder, berisi executable + dependencies).
# FFmpeg tidak dibundel di sini — harus terinstall terpisah di sistem (lihat README).

from PyInstaller.utils.hooks import collect_all

datas = [("static", "static")]
binaries = []
hiddenimports = [
    "clipper",
    "clipper.ffmpeg",
    "clipper.captions",
    "clipper.jobs",
    "clipper.projects",
    "clipper.thumbnails",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

# faster-whisper (Auto Caption) & dependency-nya (ctranslate2) punya binary compiled +
# data file yang tidak selalu terdeteksi otomatis oleh Analysis, jadi di-collect eksplisit.
for pkg in ("faster_whisper", "ctranslate2"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

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
