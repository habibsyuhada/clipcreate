"""Load/save daftar clip untuk sebuah video ke file JSON lokal (di sebelah video)."""

import json
import os
import threading

_LOCK = threading.Lock()


def _project_path(video_path: str) -> str:
    directory = os.path.dirname(video_path)
    base = os.path.basename(video_path)
    return os.path.join(directory, f".{base}.clips.json")


def load_project(video_path: str) -> dict:
    path = _project_path(video_path)
    if not os.path.exists(path):
        return {"video_path": video_path, "clips": []}
    with _LOCK:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    data.setdefault("clips", [])
    data["video_path"] = video_path
    return data


def save_project(video_path: str, data: dict) -> None:
    path = _project_path(video_path)
    data = dict(data)
    data["video_path"] = video_path
    with _LOCK:
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
