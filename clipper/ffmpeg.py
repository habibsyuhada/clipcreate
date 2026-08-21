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

CROP_ANCHORS = {"left", "center", "right"}

GRID_POSITIONS = {
    "top-left", "top-center", "top-right",
    "middle-left", "middle-center", "middle-right",
    "bottom-left", "bottom-center", "bottom-right",
}
_LEGACY_POSITION_MAP = {"top": "top-center", "middle": "middle-center", "bottom": "bottom-center"}

TEXT_POSITION_XY = {
    "top-left": ("40", "40"),
    "top-center": ("(w-text_w)/2", "40"),
    "top-right": ("w-text_w-40", "40"),
    "middle-left": ("40", "(h-text_h)/2"),
    "middle-center": ("(w-text_w)/2", "(h-text_h)/2"),
    "middle-right": ("w-text_w-40", "(h-text_h)/2"),
    "bottom-left": ("40", "h-text_h-40"),
    "bottom-center": ("(w-text_w)/2", "h-text_h-40"),
    "bottom-right": ("w-text_w-40", "h-text_h-40"),
}


def _overlay_xy(position: str, margin: int = 20) -> tuple:
    mapping = {
        "top-left": (f"{margin}", f"{margin}"),
        "top-center": ("(W-w)/2", f"{margin}"),
        "top-right": (f"W-w-{margin}", f"{margin}"),
        "middle-left": (f"{margin}", "(H-h)/2"),
        "middle-center": ("(W-w)/2", "(H-h)/2"),
        "middle-right": (f"W-w-{margin}", "(H-h)/2"),
        "bottom-left": (f"{margin}", f"H-h-{margin}"),
        "bottom-center": ("(W-w)/2", f"H-h-{margin}"),
        "bottom-right": (f"W-w-{margin}", f"H-h-{margin}"),
    }
    return mapping.get(position, mapping["top-right"])


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


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


def escape_filter_path(path: str) -> str:
    """Escape path untuk dipakai sebagai argument filter ffmpeg (mis. subtitles=filename='...')."""
    path = path.replace("\\", "\\\\")
    path = path.replace("'", "\\'")
    path = path.replace(":", "\\:")
    return path


MEME_FILTERS = {
    "none": [],
    "deepfry": ["eq=contrast=1.6:saturation=2.8:gamma=1.3", "noise=alls=25:allf=t+u", "unsharp=5:5:1.5"],
    "vhs": ["hue=s=0.6", "noise=alls=15:allf=t", "chromashift=cbh=2:crh=-2"],
    "grayscale": ["hue=s=0"],
}

PUNCH_TYPES = {"zoom", "shake", "flash"}

TIMELAPSE_MIN_FACTOR = 2
TIMELAPSE_MAX_FACTOR = 120


def _meme_filter_chain(name: str) -> list:
    return list(MEME_FILTERS.get(name or "none", []))


def _punch_filters(punch: dict, width: int, height: int, clip_start: float = 0.0) -> list:
    """Efek 'punch' sesaat (zoom-in, shake, atau flash) di titik waktu tertentu pada clip.

    `t` di dalam ekspresi filter ffmpeg adalah timestamp absolut video sumber (bukan relatif
    ke awal clip, sudah diverifikasi karena -ss dipasang sebagai output option), jadi waktu
    yang diminta user (relatif ke awal clip) harus ditambah `clip_start` di sini.
    """
    if not punch or not punch.get("enabled"):
        return []
    ptype = punch.get("type", "zoom")
    if ptype not in PUNCH_TYPES:
        return []
    time_at = clip_start + max(float(punch.get("time", 0) or 0), 0)
    duration = _clamp(float(punch.get("duration", 0.3) or 0.3), 0.05, 5.0)
    half = duration / 2
    end_at = time_at + duration

    if ptype == "zoom":
        intensity = _clamp(float(punch.get("intensity", 25) or 25), 1, 200) / 100
        zoom_expr = f"(1+({intensity:.4f})*max(0,1-abs(t-{time_at:.3f})/{half:.3f}))"
        return [
            f"scale=w='trunc(iw*{zoom_expr}/2)*2':h='trunc(ih*{zoom_expr}/2)*2':eval=frame",
            f"crop=w={width}:h={height}:x='(in_w-out_w)/2':y='(in_h-out_h)/2'",
        ]

    if ptype == "shake":
        amp = int(_clamp(float(punch.get("intensity", 16) or 16), 2, 60))
        sx = (
            f"{amp}+{amp}*if(between(t\\,{time_at:.3f}\\,{end_at:.3f})\\,1\\,0)"
            f"*sin(2*PI*16*(t-{time_at:.3f}))"
        )
        sy = (
            f"{amp}+{amp}*if(between(t\\,{time_at:.3f}\\,{end_at:.3f})\\,1\\,0)"
            f"*cos(2*PI*21*(t-{time_at:.3f}))"
        )
        return [
            f"scale=w=iw+{amp * 2}:h=ih+{amp * 2}",
            f"crop=w={width}:h={height}:x='{sx}':y='{sy}'",
        ]

    # flash
    strength = _clamp(float(punch.get("intensity", 80) or 80), 5, 100) / 100
    expr = f"{strength:.3f}*max(0,1-abs(t-{time_at:.3f})/{half:.3f})"
    return [f"eq=brightness='{expr}':eval=frame"]


def _all_text_layers(edits: dict) -> list:
    """Gabungkan `texts` (list layer baru) dengan `text` singular (format lama, untuk backward compat)."""
    texts = list(edits.get("texts") or [])
    legacy = edits.get("text")
    if legacy and legacy.get("content"):
        texts = texts + [legacy]
    return [t for t in texts if (t or {}).get("content")]


def _timelapse_factor(edits: dict) -> float | None:
    """Faktor kecepatan timelapse (2x-120x) kalau mode timelapse aktif, else None.

    Timelapse menggantikan (bukan menambah) edit Kecepatan biasa, dan audio selalu
    dibuang karena di kecepatan setinggi ini audio hasil atempo tidak lagi berguna.
    """
    timelapse = edits.get("timelapse") or {}
    if not timelapse.get("enabled"):
        return None
    factor = _clamp(float(timelapse.get("factor", 8) or 8), TIMELAPSE_MIN_FACTOR, TIMELAPSE_MAX_FACTOR)
    return factor


def needs_reencode(edits: dict) -> bool:
    """Tentukan apakah clip butuh re-encode berdasarkan edit yang aktif."""
    if not edits:
        return False
    if _timelapse_factor(edits) is not None:
        return True
    crop = edits.get("crop", "original")
    if crop and crop != "original":
        return True
    speed = float(edits.get("speed", 1.0) or 1.0)
    if abs(speed - 1.0) > 1e-6:
        return True
    if _all_text_layers(edits):
        return True
    watermark = edits.get("watermark") or {}
    if watermark.get("enabled") and watermark.get("image_path"):
        return True
    subtitle = edits.get("subtitle") or {}
    if subtitle.get("enabled") and subtitle.get("path"):
        return True
    meme_filter = edits.get("meme_filter", "none")
    if meme_filter and meme_filter != "none":
        return True
    punch = edits.get("punch") or {}
    if punch.get("enabled") and punch.get("type") in PUNCH_TYPES:
        return True
    sound_effect = edits.get("sound_effect") or {}
    if sound_effect.get("enabled") and sound_effect.get("audio_path"):
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


def _crop_dims(crop: str, anchor: str, width: int, height: int) -> tuple | None:
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
    else:
        # sumber lebih sempit dari target -> crop tinggi
        crop_w = width
        crop_h = int(round(width / target_ar))
        crop_h -= crop_h % 2
        x = 0
        y = (height - crop_h) // 2
    return crop_w, crop_h, x, y


def _text_filter(text_cfg: dict) -> str | None:
    content = (text_cfg or {}).get("content")
    if not content:
        return None
    position = text_cfg.get("position", "middle-center")
    position = _LEGACY_POSITION_MAP.get(position, position)
    if position not in GRID_POSITIONS:
        position = "middle-center"
    x_expr, y_expr = TEXT_POSITION_XY[position]
    size = int(text_cfg.get("size", 36) or 36)
    color = text_cfg.get("color", "white") or "white"
    outline = text_cfg.get("outline", "black") or "black"
    meme = bool(text_cfg.get("meme"))
    if meme:
        content = content.upper()
    borderw = max(4, size // 8) if meme else 2

    escaped = escape_drawtext(content)
    return (
        f"drawtext=text='{escaped}':fontcolor={color}:fontsize={size}:"
        f"borderw={borderw}:bordercolor={outline}:x={x_expr}:y={y_expr}"
    )


def _subtitle_filter(sub_cfg: dict) -> str | None:
    if not sub_cfg or not sub_cfg.get("enabled") or not sub_cfg.get("path"):
        return None
    path = escape_filter_path(sub_cfg["path"])
    size = int(sub_cfg.get("size", 24) or 24)
    return f"subtitles=filename='{path}':force_style='FontSize={size}'"


def build_video_filters(edits: dict, width: int, height: int, clip_start: float = 0.0) -> list:
    filters = []
    cur_w, cur_h = width, height
    crop = edits.get("crop", "original")
    anchor = edits.get("crop_anchor", "center")
    if anchor not in CROP_ANCHORS:
        anchor = "center"
    dims = _crop_dims(crop, anchor, width, height)
    if dims:
        crop_w, crop_h, x, y = dims
        filters.append(f"crop={crop_w}:{crop_h}:{x}:{y}")
        cur_w, cur_h = crop_w, crop_h

    filters.extend(_meme_filter_chain(edits.get("meme_filter", "none")))
    filters.extend(_punch_filters(edits.get("punch") or {}, cur_w, cur_h, clip_start))

    for text_cfg in _all_text_layers(edits):
        text_f = _text_filter(text_cfg)
        if text_f:
            filters.append(text_f)

    sub_f = _subtitle_filter(edits.get("subtitle") or {})
    if sub_f:
        filters.append(sub_f)

    timelapse_factor = _timelapse_factor(edits)
    speed = timelapse_factor if timelapse_factor is not None else float(edits.get("speed", 1.0) or 1.0)
    if abs(speed - 1.0) > 1e-6:
        filters.append(f"setpts=PTS/{speed:.6f}")

    return filters


def build_audio_filters(edits: dict, clip_duration: float) -> list:
    if _timelapse_factor(edits) is not None:
        return None  # timelapse: audio selalu dibuang (-an), atempo di kecepatan ini sudah tidak berguna

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

    watermark = edits.get("watermark") or {}
    watermark_path = watermark.get("image_path") if watermark.get("enabled") else None

    sound_effect = edits.get("sound_effect") or {}
    sfx_path = sound_effect.get("audio_path") if sound_effect.get("enabled") else None

    # re-encode (akurat): -ss setelah -i agar frame-accurate
    cmd = ["ffmpeg", "-y", "-i", input_path]
    next_input_idx = 1
    watermark_idx = None
    sfx_idx = None
    if watermark_path:
        cmd += ["-loop", "1", "-i", watermark_path]
        watermark_idx = next_input_idx
        next_input_idx += 1
    if sfx_path:
        # -itsoffset menggeser PTS file sfx (jam sendiri, mulai dari 0) supaya sejajar dengan
        # jam absolut input utama (yang tetap dipertahankan karena -ss dipasang sebagai output
        # option demi frame-accuracy) — tanpa ini, filter -ss/-t global di bawah akan salah
        # memotong/membuang audio efek karena PTS-nya tidak nyambung dengan window clip.
        cmd += ["-itsoffset", f"{start:.3f}", "-i", sfx_path]
        sfx_idx = next_input_idx
        next_input_idx += 1
    cmd += ["-ss", f"{start:.3f}", "-t", f"{duration:.3f}"]

    video_filters = build_video_filters(edits, width, height, clip_start=start)
    audio_filters = build_audio_filters(edits, duration)

    complex_parts = []
    video_label = None
    if watermark_path:
        wm_scale_pct = _clamp(float(watermark.get("scale", 20) or 20), 5, 100)
        wm_opacity = _clamp(float(watermark.get("opacity", 100) or 100), 0, 100) / 100
        wm_w = max(int(width * wm_scale_pct / 100), 2)
        x_expr, y_expr = _overlay_xy(watermark.get("position", "top-right"))

        base_chain = ",".join(video_filters) if video_filters else "null"
        complex_parts.append(f"[0:v]{base_chain}[base]")
        complex_parts.append(f"[{watermark_idx}:v]scale={wm_w}:-1,format=rgba,colorchannelmixer=aa={wm_opacity:.3f}[wm]")
        complex_parts.append(f"[base][wm]overlay={x_expr}:{y_expr}:shortest=1[vout]")
        video_label = "[vout]"
    elif video_filters:
        cmd += ["-vf", ",".join(video_filters)]

    audio_label = None
    if sfx_idx is not None:
        # Efek suara: audio kedua yang ditunda (adelay) ke titik waktu tertentu di clip,
        # lalu di-mix dengan audio asli (kalau audio asli tidak di-mute).
        delay_ms = int(round(max(float(sound_effect.get("time", 0) or 0), 0) * 1000))
        effect_volume = _clamp(float(sound_effect.get("volume", 100) or 100), 0, 300) / 100
        complex_parts.append(f"[{sfx_idx}:a]adelay={delay_ms}|{delay_ms}:all=1,volume={effect_volume:.3f}[sfx]")

        if audio_filters is None:
            audio_label = "[sfx]"
        else:
            main_chain = ",".join(audio_filters) if audio_filters else None
            main_label = "[a0]" if main_chain else "[0:a]"
            if main_chain:
                complex_parts.append(f"[0:a]{main_chain}[a0]")
            complex_parts.append(f"{main_label}[sfx]amix=inputs=2:duration=first:dropout_transition=0[aout]")
            audio_label = "[aout]"

    if complex_parts:
        cmd += ["-filter_complex", ";".join(complex_parts)]
        cmd += ["-map", video_label or "0:v"]
        cmd += ["-map", audio_label or "0:a?"]

    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]

    if audio_label is not None:
        cmd += ["-c:a", "aac"]
    elif audio_filters is None:
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
