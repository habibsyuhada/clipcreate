"""Builder perintah FFmpeg: probe video, cut, crop, speed, text, audio, concat."""

import json
import re
import shutil
import subprocess

CROP_RATIOS = {
    "original": None,
    "9:16": (9, 16),
    "1:1": (1, 1),
    "16:9": (16, 9),
}

TEXT_POSITIONS = {"top", "middle", "bottom"}
CROP_ANCHORS = {"left", "center", "right"}


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe_video(path: str) -> dict:
    """Return {duration, width, height} for a video file using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-show_entries", "format=duration",
        "-of", "json",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe gagal: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError("Tidak ada video stream yang ditemukan")
    width = int(streams[0]["width"])
    height = int(streams[0]["height"])
    duration = float(data["format"]["duration"])
    return {"duration": duration, "width": width, "height": height}


def escape_drawtext(text: str) -> str:
    """Escape karakter khusus untuk filter drawtext FFmpeg."""
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "’")  # ganti quote lurus dengan curly agar tak perlu escape rumit
    text = text.replace("%", "\\%")
    return text


def needs_reencode(edits: dict) -> bool:
    """Tentukan apakah clip butuh re-encode berdasarkan edit yang aktif."""
    if not edits:
        return False
    crop = edits.get("crop", "original")
    if crop and crop != "original":
        return True
    speed = float(edits.get("speed", 1.0) or 1.0)
    if abs(speed - 1.0) > 1e-6:
        return True
    text = edits.get("text") or {}
    if text.get("content"):
        return True
    audio = edits.get("audio") or {}
    if audio.get("mute"):
        return True
    if float(audio.get("volume", 100) or 100) != 100:
        return True
    if float(audio.get("fade_in", 0) or 0) > 0:
        return True
    if float(audio.get("fade_out", 0) or 0) > 0:
        return True
    return False


def _atempo_chain(speed: float) -> list:
    """atempo hanya mendukung 0.5-2.0 per filter, jadi chain kalau perlu."""
    if speed <= 0:
        raise ValueError("speed harus > 0")
    filters = []
    remaining = speed
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.6f}")
    return filters


def _crop_filter(crop: str, anchor: str, width: int, height: int) -> str | None:
    ratio = CROP_RATIOS.get(crop)
    if ratio is None:
        return None
    rw, rh = ratio
    target_ar = rw / rh
    source_ar = width / height

    if source_ar > target_ar:
        # sumber lebih lebar dari target -> crop lebar
        crop_h = height
        crop_w = int(round(height * target_ar))
        crop_w -= crop_w % 2
        if anchor == "left":
            x = 0
        elif anchor == "right":
            x = width - crop_w
        else:
            x = (width - crop_w) // 2
        y = 0
        return f"crop={crop_w}:{crop_h}:{x}:{y}"
    else:
        # sumber lebih sempit dari target -> crop tinggi
        crop_w = width
        crop_h = int(round(width / target_ar))
        crop_h -= crop_h % 2
        x = 0
        y = (height - crop_h) // 2
        return f"crop={crop_w}:{crop_h}:{x}:{y}"


def _text_filter(text_cfg: dict) -> str | None:
    content = (text_cfg or {}).get("content")
    if not content:
        return None
    position = text_cfg.get("position", "bottom")
    if position not in TEXT_POSITIONS:
        position = "bottom"
    size = int(text_cfg.get("size", 36) or 36)
    color = text_cfg.get("color", "white") or "white"
    outline = text_cfg.get("outline", "black") or "black"

    if position == "top":
        y = "40"
    elif position == "middle":
        y = "(h-text_h)/2"
    else:
        y = "h-text_h-40"

    escaped = escape_drawtext(content)
    return (
        f"drawtext=text='{escaped}':fontcolor={color}:fontsize={size}:"
        f"borderw=2:bordercolor={outline}:x=(w-text_w)/2:y={y}"
    )


def build_video_filters(edits: dict, width: int, height: int) -> list:
    filters = []
    crop = edits.get("crop", "original")
    anchor = edits.get("crop_anchor", "center")
    if anchor not in CROP_ANCHORS:
        anchor = "center"
    crop_f = _crop_filter(crop, anchor, width, height)
    if crop_f:
        filters.append(crop_f)

    text_f = _text_filter(edits.get("text") or {})
    if text_f:
        filters.append(text_f)

    speed = float(edits.get("speed", 1.0) or 1.0)
    if abs(speed - 1.0) > 1e-6:
        filters.append(f"setpts=PTS/{speed:.6f}")

    return filters


def build_audio_filters(edits: dict, clip_duration: float) -> list:
    audio = edits.get("audio") or {}
    if audio.get("mute"):
        return None  # sinyal: buang audio track (-an)

    filters = []
    speed = float(edits.get("speed", 1.0) or 1.0)
    if abs(speed - 1.0) > 1e-6:
        filters.extend(_atempo_chain(speed))

    volume = float(audio.get("volume", 100) or 100)
    if volume != 100:
        filters.append(f"volume={volume / 100:.4f}")

    fade_in = float(audio.get("fade_in", 0) or 0)
    if fade_in > 0:
        filters.append(f"afade=t=in:st=0:d={fade_in:.3f}")

    fade_out = float(audio.get("fade_out", 0) or 0)
    if fade_out > 0:
        real_duration = clip_duration / speed if speed else clip_duration
        start = max(real_duration - fade_out, 0)
        filters.append(f"afade=t=out:st={start:.3f}:d={fade_out:.3f}")

    return filters


def build_cut_command(
    input_path: str,
    output_path: str,
    start: float,
    end: float,
    edits: dict | None,
    width: int,
    height: int,
    mode: str,
) -> list:
    """Susun command ffmpeg lengkap untuk memotong+edit satu clip."""
    edits = edits or {}
    duration = max(end - start, 0.01)

    if mode == "copy":
        return [
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}",
            "-i", input_path,
            "-t", f"{duration:.3f}",
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            output_path,
        ]

    # re-encode (akurat): -ss setelah -i agar frame-accurate
    cmd = ["ffmpeg", "-y", "-i", input_path, "-ss", f"{start:.3f}", "-t", f"{duration:.3f}"]

    video_filters = build_video_filters(edits, width, height)
    audio_filters = build_audio_filters(edits, duration)

    if video_filters:
        cmd += ["-vf", ",".join(video_filters)]

    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]

    if audio_filters is None:
        cmd += ["-an"]
    else:
        if audio_filters:
            cmd += ["-af", ",".join(audio_filters)]
        cmd += ["-c:a", "aac"]

    cmd += ["-movflags", "+faststart", output_path]
    return cmd


def build_normalize_command(
    input_path: str, output_path: str, width: int, height: int, fps: int, has_audio: bool = True
) -> list:
    """Samakan resolusi/fps/audio sebelum concat atau transisi.

    Kalau clip sumber tidak punya audio (mis. di-mute), tambahkan silent audio track
    supaya tetap ada stream audio yang konsisten untuk di-concat/crossfade.
    """
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps}"
    )
    if has_audio:
        return [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart",
            output_path,
        ]
    return [
        "ffmpeg", "-y",
        "-i", input_path,
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-vf", vf,
        "-map", "0:v:0", "-map", "1:a:0", "-shortest",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        output_path,
    ]


def build_concat_command(list_file: str, output_path: str) -> list:
    return [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output_path,
    ]


TRANSITIONS = {"fade", "dissolve"}


def build_transition_merge_command(
    paths: list, durations: list, output_path: str, transition: str, trans_duration: float
) -> list:
    """Gabung beberapa video (sudah dinormalisasi resolusi/fps/audio-nya sama) dengan crossfade
    berantai (xfade untuk video, acrossfade untuk audio). offset transisi ke-i dihitung dari
    akumulasi durasi asli tiap clip dikurangi i * durasi transisi (rumus xfade berantai standar)."""
    cmd = ["ffmpeg", "-y"]
    for p in paths:
        cmd += ["-i", p]

    v_filters = []
    a_filters = []
    v_label = "0:v"
    a_label = "0:a"
    cumulative = durations[0]
    n = len(paths)
    for i in range(1, n):
        offset = cumulative - trans_duration * i
        out_v = f"v{i}" if i < n - 1 else "vout"
        out_a = f"a{i}" if i < n - 1 else "aout"
        v_filters.append(
            f"[{v_label}][{i}:v]xfade=transition={transition}:duration={trans_duration:.3f}:offset={offset:.3f}[{out_v}]"
        )
        a_filters.append(f"[{a_label}][{i}:a]acrossfade=d={trans_duration:.3f}[{out_a}]")
        v_label, a_label = out_v, out_a
        cumulative += durations[i]

    filter_complex = ";".join(v_filters + a_filters)
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac",
        "-movflags", "+faststart",
        output_path,
    ]
    return cmd


def has_audio_stream(path: str) -> bool:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() != ""


def build_thumbnail_command(input_path: str, timestamp: float, output_path: str, width: int = 160) -> list:
    """Ekstrak satu frame thumbnail. -ss sebelum -i = fast seek (keyframe terdekat), cukup akurat untuk preview."""
    return [
        "ffmpeg", "-y",
        "-ss", f"{max(timestamp, 0):.3f}",
        "-i", input_path,
        "-frames:v", "1",
        "-vf", f"scale={width}:-2",
        "-q:v", "4",
        output_path,
    ]


def build_waveform_command(input_path: str, output_path: str, width: int = 1600, height: int = 120, color: str = "5eb0ef") -> list:
    return [
        "ffmpeg", "-y",
        "-i", input_path,
        "-filter_complex", f"aformat=channel_layouts=mono,showwavespic=s={width}x{height}:colors=0x{color}",
        "-frames:v", "1",
        output_path,
    ]


def sanitize_filename(name: str) -> str:
    name = name.strip() or "clip"
    name = re.sub(r"[^A-Za-z0-9._\- ]+", "_", name)
    if not name.lower().endswith(".mp4"):
        name += ".mp4"
    return name
