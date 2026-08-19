"use strict";

const CLIP_COLORS = ["#5eb0ef", "#f5a742", "#65d68a", "#e56b8f", "#b98af0", "#f2d94e", "#4fd1c5", "#f07a5f"];

const state = {
  videoPath: null,
  info: null, // {duration, width, height, filename}
  clips: [],
  mergeMode: false,
  pendingStart: null,
  pendingEnd: null,
  thumbMeta: null, // {count, thumb_width, thumb_height, interval}
  timelineDragging: false,
};

const MIN_CLIP_DURATION = 0.2;

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const videoEl = $("#videoEl");
const app = $("#app");

// ---------- Utils ----------

function formatTime(seconds) {
  if (seconds == null || isNaN(seconds)) return "00:00.000";
  const neg = seconds < 0;
  seconds = Math.abs(seconds);
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const sStr = s.toFixed(3).padStart(6, "0");
  const body = h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${sStr}`
    : `${String(m).padStart(2, "0")}:${sStr}`;
  return neg ? `-${body}` : body;
}

function parseTime(str) {
  if (str == null) return null;
  str = str.trim();
  if (str === "") return null;
  const parts = str.split(":").map((p) => p.trim());
  if (parts.some((p) => p === "" || isNaN(Number(p)))) return null;
  let seconds = 0;
  if (parts.length === 3) {
    seconds = Number(parts[0]) * 3600 + Number(parts[1]) * 60 + Number(parts[2]);
  } else if (parts.length === 2) {
    seconds = Number(parts[0]) * 60 + Number(parts[1]);
  } else if (parts.length === 1) {
    seconds = Number(parts[0]);
  } else {
    return null;
  }
  return seconds;
}

function clamp(v, lo, hi) {
  return Math.min(Math.max(v, lo), hi);
}

function uuid() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function defaultEdits() {
  return {
    crop: "original",
    crop_anchor: "center",
    speed: 1,
    texts: [],
    audio: { volume: 100, fade_in: 0, fade_out: 0, mute: false },
    watermark: { enabled: false, image_path: "", position: "top-right", scale: 20, opacity: 100 },
    subtitle: { enabled: false, path: "", size: 24 },
  };
}

const LEGACY_TEXT_POSITION_MAP = { top: "top-center", middle: "middle-center", bottom: "bottom-center" };

// Migrasi format edit lama (single `text`) + isi default field yang belum ada di project tersimpan.
function normalizeEdits(edits) {
  const base = defaultEdits();
  if (!edits) return base;
  const merged = {
    ...base,
    ...edits,
    audio: { ...base.audio, ...(edits.audio || {}) },
    watermark: { ...base.watermark, ...(edits.watermark || {}) },
    subtitle: { ...base.subtitle, ...(edits.subtitle || {}) },
    texts: Array.isArray(edits.texts) ? edits.texts.map((t) => ({ ...t })) : [],
  };
  if (edits.text && edits.text.content && merged.texts.length === 0) {
    merged.texts = [{
      content: edits.text.content,
      position: LEGACY_TEXT_POSITION_MAP[edits.text.position] || edits.text.position || "middle-center",
      size: edits.text.size || 36,
      color: edits.text.color || "#ffffff",
      outline: edits.text.outline || "#000000",
    }];
  }
  delete merged.text;
  return merged;
}

function editBadges(edits) {
  if (!edits) return [];
  const badges = [];
  if (edits.crop && edits.crop !== "original") badges.push(edits.crop);
  const speed = Number(edits.speed || 1);
  if (Math.abs(speed - 1) > 1e-6) badges.push(`${speed}x`);
  const texts = (edits.texts || []).filter((t) => t.content);
  if (texts.length === 1) badges.push("teks");
  else if (texts.length > 1) badges.push(`teks x${texts.length}`);
  const watermark = edits.watermark || {};
  if (watermark.enabled && watermark.image_path) badges.push("watermark");
  const subtitle = edits.subtitle || {};
  if (subtitle.enabled && subtitle.path) badges.push("subtitle");
  const audio = edits.audio || {};
  if (audio.mute) badges.push("mute");
  else if (Number(audio.volume || 100) !== 100) badges.push(`${audio.volume}%`);
  if (Number(audio.fade_in || 0) > 0 || Number(audio.fade_out || 0) > 0) badges.push("fade");
  return badges;
}

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

// ---------- Health ----------

async function checkHealth() {
  try {
    const data = await api("/api/health");
    const badge = $("#ffmpegBadge");
    if (data.ffmpeg_ok) {
      badge.textContent = "FFmpeg OK";
      badge.className = "badge badge-ok";
    } else {
      badge.textContent = "FFmpeg TIDAK ditemukan — install FFmpeg dulu";
      badge.className = "badge badge-error";
    }
  } catch (e) {
    $("#ffmpegBadge").textContent = "Gagal cek FFmpeg";
  }
}

// ---------- File browser ----------

const browseModal = $("#browseModal");

async function openBrowse(path) {
  browseModal.classList.remove("hidden");
  await loadBrowseDir(path);
}

function closeBrowse() {
  browseModal.classList.add("hidden");
}

async function loadBrowseDir(path) {
  const qs = path ? `?path=${encodeURIComponent(path)}` : "";
  const data = await api(`/api/browse${qs}`);
  $("#browsePathInput").value = data.current;
  $("#browseUpBtn").disabled = !data.parent;
  $("#browseUpBtn").dataset.parent = data.parent || "";

  const list = $("#browseList");
  list.innerHTML = "";
  data.entries.forEach((entry) => {
    const li = document.createElement("li");
    li.className = "browse-item" + (entry.is_video ? " browse-video" : "");
    li.textContent = (entry.is_dir ? "📁 " : "🎞️ ") + entry.name;
    li.addEventListener("click", () => {
      if (entry.is_dir) {
        loadBrowseDir(entry.path);
      } else if (entry.is_video) {
        closeBrowse();
        selectVideo(entry.path);
      }
    });
    list.appendChild(li);
  });
}

$("#openBtn").addEventListener("click", () => openBrowse());
$("#browseCloseBtn").addEventListener("click", closeBrowse);
$("#browseUpBtn").addEventListener("click", (e) => {
  const parent = e.currentTarget.dataset.parent;
  if (parent) loadBrowseDir(parent);
});
$("#browsePathInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const val = e.currentTarget.value.trim();
    if (/\.(mp4|mov|mkv|avi|webm|m4v)$/i.test(val)) {
      closeBrowse();
      selectVideo(val);
    } else {
      loadBrowseDir(val);
    }
  }
});

// drag & drop (path lengkap tidak selalu tersedia di browser biasa, jadi minta user paste path jika gagal)
const dropZone = $("#dropZone");
["dragover", "dragenter"].forEach((evt) =>
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropZone.addEventListener(evt, (e) => {
    dropZone.classList.remove("drag-over");
  })
);
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  const file = e.dataTransfer.files && e.dataTransfer.files[0];
  if (file && file.path) {
    // tersedia di beberapa runtime desktop (mis. Electron); di browser biasa file.path kosong
    selectVideo(file.path);
  } else {
    openBrowse();
  }
});

// ---------- Select video ----------

async function selectVideo(path) {
  try {
    const info = await api(`/api/video/info?path=${encodeURIComponent(path)}`);
    state.videoPath = info.path;
    state.info = info;
    videoEl.src = `/video/stream?path=${encodeURIComponent(info.path)}`;
    app.classList.remove("hidden");
    document.title = `Video Clipper — ${info.filename}`;

    const project = await api(`/api/project?path=${encodeURIComponent(info.path)}`);
    state.clips = (project.clips || []).map((c) => ({ ...c, edits: normalizeEdits(c.edits) }));
    renderAll();
    loadTimelineVisuals();
  } catch (e) {
    alert(`Gagal membuka video: ${e.message}`);
  }
}

// ---------- Timeline thumbnail sprite & waveform ----------

async function loadTimelineVisuals() {
  if (!state.videoPath) return;
  state.thumbMeta = null;
  loadThumbnails();
  loadWaveform();
}

async function loadThumbnails() {
  const thumbImg = $("#timelineThumbs");
  thumbImg.classList.add("hidden");
  try {
    const meta = await api(`/api/video/thumbnails?path=${encodeURIComponent(state.videoPath)}`);
    state.thumbMeta = meta;
    thumbImg.onload = () => thumbImg.classList.remove("hidden");
    thumbImg.src = `/video/thumbnail-sprite?path=${encodeURIComponent(state.videoPath)}&t=${Date.now()}`;
  } catch (e) {
    console.error("Gagal membuat thumbnail timeline", e);
  }
}

async function loadWaveform() {
  const wfImg = $("#timelineWaveform");
  wfImg.classList.add("hidden");
  try {
    const res = await api(`/api/video/waveform?path=${encodeURIComponent(state.videoPath)}`);
    if (!res.has_audio) return;
    wfImg.onload = () => wfImg.classList.remove("hidden");
    wfImg.src = `/video/waveform-image?path=${encodeURIComponent(state.videoPath)}&t=${Date.now()}`;
  } catch (e) {
    console.error("Gagal membuat waveform timeline", e);
  }
}

const HOVER_THUMB_W = 140;
const hoverPreview = $("#timelineHoverPreview");
const hoverThumb = $("#hoverThumb");
const hoverTimeEl = $("#hoverTime");

function showHoverPreview(t, rect) {
  const x = clamp((t / state.info.duration) * rect.width, 0, rect.width);
  hoverTimeEl.textContent = formatTime(t);
  hoverPreview.style.left = `${clamp(x, HOVER_THUMB_W / 2, rect.width - HOVER_THUMB_W / 2)}px`;
  hoverPreview.classList.remove("hidden");

  const meta = state.thumbMeta;
  if (meta && meta.count && meta.interval > 0) {
    const boxH = Math.round(HOVER_THUMB_W * (meta.thumb_height / meta.thumb_width));
    const idx = clamp(Math.floor(t / meta.interval), 0, meta.count - 1);
    hoverThumb.style.width = `${HOVER_THUMB_W}px`;
    hoverThumb.style.height = `${boxH}px`;
    hoverThumb.style.backgroundImage = `url(/video/thumbnail-sprite?path=${encodeURIComponent(state.videoPath)})`;
    hoverThumb.style.backgroundSize = `${meta.count * HOVER_THUMB_W}px ${boxH}px`;
    hoverThumb.style.backgroundPosition = `-${idx * HOVER_THUMB_W}px 0`;
  } else {
    hoverThumb.style.backgroundImage = "none";
  }
}

function hideHoverPreview() {
  hoverPreview.classList.add("hidden");
}

$("#timeline").addEventListener("mousemove", (e) => {
  if (!state.info || !state.info.duration || state.timelineDragging) return;
  const rect = $("#timeline").getBoundingClientRect();
  const x = clamp(e.clientX - rect.left, 0, rect.width);
  const t = (rect.width ? x / rect.width : 0) * state.info.duration;
  showHoverPreview(t, rect);
});

$("#timeline").addEventListener("mouseleave", () => {
  if (!state.timelineDragging) hideHoverPreview();
});

// ---------- Player controls ----------

$("#playBtn").addEventListener("click", () => togglePlay());

function togglePlay() {
  if (videoEl.paused) videoEl.play();
  else videoEl.pause();
}

$("#speedSelect").addEventListener("change", (e) => {
  videoEl.playbackRate = Number(e.target.value);
});

videoEl.addEventListener("timeupdate", updateTimeDisplay);
videoEl.addEventListener("loadedmetadata", updateTimeDisplay);

function updateTimeDisplay() {
  const dur = state.info ? state.info.duration : videoEl.duration || 0;
  $("#timeDisplay").textContent = `${formatTime(videoEl.currentTime)} / ${formatTime(dur)}`;
  updatePlayhead();
}

function updatePlayhead() {
  const dur = state.info ? state.info.duration : videoEl.duration || 0;
  if (!dur) return;
  const pct = clamp(videoEl.currentTime / dur, 0, 1) * 100;
  $("#timelinePlayhead").style.left = `${pct}%`;
}

// ---------- Mark start/end ----------

$("#setStartBtn").addEventListener("click", () => setStart());
$("#setEndBtn").addEventListener("click", () => setEnd());
$("#addClipBtn").addEventListener("click", () => addClip());

function setStart() {
  state.pendingStart = videoEl.currentTime;
  $("#startInput").value = formatTime(state.pendingStart);
}

function setEnd() {
  state.pendingEnd = videoEl.currentTime;
  $("#endInput").value = formatTime(state.pendingEnd);
}

$("#startInput").addEventListener("change", (e) => {
  const t = parseTime(e.target.value);
  if (t != null) state.pendingStart = t;
});
$("#endInput").addEventListener("change", (e) => {
  const t = parseTime(e.target.value);
  if (t != null) state.pendingEnd = t;
});

function addClip() {
  if (!state.info) return;
  let start = state.pendingStart != null ? state.pendingStart : 0;
  let end = state.pendingEnd != null ? state.pendingEnd : state.info.duration;
  start = clamp(start, 0, state.info.duration);
  end = clamp(end, 0, state.info.duration);
  if (start >= end) {
    alert("Start harus lebih kecil dari End");
    return;
  }
  const clip = {
    id: uuid(),
    name: `${baseName(state.info.filename)}_clip${state.clips.length + 1}.mp4`,
    start,
    end,
    edits: defaultEdits(),
    status: "idle",
    error: null,
    output_path: null,
  };
  state.clips.push(clip);
  state.pendingStart = null;
  state.pendingEnd = null;
  $("#startInput").value = "";
  $("#endInput").value = "";
  renderAll();
  saveProject();
}

function baseName(filename) {
  return filename.replace(/\.[^.]+$/, "");
}

// ---------- Timeline ----------

function positionSegment(seg, clip, dur) {
  seg.style.left = `${(clip.start / dur) * 100}%`;
  seg.style.width = `${Math.max(((clip.end - clip.start) / dur) * 100, 0.3)}%`;
}

function updateClipTimeLabel(clip) {
  const li = $(`.clip-item[data-id="${clip.id}"]`);
  if (li) li.querySelector(".clip-time").textContent = `${formatTime(clip.start)} → ${formatTime(clip.end)}`;
}

function wireSegmentDrag(seg, handleL, handleR, clip, dur) {
  let mode = null; // "move" | "left" | "right"
  let startX = 0;
  let origStart = 0;
  let origEnd = 0;
  let dragged = false;

  function onMove(e) {
    if (!mode) return;
    const rect = $("#timeline").getBoundingClientRect();
    const deltaT = ((e.clientX - startX) / rect.width) * dur;
    if (Math.abs(e.clientX - startX) > 2) dragged = true;

    if (mode === "left") {
      clip.start = clamp(origStart + deltaT, 0, clip.end - MIN_CLIP_DURATION);
    } else if (mode === "right") {
      clip.end = clamp(origEnd + deltaT, clip.start + MIN_CLIP_DURATION, dur);
    } else {
      const length = origEnd - origStart;
      clip.start = clamp(origStart + deltaT, 0, dur - length);
      clip.end = clip.start + length;
    }

    positionSegment(seg, clip, dur);
    updateClipTimeLabel(clip);
    showHoverPreview(mode === "left" ? clip.start : clip.end, rect);
  }

  function onUp() {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
    state.timelineDragging = false;
    hideHoverPreview();
    if (mode && dragged) {
      renderClipList();
      saveProject();
    }
    mode = null;
  }

  function onDown(e, m) {
    e.preventDefault();
    e.stopPropagation();
    mode = m;
    dragged = false;
    startX = e.clientX;
    origStart = clip.start;
    origEnd = clip.end;
    state.timelineDragging = true;
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
  }

  handleL.addEventListener("pointerdown", (e) => onDown(e, "left"));
  handleR.addEventListener("pointerdown", (e) => onDown(e, "right"));
  seg.addEventListener("pointerdown", (e) => onDown(e, "move"));
  seg.addEventListener("click", () => {
    if (!dragged) videoEl.currentTime = clip.start;
  });
}

function renderTimeline() {
  const container = $("#timelineSegments");
  container.innerHTML = "";
  if (!state.info || !state.info.duration) return;
  const dur = state.info.duration;
  state.clips.forEach((clip, idx) => {
    const seg = document.createElement("div");
    seg.className = "timeline-segment";
    seg.dataset.id = clip.id;
    positionSegment(seg, clip, dur);
    seg.style.background = CLIP_COLORS[idx % CLIP_COLORS.length];
    seg.title = clip.name;

    const handleL = document.createElement("div");
    handleL.className = "seg-handle seg-handle-left";
    const handleR = document.createElement("div");
    handleR.className = "seg-handle seg-handle-right";
    seg.appendChild(handleL);
    seg.appendChild(handleR);

    wireSegmentDrag(seg, handleL, handleR, clip, dur);

    container.appendChild(seg);
  });
  updatePlayhead();
}

$("#timeline").addEventListener("click", (e) => {
  if (!state.info || !state.info.duration) return;
  if (e.target.closest(".timeline-segment")) return;
  const rect = $("#timeline").getBoundingClientRect();
  const pct = clamp((e.clientX - rect.left) / rect.width, 0, 1);
  videoEl.currentTime = pct * state.info.duration;
});

// ---------- Clip list rendering ----------

const clipTemplate = $("#clipItemTemplate");

function renderClipList() {
  const list = $("#clipList");
  list.innerHTML = "";
  state.clips.forEach((clip, idx) => {
    const node = clipTemplate.content.cloneNode(true);
    const li = node.querySelector(".clip-item");
    li.dataset.id = clip.id;
    li.querySelector(".clip-color-dot").style.background = CLIP_COLORS[idx % CLIP_COLORS.length];

    const nameInput = li.querySelector(".clip-name-input");
    nameInput.value = clip.name;
    nameInput.addEventListener("change", () => {
      clip.name = nameInput.value.trim() || clip.name;
      saveProject();
    });

    li.querySelector(".clip-time").textContent = `${formatTime(clip.start)} → ${formatTime(clip.end)}`;

    const badgeWrap = li.querySelector(".clip-badges");
    editBadges(clip.edits).forEach((b) => {
      const span = document.createElement("span");
      span.className = "badge badge-edit";
      span.textContent = b;
      badgeWrap.appendChild(span);
    });

    const statusEl = li.querySelector(".clip-status");
    statusEl.textContent = clip.status || "idle";
    statusEl.className = "clip-status badge " + statusClass(clip.status);

    const errEl = li.querySelector(".clip-error");
    if (clip.error) {
      errEl.textContent = clip.error;
      errEl.classList.remove("hidden");
    } else {
      errEl.classList.add("hidden");
    }

    li.querySelector(".clip-preview-btn").addEventListener("click", () => {
      videoEl.currentTime = clip.start;
      videoEl.play();
    });

    li.querySelector(".clip-move-up-btn").addEventListener("click", () => moveClip(clip.id, -1));
    li.querySelector(".clip-move-down-btn").addEventListener("click", () => moveClip(clip.id, 1));

    li.querySelector(".clip-edit-btn").addEventListener("click", () => {
      li.querySelector(".clip-edit-panel").classList.toggle("hidden");
    });

    li.querySelector(".clip-render-btn").addEventListener("click", () => renderClips([clip.id]));

    li.querySelector(".clip-delete-btn").addEventListener("click", () => {
      state.clips = state.clips.filter((c) => c.id !== clip.id);
      renderAll();
      saveProject();
    });

    const mergeCheck = li.querySelector(".clip-merge-check");
    mergeCheck.dataset.id = clip.id;
    if (state.mergeMode) mergeCheck.classList.remove("hidden");
    else mergeCheck.classList.add("hidden");

    wireEditPanel(li, clip);

    list.appendChild(node);
  });
}

function statusClass(status) {
  switch (status) {
    case "done":
      return "badge-ok";
    case "error":
      return "badge-error";
    case "processing":
    case "queued":
      return "badge-warn";
    default:
      return "badge-muted";
  }
}

function moveClip(id, dir) {
  const idx = state.clips.findIndex((c) => c.id === id);
  const newIdx = idx + dir;
  if (idx < 0 || newIdx < 0 || newIdx >= state.clips.length) return;
  const [item] = state.clips.splice(idx, 1);
  state.clips.splice(newIdx, 0, item);
  renderAll();
  saveProject();
}

const textLayerTemplate = $("#textLayerTemplate");

function addTextLayerRow(container, layer) {
  const node = textLayerTemplate.content.cloneNode(true);
  const row = node.querySelector(".text-layer-row");
  row.querySelector(".text-layer-content").value = layer.content || "";
  row.querySelector(".text-layer-position").value = layer.position || "middle-center";
  row.querySelector(".text-layer-size").value = layer.size || 36;
  row.querySelector(".text-layer-color").value = layer.color || "#ffffff";
  row.querySelector(".text-layer-outline").value = layer.outline || "#000000";
  row.querySelector(".text-layer-remove-btn").addEventListener("click", () => row.remove());
  container.appendChild(row);
}

function readTextLayers(container) {
  return $$(".text-layer-row", container)
    .map((row) => ({
      content: row.querySelector(".text-layer-content").value,
      position: row.querySelector(".text-layer-position").value,
      size: Number(row.querySelector(".text-layer-size").value) || 36,
      color: row.querySelector(".text-layer-color").value,
      outline: row.querySelector(".text-layer-outline").value,
    }))
    .filter((t) => t.content.trim() !== "");
}

function wireEditPanel(li, clip) {
  const e = clip.edits;
  li.querySelector(".edit-crop").value = e.crop;
  li.querySelector(".edit-anchor").value = e.crop_anchor;
  li.querySelector(".edit-speed").value = String(e.speed);
  li.querySelector(".edit-volume").value = e.audio.volume;
  li.querySelector(".edit-fadein").value = e.audio.fade_in;
  li.querySelector(".edit-fadeout").value = e.audio.fade_out;
  li.querySelector(".edit-mute").checked = !!e.audio.mute;

  const textsList = li.querySelector(".text-layers-list");
  textsList.innerHTML = "";
  (e.texts || []).forEach((layer) => addTextLayerRow(textsList, layer));
  li.querySelector(".text-layer-add-btn").addEventListener("click", () => {
    addTextLayerRow(textsList, { content: "", position: "middle-center", size: 36, color: "#ffffff", outline: "#000000" });
  });

  li.querySelector(".edit-watermark-enabled").checked = !!e.watermark.enabled;
  li.querySelector(".edit-watermark-path").value = e.watermark.image_path || "";
  li.querySelector(".edit-watermark-position").value = e.watermark.position || "top-right";
  li.querySelector(".edit-watermark-scale").value = e.watermark.scale;
  li.querySelector(".edit-watermark-opacity").value = e.watermark.opacity;

  li.querySelector(".edit-subtitle-enabled").checked = !!e.subtitle.enabled;
  li.querySelector(".edit-subtitle-path").value = e.subtitle.path || "";
  li.querySelector(".edit-subtitle-size").value = e.subtitle.size;

  li.querySelector(".edit-save-btn").addEventListener("click", async () => {
    clip.edits = {
      crop: li.querySelector(".edit-crop").value,
      crop_anchor: li.querySelector(".edit-anchor").value,
      speed: Number(li.querySelector(".edit-speed").value),
      texts: readTextLayers(textsList),
      audio: {
        volume: Number(li.querySelector(".edit-volume").value),
        fade_in: Number(li.querySelector(".edit-fadein").value),
        fade_out: Number(li.querySelector(".edit-fadeout").value),
        mute: li.querySelector(".edit-mute").checked,
      },
      watermark: {
        enabled: li.querySelector(".edit-watermark-enabled").checked,
        image_path: li.querySelector(".edit-watermark-path").value.trim(),
        position: li.querySelector(".edit-watermark-position").value,
        scale: Number(li.querySelector(".edit-watermark-scale").value) || 20,
        opacity: Number(li.querySelector(".edit-watermark-opacity").value),
      },
      subtitle: {
        enabled: li.querySelector(".edit-subtitle-enabled").checked,
        path: li.querySelector(".edit-subtitle-path").value.trim(),
        size: Number(li.querySelector(".edit-subtitle-size").value) || 24,
      },
    };
    await saveProjectNow();
    renderAll();
  });
}

function renderAll() {
  renderClipList();
  renderTimeline();
}

// ---------- Persistence ----------

let saveTimer = null;

// Simpan langsung (tanpa debounce) — dipakai sebelum render/merge supaya server selalu
// pakai edits yang paling baru, bukan versi lama karena masih menunggu debounce selesai.
async function saveProjectNow() {
  if (!state.videoPath) return;
  clearTimeout(saveTimer);
  try {
    await api("/api/project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_path: state.videoPath, clips: state.clips }),
    });
  } catch (e) {
    console.error("Gagal menyimpan project", e);
  }
}

function saveProject() {
  if (!state.videoPath) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveProjectNow, 300);
}

// ---------- Render (FFmpeg) ----------

$("#renderAllBtn").addEventListener("click", () => renderClips(state.clips.map((c) => c.id)));

async function renderClips(clipIds) {
  if (!state.videoPath || clipIds.length === 0) return;
  try {
    await saveProjectNow(); // pastikan edit terbaru (mis. baru saja Simpan Edit) sudah tersimpan sebelum render dipicu
    const res = await api("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_path: state.videoPath, clip_ids: clipIds }),
    });
    clipIds.forEach((id) => {
      const clip = state.clips.find((c) => c.id === id);
      if (clip) {
        clip.status = "queued";
        clip.error = null;
      }
    });
    renderAll();
    pollJobs(Object.values(res.jobs));
  } catch (e) {
    alert(`Gagal memulai render: ${e.message}`);
  }
}

function pollJobs(jobIds) {
  if (!jobIds.length) return;
  const interval = setInterval(async () => {
    try {
      const res = await api(`/api/jobs?ids=${jobIds.join(",")}`);
      let allDone = true;
      res.jobs.forEach((job) => {
        const clipId = job.meta && job.meta.clip_id;
        if (clipId) {
          const clip = state.clips.find((c) => c.id === clipId);
          if (clip) {
            clip.status = job.status;
            clip.error = job.error;
          }
        }
        if (job.status === "queued" || job.status === "processing") allDone = false;
      });
      renderAll();
      if (allDone) {
        clearInterval(interval);
        // refresh dari server untuk sinkron output_path final
        const project = await api(`/api/project?path=${encodeURIComponent(state.videoPath)}`);
        state.clips = (project.clips || []).map((c) => ({ ...c, edits: normalizeEdits(c.edits) }));
        renderAll();
      }
    } catch (e) {
      clearInterval(interval);
      console.error("Polling job gagal", e);
    }
  }, 1200);
}

// ---------- Merge ----------

const mergeBar = $("#mergeBar");
$("#mergeModeBtn").addEventListener("click", () => {
  state.mergeMode = !state.mergeMode;
  mergeBar.classList.toggle("hidden", !state.mergeMode);
  $("#mergeModeBtn").classList.toggle("active", state.mergeMode);
  renderClipList();
});

$("#mergeTransition").addEventListener("change", (e) => {
  $("#mergeTransitionDuration").disabled = e.target.value === "none";
});

$("#mergeGoBtn").addEventListener("click", async () => {
  const checked = $$(".clip-merge-check:checked").map((el) => el.dataset.id);
  // urutkan sesuai urutan tampil di daftar (state.clips)
  const orderedIds = state.clips.filter((c) => checked.includes(c.id)).map((c) => c.id);
  const outputName = $("#mergeName").value.trim() || "merged.mp4";
  const transition = $("#mergeTransition").value;
  const transitionDuration = Number($("#mergeTransitionDuration").value) || 0.5;
  if (orderedIds.length < 2) {
    alert("Pilih minimal 2 clip untuk digabung");
    return;
  }
  const statusEl = $("#mergeStatus");
  statusEl.textContent = "Menggabungkan...";
  try {
    await saveProjectNow(); // pastikan edit/urutan clip terbaru sudah tersimpan sebelum merge dipicu
    const res = await api("/api/merge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        video_path: state.videoPath,
        clip_ids: orderedIds,
        output_name: outputName,
        transition,
        transition_duration: transitionDuration,
      }),
    });
    pollMergeJob(res.job_id, statusEl);
  } catch (e) {
    statusEl.textContent = `Gagal: ${e.message}`;
  }
});

function pollMergeJob(jobId, statusEl) {
  const interval = setInterval(async () => {
    try {
      const res = await api(`/api/jobs?ids=${jobId}`);
      const job = res.jobs[0];
      if (!job) return;
      if (job.status === "done") {
        const warning = job.meta && job.meta.warning;
        statusEl.textContent = `Selesai: ${job.meta.output_path}` + (warning ? ` (⚠ ${warning})` : "");
        clearInterval(interval);
      } else if (job.status === "error") {
        statusEl.textContent = `Error: ${job.error}`;
        clearInterval(interval);
      } else {
        statusEl.textContent = `Status: ${job.status}...`;
      }
    } catch (e) {
      clearInterval(interval);
    }
  }, 1200);
}

// ---------- Keyboard shortcuts ----------

document.addEventListener("keydown", (e) => {
  const tag = (e.target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "select" || tag === "textarea") return;
  if (!state.info) return;

  switch (e.key) {
    case " ":
      e.preventDefault();
      togglePlay();
      break;
    case "i":
    case "I":
      setStart();
      break;
    case "o":
    case "O":
      setEnd();
      break;
    case "ArrowLeft":
      e.preventDefault();
      videoEl.currentTime = clamp(videoEl.currentTime - 5, 0, state.info.duration);
      break;
    case "ArrowRight":
      e.preventDefault();
      videoEl.currentTime = clamp(videoEl.currentTime + 5, 0, state.info.duration);
      break;
  }
});

// ---------- Init ----------

checkHealth();
