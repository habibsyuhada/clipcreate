"""Render queue & status, jalan di background thread, satu job berurutan (non-blocking)."""

import queue
import subprocess
import threading
import time
import uuid

STATUS_QUEUED = "queued"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_ERROR = "error"

_jobs: dict[str, dict] = {}
_fns: dict[str, callable] = {}
_queue: "queue.Queue[str]" = queue.Queue()
_lock = threading.Lock()
_worker_started = False


def _shorten(text: str, limit: int = 800) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def run_ffmpeg(command: list) -> None:
    """Helper: jalankan satu perintah ffmpeg, raise RuntimeError kalau gagal."""
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(_shorten(result.stderr or "ffmpeg gagal tanpa pesan error"))


def submit_job(fn, meta: dict | None = None) -> str:
    """Daftarkan job baru ke queue. fn() dipanggil di worker thread; raise Exception jika gagal."""
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": STATUS_QUEUED,
            "error": None,
            "created_at": time.time(),
            "meta": meta or {},
        }
        _fns[job_id] = fn
    _queue.put(job_id)
    _ensure_worker()
    return job_id


def get_job(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def list_jobs(job_ids: list | None = None) -> list:
    with _lock:
        if job_ids is None:
            return [dict(j) for j in _jobs.values()]
        return [dict(_jobs[j]) for j in job_ids if j in _jobs]


def _ensure_worker():
    global _worker_started
    with _lock:
        if _worker_started:
            return
        _worker_started = True
    thread = threading.Thread(target=_worker_loop, daemon=True)
    thread.start()


def _worker_loop():
    while True:
        job_id = _queue.get()
        with _lock:
            job = _jobs.get(job_id)
            fn = _fns.pop(job_id, None)
            if job is None or fn is None:
                continue
            job["status"] = STATUS_PROCESSING

        try:
            fn()
            with _lock:
                _jobs[job_id]["status"] = STATUS_DONE
        except Exception as exc:
            with _lock:
                _jobs[job_id]["status"] = STATUS_ERROR
                _jobs[job_id]["error"] = str(exc)
