# Video Clipper

Aplikasi lokal untuk memotong video (mis. hasil download YouTube) menjadi beberapa clip, dengan fitur edit dasar berbasis FFmpeg. Jalan sepenuhnya offline di komputer sendiri — tidak butuh internet sama sekali.

## Fitur

- Buka video lokal (browser file di server, atau paste path lengkap), player HTML5 dengan seek cepat (HTTP Range).
- Tandai start/end clip dari posisi playhead atau ketik timestamp manual, banyak clip per video.
- Timeline visual dengan thumbnail sprite (preview frame) dan waveform audio di background — memudahkan cari posisi potong presisi. Arahkan mouse ke timeline untuk preview frame (hover scrubbing). Thumbnail & waveform di-cache otomatis (regenerate hanya kalau file video berubah), keyboard shortcut `I`/`O`/`Space`/`←`/`→`.
- Edit per clip (opsional): crop 9:16 / 1:1 / 16:9 dengan anchor, kecepatan 0.5x–2x, volume/fade/mute audio, multi-layer teks overlay (posisi grid 9 titik), watermark gambar (PNG/JPG dengan opacity & skala), dan burn-in subtitle dari file `.srt`.
- Render clip satu-satu atau semua sekaligus, lewat render queue di background (tidak blocking), status `queued → processing → done/error`.
- Mode potong cepat (`-c copy`) otomatis dipakai jika clip tanpa edit apa pun, mode akurat (re-encode) otomatis dipakai jika ada edit.
- Gabung (merge) beberapa clip terpilih menjadi satu file, resolusi/fps/audio otomatis disamakan sebelum digabung. Opsional pilih transisi antar clip (Fade / Dissolve) dengan durasi custom — otomatis dinonaktifkan (fallback ke potongan langsung) kalau ada clip yang terlalu pendek untuk durasi transisi yang diminta.
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
3. Klik **Edit** pada sebuah clip untuk atur crop/kecepatan/audio/teks/watermark/subtitle (opsional). Teks overlay bisa lebih dari satu layer (tombol **+ Tambah Teks**), masing-masing dengan posisi/ukuran/warna sendiri.
4. Klik **Render** per clip atau **Render All** untuk semua clip. Status akan ter-update otomatis.
5. Untuk menggabungkan beberapa clip: klik **Merge Mode**, centang clip yang ingin digabung (urutan mengikuti urutan di daftar — pakai tombol ↑/↓ untuk mengatur ulang), isi nama file, klik **Merge & Render**.
6. Hasil render ada di folder `clips/` di sebelah file video sumber.

## Desktop App (Windows)

Video Clipper juga bisa dijalankan sebagai aplikasi desktop (jendela native, bukan tab browser) lewat [pywebview](https://pywebview.flowrl.com/), dan di-build jadi satu file `.exe` portable dengan [PyInstaller](https://pyinstaller.org/) — FFmpeg ikut dibundel di dalam exe-nya, jadi tinggal jalankan tanpa instalasi apa pun.

### Cara build (tanpa perlu mesin Windows)

Repo ini sudah ada GitHub Actions workflow (`.github/workflows/build-windows.yml`) yang otomatis:
1. Download static build FFmpeg untuk Windows.
2. Build `VideoClipper.exe` pakai PyInstaller di runner `windows-latest`.
3. Upload hasilnya sebagai artifact (bisa didownload dari tab **Actions** di GitHub setelah run selesai).

Jalankan lewat tab **Actions → Build Windows Desktop App → Run workflow**, atau otomatis terpicu tiap push tag `v*`.

> ⚠️ Build ini memakai FFmpeg static build dari [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (varian "essentials", lisensi GPL). Kalau exe hasil build ini didistribusikan ke orang lain, pastikan mematuhi ketentuan lisensi GPL FFmpeg (mis. sediakan source code / tautan ke source FFmpeg yang dipakai).

### Build manual di mesin Windows sendiri

```powershell
pip install -r requirements.txt -r requirements-desktop.txt
# taruh ffmpeg.exe & ffprobe.exe di vendor\ffmpeg\ (download dari ffmpeg.org atau gyan.dev)
pyinstaller build_windows.spec
# hasil: dist\VideoClipper.exe
```

### Jalan langsung tanpa build (dev/testing, semua OS)

```bash
pip install -r requirements.txt -r requirements-desktop.txt
python desktop.py
```

Ini membuka jendela native yang menjalankan server FastAPI di background pada port lokal acak — tidak perlu buka browser manual. Catatan: logika server/threading sudah diverifikasi lewat automated test di sandbox Linux, tapi lapisan jendela native (WebView2) hanya bisa diverifikasi penuh di mesin Windows asli — jadi coba jalankan `dist\VideoClipper.exe` hasil build sendiri untuk memastikan sebelum didistribusikan.

## Struktur Project

```
clipcreate/
├── app.py              # Entry point FastAPI
├── desktop.py           # Entry point desktop (pywebview + server di background thread)
├── build_windows.spec   # Config PyInstaller untuk build VideoClipper.exe
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
├── requirements-desktop.txt  # Dependency tambahan untuk desktop app (pywebview, pyinstaller)
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
