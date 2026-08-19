"""Video Clipper — desktop entry point. Membungkus app.py FastAPI dalam window native (pywebview).

Dipakai untuk build standalone executable (lihat desktop.spec / .github/workflows/release.yml).
Tetap bisa dijalankan langsung: python desktop.py
"""

import socket
import threading
import time

import uvicorn
import webview

from app import app
from clipper import ffmpeg as ff


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run_server(port: int) -> None:
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main() -> None:
    if not ff.ffmpeg_available():
        webview.settings["ALLOW_DOWNLOADS"] = False

    port = _free_port()
    thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    thread.start()

    window_title = "Video Clipper"
    if not ff.ffmpeg_available():
        window_title += " (FFmpeg tidak ditemukan — install FFmpeg agar render berfungsi)"

    url = f"http://127.0.0.1:{port}"
    webview.create_window(window_title, url, width=1280, height=800, min_size=(960, 600))
    try:
        webview.start()
    except Exception:
        # Tidak ada backend GTK/QT/WebKit tersedia (umum di sebagian distro Linux tanpa
        # PyGObject/webkit2gtk terpasang). Fallback: buka browser default, server tetap
        # jalan di background selama proses ini hidup.
        import webbrowser

        webbrowser.open(url)
        print(f"Window desktop tidak tersedia di sistem ini. Video Clipper dibuka di browser: {url}")
        print("Biarkan terminal ini tetap terbuka. Tekan Ctrl+C untuk keluar.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
