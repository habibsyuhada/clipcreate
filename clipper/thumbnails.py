"""Generate & cache sprite thumbnail dan waveform image untuk timeline scrubbing.

Hasil di-cache di folder tersembunyi `.<namavideo>.assets/` di sebelah video,
di-regenerate otomatis hanya kalau ukuran/mtime video berubah.
"""

import json
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor

from . import ffmpeg as ff
from .jobs import run_ffmpeg

THUMB_COUNT = 60
THUMB_WIDTH = 160
WAVEFORM_WIDTH = 1600
WAVEFORM_HEIGHT = 120
WAVEFORM_COLOR = "5eb0ef"

_LOCK = threading.Lock()


def _assets_dir(video_path: str) -> str:
    directory = os.path.dirname(video_path)
    base = os.path.basename(video_path)
    path = os.path.join(directory, f".{base}.assets")
    os.makedirs(path, exist_ok=True)
    return path


def _meta_path(assets_dir: str) -> str:
    return os.path.join(assets_dir, "meta.json")


def _fingerprint(video_path: str) -> dict:
    stat = os.stat(video_path)
    return {"size": stat.st_size, "mtime": stat.st_mtime}


def _load_meta(assets_dir: str) -> dict:
    path = _meta_path(assets_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_meta(assets_dir: str, meta: dict) -> None:
    tmp_path = _meta_path(assets_dir) + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    os.replace(tmp_path, _meta_path(assets_dir))


def assets_dir(video_path: str) -> str:
    """Folder cache tersembunyi di sebelah video (dipakai juga oleh modul lain, mis. captions.py)."""
    return _assets_dir(video_path)


def sprite_path(video_path: str) -> str:
    return os.path.join(_assets_dir(video_path), "thumbs.jpg")


def waveform_path(video_path: str) -> str:
    return os.path.join(_assets_dir(video_path), "waveform.png")


def ensure_thumbnails(video_path: str, duration: float) -> dict:
    """Generate (kalau perlu) sprite thumbnail, return meta {count, thumb_width, thumb_height, interval}."""
    assets_dir = _assets_dir(video_path)
    fp = _fingerprint(video_path)
    sprite = sprite_path(video_path)

    with _LOCK:
        meta = _load_meta(assets_dir)
        if meta.get("fingerprint") == fp and meta.get("thumbs") and os.path.exists(sprite):
            return meta["thumbs"]

    count = max(min(THUMB_COUNT, int(duration or 0)), 1)
    interval = (duration / count) if duration else 0

    tmp_dir = sprite + ".tmp"
    os.makedirs(tmp_dir, exist_ok=True)
    try:
        timestamps = [min(i * interval, max((duration or 0) - 0.05, 0)) for i in range(count)]

        def extract(idx_ts):
            idx, ts = idx_ts
            frame_path = os.path.join(tmp_dir, f"f{idx:04d}.jpg")
            run_ffmpeg(ff.build_thumbnail_command(video_path, ts, frame_path, THUMB_WIDTH))
            return frame_path

        with ThreadPoolExecutor(max_workers=4) as executor:
            frame_paths = list(executor.map(extract, enumerate(timestamps)))

        thumb_h = _combine_sprite(frame_paths, sprite)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    thumbs_meta = {"count": count, "thumb_width": THUMB_WIDTH, "thumb_height": thumb_h, "interval": interval}
    with _LOCK:
        meta = _load_meta(assets_dir)
        meta["fingerprint"] = fp
        meta["thumbs"] = thumbs_meta
        _save_meta(assets_dir, meta)
    return thumbs_meta


def _combine_sprite(frame_paths: list, output_path: str) -> int:
    from PIL import Image

    images = [Image.open(p) for p in frame_paths]
    w = images[0].width
    h = images[0].height
    sprite = Image.new("RGB", (w * len(images), h), (0, 0, 0))
    for i, img in enumerate(images):
        sprite.paste(img.convert("RGB"), (i * w, 0))
        img.close()
    sprite.save(output_path, "JPEG", quality=80)
    return h


def ensure_waveform(video_path: str) -> bool:
    """Generate (kalau perlu) waveform image. Return False kalau video tidak punya audio track."""
    assets_dir = _assets_dir(video_path)
    fp = _fingerprint(video_path)
    wf = waveform_path(video_path)

    with _LOCK:
        meta = _load_meta(assets_dir)
        if meta.get("fingerprint") == fp and "waveform" in meta:
            return meta["waveform"] and os.path.exists(wf)

    has_audio = ff.has_audio_stream(video_path)
    if has_audio:
        run_ffmpeg(ff.build_waveform_command(video_path, wf, WAVEFORM_WIDTH, WAVEFORM_HEIGHT, WAVEFORM_COLOR))

    with _LOCK:
        meta = _load_meta(assets_dir)
        meta["fingerprint"] = fp
        meta["waveform"] = has_audio
        _save_meta(assets_dir, meta)
    return has_audio
