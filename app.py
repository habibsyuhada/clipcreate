"""Video Clipper — entry point FastAPI. Jalankan dengan: python app.py"""

import mimetypes
import os
import re
import sys
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from clipper import captions
from clipper import ffmpeg as ff
from clipper import jobs
from clipper import projects
from clipper import thumbnails as thumbs

APP_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(APP_DIR, "static")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}

app = FastAPI(title="Video Clipper")


# ---------- Model request body ----------

class ProjectPayload(BaseModel):
    video_path: str
    clips: list


class RenderPayload(BaseModel):
    video_path: str
    clip_ids: list | None = None
    mode: str | None = None  # "auto" (default) | "copy" | "reencode"


class CaptionPayload(BaseModel):
    video_path: str
    language: str | None = None  # "auto" (default) | "id" | "en"


class MergePayload(BaseModel):
    video_path: str
    clip_ids: list
    output_name: str
    transition: str | None = None  # None/"none" | "fade" | "dissolve"
    transition_duration: float | None = None  # detik, default 0.5


# ---------- Helper ----------

def _abspath(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


def clamp_number(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _require_file(path: str) -> str:
    path = _abspath(path)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"File tidak ditemukan: {path}")
    return path


def _clips_dir(video_path: str) -> str:
    directory = os.path.join(os.path.dirname(video_path), "clips")
    os.makedirs(directory, exist_ok=True)
    return directory


def _find_clip(clips: list, clip_id: str) -> dict | None:
    for c in clips:
        if c.get("id") == clip_id:
            return c
    return None


def _decide_mode(clip: dict, override: str | None) -> str:
    if override in ("copy", "reencode"):
        return "copy" if override == "copy" else "reencode"
    return "reencode" if ff.needs_reencode(clip.get("edits") or {}) else "copy"


def _render_one(video_path: str, clip: dict, info: dict, mode: str) -> tuple:
    output_dir = _clips_dir(video_path)
    filename = ff.sanitize_filename(clip.get("name") or f"clip_{clip['id'][:8]}.mp4")
    output_path = os.path.join(output_dir, filename)
    cmd = ff.build_cut_command(
        input_path=video_path,
        output_path=output_path,
        start=float(clip["start"]),
        end=float(clip["end"]),
        edits=clip.get("edits") or {},
        width=info["width"],
        height=info["height"],
        mode=mode,
    )
    return cmd, output_path


def _update_clip_in_project(video_path: str, clip_id: str, **fields):
    data = projects.load_project(video_path)
    clip = _find_clip(data.get("clips", []), clip_id)
    if clip is not None:
        clip.update(fields)
        projects.save_project(video_path, data)


# ---------- Static / index ----------

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ---------- Health ----------

@app.get("/api/health")
def health():
    return {"ffmpeg_ok": ff.ffmpeg_available()}


# ---------- Browse filesystem (file picker sederhana) ----------

@app.get("/api/browse")
def browse(path: str | None = None):
    current = _abspath(path) if path else os.path.expanduser("~")
    if not os.path.isdir(current):
        current = os.path.dirname(current) if os.path.isfile(current) else os.path.expanduser("~")

    try:
        raw_entries = os.listdir(current)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Tidak ada akses ke folder ini")

    entries = []
    for name in sorted(raw_entries, key=str.lower):
        if name.startswith("."):
            continue
        full = os.path.join(current, name)
        is_dir = os.path.isdir(full)
        ext = os.path.splitext(name)[1].lower()
        is_video = (not is_dir) and ext in VIDEO_EXTENSIONS
        if is_dir or is_video:
            entries.append({"name": name, "path": full, "is_dir": is_dir, "is_video": is_video})

    parent = os.path.dirname(current) if current != os.path.dirname(current) else None
    return {"current": current, "parent": parent, "entries": entries}


# ---------- Info video ----------

@app.get("/api/video/info")
def video_info(path: str):
    full = _require_file(path)
    if not ff.ffmpeg_available():
        raise HTTPException(status_code=500, detail="FFmpeg/ffprobe tidak ditemukan di PATH. Install FFmpeg terlebih dahulu.")
    try:
        info = ff.probe_video(full)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    info["filename"] = os.path.basename(full)
    info["path"] = full
    return info


# ---------- Streaming video (HTTP Range) ----------

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def _iter_file(path: str, start: int, end: int, chunk_size: int = 1024 * 1024):
    with open(path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = f.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@app.get("/video/stream")
def stream_video(path: str, request: Request):
    full = _require_file(path)
    file_size = os.path.getsize(full)
    content_type = mimetypes.guess_type(full)[0] or "application/octet-stream"

    range_header = request.headers.get("range")
    if range_header:
        match = RANGE_RE.match(range_header)
        if not match:
            raise HTTPException(status_code=416, detail="Range header tidak valid")
        start_s, end_s = match.groups()
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else file_size - 1
        end = min(end, file_size - 1)
        if start > end or start >= file_size:
            raise HTTPException(status_code=416, detail="Range tidak valid")
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
        }
        return StreamingResponse(
            _iter_file(full, start, end), status_code=206, headers=headers, media_type=content_type
        )

    headers = {"Accept-Ranges": "bytes", "Content-Length": str(file_size)}
    return StreamingResponse(_iter_file(full, 0, file_size - 1), headers=headers, media_type=content_type)


# ---------- Thumbnail sprite & waveform (untuk timeline) ----------

@app.get("/api/video/thumbnails")
def video_thumbnails(path: str):
    full = _require_file(path)
    if not ff.ffmpeg_available():
        raise HTTPException(status_code=500, detail="FFmpeg tidak ditemukan di PATH.")
    try:
        info = ff.probe_video(full)
        meta = thumbs.ensure_thumbnails(full, info["duration"])
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return meta


@app.get("/video/thumbnail-sprite")
def thumbnail_sprite(path: str):
    full = _require_file(path)
    sprite = thumbs.sprite_path(full)
    if not os.path.exists(sprite):
        raise HTTPException(status_code=404, detail="Sprite belum digenerate, panggil /api/video/thumbnails dulu")
    return FileResponse(sprite, media_type="image/jpeg")


@app.get("/api/video/waveform")
def video_waveform(path: str):
    full = _require_file(path)
    if not ff.ffmpeg_available():
        raise HTTPException(status_code=500, detail="FFmpeg tidak ditemukan di PATH.")
    try:
        has_audio = thumbs.ensure_waveform(full)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"has_audio": has_audio}


@app.get("/video/waveform-image")
def waveform_image(path: str):
    full = _require_file(path)
    wf = thumbs.waveform_path(full)
    if not os.path.exists(wf):
        raise HTTPException(status_code=404, detail="Waveform belum digenerate atau video tidak punya audio")
    return FileResponse(wf, media_type="image/png")


# ---------- Persistence project (daftar clip) ----------

@app.get("/api/project")
def get_project(path: str):
    full = _require_file(path)
    return projects.load_project(full)


@app.post("/api/project")
def post_project(payload: ProjectPayload):
    full = _require_file(payload.video_path)
    data = {"video_path": full, "clips": payload.clips}
    projects.save_project(full, data)
    return data


# ---------- Render ----------

@app.post("/api/render")
def render(payload: RenderPayload):
    video_path = _require_file(payload.video_path)
    if not ff.ffmpeg_available():
        raise HTTPException(status_code=500, detail="FFmpeg tidak ditemukan di PATH.")

    data = projects.load_project(video_path)
    clips = data.get("clips", [])
    if not clips:
        raise HTTPException(status_code=400, detail="Belum ada clip untuk video ini")

    target_ids = payload.clip_ids if payload.clip_ids else [c["id"] for c in clips]

    try:
        info = ff.probe_video(video_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    job_map = {}
    for clip_id in target_ids:
        clip = _find_clip(clips, clip_id)
        if clip is None:
            continue
        mode = _decide_mode(clip, payload.mode)
        cmd, output_path = _render_one(video_path, clip, info, mode)

        clip["status"] = jobs.STATUS_QUEUED
        clip["error"] = None
        clip["output_path"] = output_path
        clip["render_mode"] = mode

        def make_fn(cmd=cmd, video_path=video_path, clip_id=clip_id, output_path=output_path):
            def fn():
                try:
                    jobs.run_ffmpeg(cmd)
                except Exception:
                    _update_clip_in_project(video_path, clip_id, status=jobs.STATUS_ERROR)
                    raise
                else:
                    _update_clip_in_project(video_path, clip_id, status=jobs.STATUS_DONE, output_path=output_path)
            return fn

        job_id = jobs.submit_job(make_fn(), meta={"clip_id": clip_id, "video_path": video_path})
        clip["job_id"] = job_id
        job_map[clip_id] = job_id

    projects.save_project(video_path, data)
    return {"jobs": job_map}


@app.get("/api/jobs")
def get_jobs(ids: str):
    id_list = [i for i in ids.split(",") if i]
    return {"jobs": jobs.list_jobs(id_list)}


# ---------- Auto caption (speech-to-text) ----------

@app.post("/api/caption/generate")
def generate_caption(payload: CaptionPayload):
    video_path = _require_file(payload.video_path)
    language = captions.LANGUAGE_CHOICES.get(payload.language or "auto", None)
    output_path = captions.srt_output_path(video_path)

    def fn():
        captions.transcribe_to_srt(video_path, output_path, language=language)

    job_id = jobs.submit_job(
        fn, meta={"video_path": video_path, "kind": "caption", "output_path": output_path}
    )
    return {"job_id": job_id, "output_path": output_path}


# ---------- Merge / concat ----------

@app.post("/api/merge")
def merge(payload: MergePayload):
    video_path = _require_file(payload.video_path)
    if not ff.ffmpeg_available():
        raise HTTPException(status_code=500, detail="FFmpeg tidak ditemukan di PATH.")

    data = projects.load_project(video_path)
    clips = data.get("clips", [])
    ordered_clips = []
    for clip_id in payload.clip_ids:
        clip = _find_clip(clips, clip_id)
        if clip is None:
            raise HTTPException(status_code=400, detail=f"Clip tidak ditemukan: {clip_id}")
        ordered_clips.append(clip)
    if len(ordered_clips) < 2:
        raise HTTPException(status_code=400, detail="Pilih minimal 2 clip untuk digabung")

    try:
        info = ff.probe_video(video_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    output_dir = _clips_dir(video_path)
    output_name = ff.sanitize_filename(payload.output_name or "merged.mp4")
    final_output = os.path.join(output_dir, output_name)
    tmp_dir = os.path.join(output_dir, f".merge_tmp_{uuid.uuid4().hex[:8]}")

    target_w = info["width"]
    target_h = info["height"]
    target_fps = 30

    transition = payload.transition if payload.transition in ff.TRANSITIONS else "none"
    trans_duration = clamp_number(payload.transition_duration or 0.5, 0.1, 3.0)

    job_meta = {"video_path": video_path, "output_path": final_output, "kind": "merge"}

    def fn():
        os.makedirs(tmp_dir, exist_ok=True)
        try:
            normalized_paths = []
            durations = []
            for idx, clip in enumerate(ordered_clips):
                mode = "reencode"  # merge selalu re-encode agar bisa dinormalisasi
                raw_path = os.path.join(tmp_dir, f"part_{idx}_raw.mp4")
                cmd = ff.build_cut_command(
                    input_path=video_path,
                    output_path=raw_path,
                    start=float(clip["start"]),
                    end=float(clip["end"]),
                    edits=clip.get("edits") or {},
                    width=info["width"],
                    height=info["height"],
                    mode=mode,
                )
                jobs.run_ffmpeg(cmd)

                has_audio = ff.has_audio_stream(raw_path)
                norm_path = os.path.join(tmp_dir, f"part_{idx}_norm.mp4")
                norm_cmd = ff.build_normalize_command(
                    raw_path, norm_path, target_w, target_h, target_fps, has_audio=has_audio
                )
                jobs.run_ffmpeg(norm_cmd)
                normalized_paths.append(norm_path)
                durations.append(ff.probe_video(norm_path)["duration"])

            actual_transition = transition
            actual_duration = trans_duration
            if actual_transition != "none":
                max_safe_duration = min(durations) / 2 - 0.05
                if max_safe_duration < 0.1:
                    actual_transition = "none"
                    job_meta["warning"] = (
                        "Transisi dinonaktifkan otomatis: ada clip yang terlalu pendek untuk durasi transisi."
                    )
                elif actual_duration > max_safe_duration:
                    actual_duration = max_safe_duration

            if actual_transition == "none":
                list_file = os.path.join(tmp_dir, "list.txt")
                with open(list_file, "w", encoding="utf-8") as f:
                    for p in normalized_paths:
                        f.write(f"file '{p}'\n")
                jobs.run_ffmpeg(ff.build_concat_command(list_file, final_output))
            else:
                jobs.run_ffmpeg(
                    ff.build_transition_merge_command(
                        normalized_paths, durations, final_output, actual_transition, actual_duration
                    )
                )
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    job_id = jobs.submit_job(fn, meta=job_meta)
    return {"job_id": job_id, "output_path": final_output}


if __name__ == "__main__":
    import uvicorn

    if not ff.ffmpeg_available():
        print("=" * 60)
        print("PERINGATAN: FFmpeg / ffprobe tidak ditemukan di PATH.")
        print("Install FFmpeg terlebih dahulu, lalu jalankan ulang aplikasi.")
        print("Lihat README.md untuk petunjuk instalasi.")
        print("=" * 60)

    port = int(os.environ.get("PORT", "8000"))
    print(f"Video Clipper berjalan di http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)
