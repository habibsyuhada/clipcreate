# Video Clipper

Aplikasi lokal untuk memotong video (mis. hasil download YouTube) menjadi beberapa clip, dengan fitur edit dasar berbasis FFmpeg. Jalan sepenuhnya offline di komputer sendiri — tidak butuh internet sama sekali.

## Fitur

- Buka video lokal (browser file di server, atau paste path lengkap), player HTML5 dengan seek cepat (HTTP Range).
- Tandai start/end clip dari posisi playhead atau ketik timestamp manual, banyak clip per video.
- Timeline visual dengan thumbnail sprite (preview frame) dan waveform audio di background — memudahkan cari posisi potong presisi. Arahkan mouse ke timeline untuk preview frame (hover scrubbing). Thumbnail & waveform di-cache otomatis (regenerate hanya kalau file video berubah), keyboard shortcut `I`/`O`/`Space`/`←`/`→`.
- Edit per clip (opsional): crop 9:16 / 1:1 / 16:9 dengan anchor, kecepatan 0.5x–2x, volume/fade/mute audio, multi-layer teks overlay (posisi grid 9 titik), watermark gambar (PNG/JPG dengan opacity & skala), dan burn-in subtitle dari file `.srt`.
- Efek meme: teks meme klasik satu klik (kapital, outline tebal, atas+bawah) lewat toggle "Meme" di tiap layer teks; filter visual Deep-fry / VHS-glitch / Hitam-putih untuk seluruh clip; efek "punch" sesaat di titik waktu tertentu — Zoom Punch, Shake (goyang kamera), atau Flash — dengan waktu, durasi, dan intensitas yang bisa diatur; dan efek suara (sound effect) — mixing file audio (MP3/WAV) milik sendiri ke titik waktu tertentu di clip, dengan volume yang bisa diatur. Aplikasi tidak menyediakan/mengunduh suara meme apa pun — sediakan file audionya sendiri (pastikan kamu punya hak pakainya).
- Render clip satu-satu atau semua sekaligus, lewat render queue di background (tidak blocking), status `queued → processing → done/error`.
- Mode potong cepat (`-c copy`) otomatis dipakai jika clip tanpa edit apa pun, mode akurat (re-encode) otomatis dipakai jika ada edit.
- Gabung (merge) beberapa clip terpilih menjadi satu file, resolusi/fps/audio otomatis disamakan sebelum digabung. Opsional pilih transisi antar clip (Fade / Dissolve) dengan durasi custom — otomatis dinonaktifkan (fallback ke potongan langsung) kalau ada clip yang terlalu pendek untuk durasi transisi yang diminta.
- Daftar clip & pengaturan editnya tersimpan otomatis ke file JSON di sebelah video sumber — buka lagi videonya, daftar clip muncul kembali.

## Download Desktop App (tanpa install Python)

Setiap release punya build desktop siap pakai untuk Windows/macOS/Linux — tinggal download, extract, jalankan, tanpa perlu install Python atau `pip install` apa pun.

1. Buka halaman [Releases](../../releases), download file `VideoClipper-<os>.zip` sesuai OS kamu.
2. Extract zip-nya.
3. Jalankan `VideoClipper.exe` (Windows) atau `VideoClipper` (macOS/Linux) di dalam folder hasil extract.

Window desktop akan terbuka otomatis (tidak perlu buka browser manual).

- **Windows:** FFmpeg ikut dibundel di dalam build-nya — benar-benar tinggal jalankan tanpa instalasi apa pun.
- **macOS/Linux:** FFmpeg **belum** dibundel, harus terinstall terpisah (lihat langkah [FFmpeg](#1-ffmpeg) di bawah) — tanpa itu aplikasi tetap jalan tapi fitur render tidak berfungsi. Khusus Linux, kalau package `libwebkit2gtk`/PyGObject belum terpasang, window desktop otomatis fallback membuka aplikasi di browser default (server tetap jalan di background).

## Instalasi (dari source)

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

Alternatif: jalankan sebagai window desktop (pywebview) alih-alih buka browser manual:

```bash
pip install -r requirements.txt -r requirements-desktop.txt
python desktop.py
```

Ini membuka jendela native yang menjalankan server FastAPI di background pada port lokal acak — tidak perlu buka browser manual. Kalau backend GTK/QT/WebKit tidak tersedia di sistem (umum di sebagian distro Linux minimal), otomatis fallback membuka aplikasi di browser default.

## Cara Pakai Singkat

1. Klik **Buka Video**, navigasi folder di server lalu pilih file video (atau paste path lengkap dan tekan Enter).
2. Putar video, tekan `I` untuk set start dan `O` untuk set end pada posisi playhead saat ini, lalu **Add Clip**. Bisa juga ketik timestamp manual (`mm:ss` atau `hh:mm:ss`).
3. Klik **Edit** pada sebuah clip untuk atur crop/kecepatan/audio/teks/watermark/subtitle (opsional). Teks overlay bisa lebih dari satu layer (tombol **+ Tambah Teks**), masing-masing dengan posisi/ukuran/warna sendiri.
4. Klik **Render** per clip atau **Render All** untuk semua clip. Status akan ter-update otomatis.
5. Untuk menggabungkan beberapa clip: klik **Merge Mode**, centang clip yang ingin digabung (urutan mengikuti urutan di daftar — pakai tombol ↑/↓ untuk mengatur ulang), isi nama file, klik **Merge & Render**.
6. Hasil render ada di folder `clips/` di sebelah file video sumber.

## Build Desktop App Sendiri

**Windows** (satu file `.exe`, FFmpeg ikut dibundel):

```powershell
pip install -r requirements.txt -r requirements-desktop.txt
# taruh ffmpeg.exe & ffprobe.exe di vendor\ffmpeg\ (download dari ffmpeg.org atau gyan.dev)
pyinstaller build_windows.spec
# hasil: dist\VideoClipper.exe
```

**macOS/Linux** (folder executable, FFmpeg harus terinstall terpisah di sistem):

```bash
pip install -r requirements.txt -r requirements-desktop.txt
pyinstaller desktop.spec
# hasil: dist/VideoClipper/
```

Release resmi (zip untuk Windows/macOS/Linux) dibuild otomatis oleh GitHub Actions (`.github/workflows/release.yml`) setiap kali tag versi (`v*`) di-push, lalu diunggah ke halaman [Releases](../../releases). Workflow ini juga bisa dijalankan manual lewat tab **Actions → Build desktop app & release → Run workflow** (hasil build-nya jadi artifact, tanpa publish release, kalau dijalankan tanpa tag).

> ⚠️ Build Windows memakai FFmpeg static build dari [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (varian "essentials", lisensi GPL). Kalau exe hasil build ini didistribusikan ke orang lain, pastikan mematuhi ketentuan lisensi GPL FFmpeg (mis. sediakan source code / tautan ke source FFmpeg yang dipakai).

## Struktur Project

```
clipcreate/
├── app.py                    # Entry point FastAPI
├── desktop.py                 # Entry point desktop (pywebview + server di background thread)
├── build_windows.spec         # Config PyInstaller untuk build VideoClipper.exe (Windows, FFmpeg dibundel)
├── desktop.spec                # Config PyInstaller untuk build desktop macOS/Linux
├── clipper/
│   ├── ffmpeg.py               # Builder perintah FFmpeg (cut, crop, speed, text, audio, concat)
│   ├── jobs.py                  # Render queue & status (background, non-blocking)
│   ├── projects.py              # Load/save daftar clip ke JSON
│   └── thumbnails.py            # Generate & cache thumbnail sprite + waveform untuk timeline
├── static/
│   ├── index.html
│   ├── style.css               # Dark mode
│   └── app.js
├── .github/workflows/release.yml  # Build & release otomatis (Windows/macOS/Linux) saat tag v* di-push
├── requirements.txt
├── requirements-desktop.txt    # Dependency tambahan untuk desktop app (pywebview, pyinstaller)
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
- Transisi merge memakai filter `xfade` (video) + `acrossfade` (audio) berantai; durasi transisi otomatis di-clamp/dinonaktifkan kalau lebih panjang dari clip terpendek. Clip yang di-mute tetap diberi silent audio track saat merge supaya stream audio konsisten untuk crossfade.
- Watermark gambar pakai filter `overlay` (posisi grid 9 titik, skala relatif lebar video, opacity via `colorchannelmixer`). Subtitle burn-in pakai filter `subtitles` dengan timestamp `.srt` yang tetap merujuk ke timeline video sumber (bukan relatif ke clip), jadi subtitle yang didownload terpisah dari video asli otomatis sinkron.
- Project lama yang masih pakai format teks overlay lama (satu layer, field `text`) otomatis dimigrasikan ke format `texts` (multi-layer) saat dibuka di UI maupun saat di-render.
