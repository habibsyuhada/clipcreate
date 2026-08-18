# Video Clipper

Aplikasi lokal untuk memotong video (mis. hasil download YouTube) menjadi beberapa clip, dengan fitur edit dasar berbasis FFmpeg. Jalan sepenuhnya offline di komputer sendiri — tidak butuh internet sama sekali.

## Fitur

- Buka video lokal (browser file di server, atau paste path lengkap), player HTML5 dengan seek cepat (HTTP Range).
- Tandai start/end clip dari posisi playhead atau ketik timestamp manual, banyak clip per video.
- Timeline visual dengan thumbnail sprite (preview frame) dan waveform audio di background — memudahkan cari posisi potong presisi. Arahkan mouse ke timeline untuk preview frame (hover scrubbing). Thumbnail & waveform di-cache otomatis (regenerate hanya kalau file video berubah), keyboard shortcut `I`/`O`/`Space`/`←`/`→`.
- Edit per clip (opsional): crop 9:16 / 1:1 / 16:9 dengan anchor, kecepatan 0.5x–2x, volume/fade/mute audio, teks overlay.
- Render clip satu-satu atau semua sekaligus, lewat render queue di background (tidak blocking), status `queued → processing → done/error`.
- Mode potong cepat (`-c copy`) otomatis dipakai jika clip tanpa edit apa pun, mode akurat (re-encode) otomatis dipakai jika ada edit.
- Gabung (merge) beberapa clip terpilih menjadi satu file, resolusi/fps otomatis disamakan sebelum digabung.
- Daftar clip & pengaturan editnya tersimpan otomatis ke file JSON di sebelah video sumber — buka lagi videonya, daftar clip muncul kembali.

## Instalasi

### 1. FFmpeg

Aplikasi ini butuh `ffmpeg` dan `ffprobe` yang bisa diakses dari PATH.

- **macOS:** `brew install ffmpeg`
- **Ubuntu/Debian:** `sudo apt install ffmpeg`
- **Windows:** download dari https://ffmpeg.org/download.html, lalu tambahkan folder `bin`-nya ke PATH.

Cek instalasi dengan `ffmpeg -version` di terminal.

### 2. Python dependencies

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Menjalankan

```bash
python app.py
```

Lalu buka `http://localhost:8000` di browser.

Jika FFmpeg belum terpasang, aplikasi tetap jalan tapi akan menampilkan peringatan jelas (di terminal saat start, dan badge merah di UI) — fitur render tidak akan berfungsi sampai FFmpeg terpasang.

## Cara Pakai Singkat

1. Klik **Buka Video**, navigasi folder di server lalu pilih file video (atau paste path lengkap dan tekan Enter).
2. Putar video, tekan `I` untuk set start dan `O` untuk set end pada posisi playhead saat ini, lalu **Add Clip**. Bisa juga ketik timestamp manual (`mm:ss` atau `hh:mm:ss`).
3. Klik **Edit** pada sebuah clip untuk atur crop/kecepatan/audio/teks (opsional).
4. Klik **Render** per clip atau **Render All** untuk semua clip. Status akan ter-update otomatis.
5. Untuk menggabungkan beberapa clip: klik **Merge Mode**, centang clip yang ingin digabung (urutan mengikuti urutan di daftar — pakai tombol ↑/↓ untuk mengatur ulang), isi nama file, klik **Merge & Render**.
6. Hasil render ada di folder `clips/` di sebelah file video sumber.

## Struktur Project

```
clipcreate/
├── app.py              # Entry point FastAPI
├── clipper/
│   ├── ffmpeg.py        # Builder perintah FFmpeg (cut, crop, speed, text, audio, concat)
│   ├── jobs.py           # Render queue & status (background, non-blocking)
│   ├── projects.py       # Load/save daftar clip ke JSON
│   └── thumbnails.py     # Generate & cache thumbnail sprite + waveform untuk timeline
├── static/
│   ├── index.html
│   ├── style.css        # Dark mode
│   └── app.js
├── requirements.txt
└── README.md
```

## Detail Teknis

- Re-encode: H.264 (`libx264`, preset `veryfast`, CRF 20) + AAC audio.
- Speed memakai `setpts` (video) dan chain `atempo` (audio, tiap filter dibatasi 0.5x–2.0x).
- Crop 9:16/1:1/16:9 dihitung dari resolusi asli video (dari `ffprobe`) dengan anchor kiri/tengah/kanan.
- Mode potong cepat (`-c copy`) bisa meleset 1–2 detik di keyframe terdekat — dipakai otomatis hanya jika clip tidak punya edit apa pun.
- Render jalan berurutan (satu job aktif dalam satu waktu) di worker thread terpisah agar server tetap responsif.
- Nama file output disanitasi otomatis agar aman untuk filesystem.
- Thumbnail sprite (JPEG) & waveform (PNG) di-generate via FFmpeg lalu di-cache di folder tersembunyi `.<namavideo>.assets/` di sebelah video; regenerate otomatis kalau ukuran/waktu-modifikasi video berubah.
