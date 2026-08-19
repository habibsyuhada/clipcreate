"""Entry point desktop (Windows/macOS/Linux) — bungkus Video Clipper jadi jendela native
pakai pywebview, server FastAPI jalan di background thread di port lokal acak.

Jalankan langsung: python desktop.py
Build jadi satu file .exe (Windows, FFmpeg ikut dibundel): lihat build_windows.spec.
Build untuk macOS/Linux: lihat desktop.spec.
Lihat README bagian "Desktop App" untuk detail.
"""

import os
import socket
import sys
import threading
import time

import uvicorn


def bundled_dir() -> str | None:
    """Kalau jalan sebagai exe hasil PyInstaller (onefile), return folder ekstraksi sementara
    tempat ffmpeg(.exe)/ffprobe(.exe) & static/ ikut dibundel. None kalau jalan sebagai skrip biasa."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return None


def prepare_ffmpeg_path() -> None:
    """Supaya shutil.which("ffmpeg") nemu binary yang dibundel PyInstaller (kalau ada)."""
    bundled = bundled_dir()
    if bundled:
        os.environ["PATH"] = bundled + os.pathsep + os.environ.get("PATH", "")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int) -> threading.Thread:
    from app import app  # import setelah prepare_ffmpeg_path() supaya PATH sudah benar

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return thread


def wait_until_ready(port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main() -> None:
    prepare_ffmpeg_path()
    port = free_port()
    start_server(port)

    if not wait_until_ready(port):
        print(f"Server tidak merespons di port {port} setelah beberapa detik.")
        sys.exit(1)

    import webview

    url = f"http://127.0.0.1:{port}"
    webview.create_window(
        "Video Clipper",
        url,
        width=1280,
        height=860,
        min_size=(960, 640),
    )
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
