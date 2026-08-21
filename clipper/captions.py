"""Auto caption: transkripsi audio video jadi file .srt via faster-whisper (offline setelah
model didownload sekali dari Hugging Face Hub saat pertama kali dipakai — butuh internet
saat itu saja, tersimpan di cache lokal sistem setelahnya).
"""

import os
import threading

from . import thumbnails as thumbs

MODEL_SIZE = "small"

LANGUAGE_CHOICES = {"auto": None, "id": "id", "en": "en"}

_model = None
_model_lock = threading.Lock()


def _get_model():
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel

            _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        return _model


def srt_output_path(video_path: str) -> str:
    return os.path.join(thumbs.assets_dir(video_path), "auto_caption.srt")


def _format_timestamp(seconds: float) -> str:
    seconds = max(seconds, 0)
    total_ms = round(seconds * 1000)
    hours, total_ms = divmod(total_ms, 3600_000)
    minutes, total_ms = divmod(total_ms, 60_000)
    secs, ms = divmod(total_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def transcribe_to_srt(video_path: str, output_path: str, language: str | None = None) -> int:
    """Transkripsi audio video jadi file .srt (timestamp relatif ke timeline video sumber).

    Return jumlah baris subtitle yang dihasilkan, raise RuntimeError kalau gagal / tidak ada suara.
    """
    try:
        model = _get_model()
        segments, _info = model.transcribe(video_path, language=language, vad_filter=True)
    except Exception as exc:
        raise RuntimeError(f"Auto caption gagal: {exc}") from exc

    lines = []
    count = 0
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        count += 1
        lines.append(str(count))
        lines.append(f"{_format_timestamp(seg.start)} --> {_format_timestamp(seg.end)}")
        lines.append(text)
        lines.append("")

    if count == 0:
        raise RuntimeError("Tidak ada suara/dialog yang terdeteksi di video ini")

    tmp_path = output_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.replace(tmp_path, output_path)
    return count
