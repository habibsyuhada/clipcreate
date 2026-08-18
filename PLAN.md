# Video Clipper — Plan

Aplikasi lokal untuk memotong video (hasil download YouTube) menjadi beberapa clip, dengan fitur edit dasar berbasis FFmpeg. Jalan sepenuhnya offline di komputer sendiri.

## Tech Stack

- **Backend:** Python + FastAPI, jalan di `http://localhost:8000`
- **Frontend:** HTML/CSS/JS vanilla (single page, di-serve oleh FastAPI). Tanpa framework berat.
- **Video processing:** FFmpeg (harus sudah terinstall dan ada di PATH — kalau tidak ada, tampilkan error yang jelas saat startup)
- **Persistence:** File JSON lokal per video (daftar clip + pengaturan editnya)
- Tidak butuh internet sama sekali

## Struktur Project

```
video-clipper/
├── app.py              # Entry point FastAPI
├── clipper/
│   ├── ffmpeg.py       # Builder perintah FFmpeg (cut, crop, speed, text, audio, concat)
│   ├── jobs.py         # Render queue & status (background, non-blocking)
│   └── projects.py     # Load/save daftar clip ke JSON
├── static/
│   ├── index.html
│   ├── style.css       # Dark mode, bersih, sederhana
│   └── app.js
├── requirements.txt
└── README.md           # Cara install & menjalankan
```

Jalankan dengan satu perintah: `python app.py`, lalu buka `http://localhost:8000`.

## Fitur

### 1. Buka & Putar Video
- Pilih file video dari komputer (file picker atau drag & drop), format utama mp4
- Player HTML5: play/pause, seek, volume, kecepatan playback 0.5x–2x
- Backend serve file video via endpoint streaming (support HTTP range request agar seek lancar)

### 2. Penandaan Clip
- Tombol **Set Start** dan **Set End** berdasarkan posisi playhead saat ini
- Bisa ketik timestamp manual (`hh:mm:ss` atau `mm:ss`)
- **Add Clip** menambahkan segmen ke daftar; satu video bisa punya banyak clip
- Setiap clip di daftar bisa:
  - Preview (playhead lompat ke start clip)
  - Edit start/end
  - Rename nama file output (default: `namavideo_clip1.mp4`, dst)
  - Hapus
- Visualisasi segmen di bar timeline di bawah player (blok berwarna sesuai posisi start–end)
- Keyboard shortcut: `I` = set start, `O` = set end, `Space` = play/pause, `←`/`→` = mundur/maju 5 detik

### 3. Edit per Clip (Level 1 — berbasis FFmpeg)
Setiap clip punya panel pengaturan edit (semua opsional, default: tanpa edit):

- **Crop / aspect ratio:** Original, 9:16 (shorts/reels), 1:1, 16:9
  - Crop dari tengah frame secara default; sediakan pilihan anchor kiri/tengah/kanan
- **Teks statis:** satu baris teks overlay (drawtext)
  - Pengaturan: isi teks, posisi (atas/tengah/bawah), ukuran font, warna teks + outline agar terbaca
- **Kecepatan:** 0.5x, 0.75x, 1x, 1.25x, 1.5x, 2x (video + audio disesuaikan bersama via setpts + atempo)
- **Audio:** volume (0–200%), fade in/out (durasi dalam detik), atau mute
- Tampilkan ringkasan edit aktif pada tiap item clip di daftar (badge kecil, misal "9:16 • 1.5x • teks")

### 4. Gabung Clip (Concat)
- Mode opsional: pilih beberapa clip dari daftar → **Merge & Render** menjadi satu file
- Urutan clip bisa diatur (naik/turun)
- Catatan implementasi: karena tiap clip bisa punya edit berbeda, gabung dilakukan setelah tiap clip dirender (concat hasil akhir), pastikan resolusi/fps disamakan sebelum concat

### 5. Render
- Tombol **Render All** memproses semua clip di daftar (dan job merge jika ada)
- Dua mode potong:
  - **Cepat (stream copy, `-c copy`)** — default HANYA jika clip tidak punya edit apa pun; potongan bisa meleset 1–2 detik di keyframe
  - **Akurat (re-encode)** — otomatis dipakai jika clip punya edit (crop/teks/speed/audio memang butuh re-encode), atau bisa dipilih manual
- Output ke folder `clips/` di sebelah file video sumber
- Render jalan di background (queue), frontend polling status per clip: `queued → processing → done / error`
- Kalau error, tampilkan pesan FFmpeg-nya (dipendekkan) supaya bisa didiagnosis

### 6. Persistence
- Daftar clip + pengaturan editnya disimpan otomatis ke file JSON per video
- Buka lagi video yang sama → daftar clip dan pengaturannya kembali muncul

## Detail Teknis Penting

- **Re-encode settings:** H.264 (`libx264`, preset `veryfast`, CRF 20) + AAC audio — kompatibel di mana-mana
- **Speed + audio:** gunakan `setpts` untuk video dan rantai `atempo` untuk audio (atempo hanya support 0.5–2.0 per filter, jadi chain kalau perlu)
- **Drawtext:** pastikan escaping karakter khusus (titik dua, kutip) di teks user; gunakan font default sistem atau bundel satu font
- **Crop 9:16 dari video 16:9:** hitung `crop=ih*9/16:ih:x_anchor:0`
- **Jangan blocking:** render pakai worker/thread terpisah, satu job jalan berurutan (queue) agar tidak makan CPU berlebihan
- **Validasi:** start < end, timestamp tidak melebihi durasi video, nama file output aman (sanitize)

## Urutan Pengerjaan

1. Skeleton FastAPI + serve frontend + streaming video dengan range request
2. Player + set start/end + daftar clip + timeline visual + shortcut
3. Render dasar (cut saja, stream copy & re-encode) + queue + status polling
4. Persistence JSON
5. Panel edit per clip: crop → speed → audio → teks
6. Merge/concat
7. Polish UI (dark mode) + README

## Cara Verifikasi

- Potong 3 clip dari satu video, cek durasi hasil sesuai timestamp
- Clip dengan crop 9:16 → cek resolusi output benar
- Clip dengan speed 2x → cek durasi setengahnya dan audio tidak berubah pitch berlebihan
- Merge 2 clip beda pengaturan → hasil jadi satu file yang bisa diputar normal
- Tutup aplikasi, buka lagi dengan video sama → daftar clip masih ada
