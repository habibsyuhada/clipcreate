"""Entry point desktop (Windows/macOS/Linux) — bungkus Video Clipper jadi jendela native
pakai pywebview, server FastAPI jalan di background thread di port lokal acak.

Jalankan langsung: python desktop.py
Build jadi satu file .exe (Windows): lihat build_windows.spec + README bagian "Desktop App".
"""

import os
import socket
import sys
import threading
import time

import uvicorn


def bundled_dir() -> str | None:
    """Kalau jalan sebagai exe hasil PyInstaller (onefile), return folder ekstraksi sementara
    tempat ffmpeg.exe/ffprobe.exe & static/ ikut dibundel. None kalau jalan sebagai skrip biasa."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return None


def prepare_ffmpeg_path() -> None:
    """Supaya shutil.which("ffmpeg") nemu binary yang dibundel PyInstaller."""
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

    webview.create_window(
        "Video Clipper",
        f"http://127.0.0.1:{port}",
        width=1280,
        height=860,
        min_size=(960, 640),
    )
    webview.start()


if __name__ == "__main__":
    main()
