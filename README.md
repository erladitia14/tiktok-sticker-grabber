# TikTok Sticker & Media Grabber (Production Ready)

Aplikasi web & API berkecepatan tinggi untuk mengekstrak dan mengunduh stiker, GIF balasan, serta reaksi gambar dari komentar TikTok secara **100% Headless** dan **Mobile-Friendly**.

---

## ✨ Fitur Unggulan

1. **100% Headless Engine (FastAPI + Playwright Singleton)**:
   - Browser Chromium berjalan satu kali saat server start (`lifespan`).
   - Setiap request hanya membuka konteks ringan (`BrowserContext`), sangat hemat CPU & RAM (~150MB) sehingga kuat di VPS 1GB/2GB.
   - Dilengkapi `asyncio.Semaphore` untuk mencegah server overload saat banyak user akses bersamaan.
2. **Support Login Sesi TikTok (`auth.json`)**:
   - Menghindari slider puzzle / CAPTCHA TikTok secara otomatis.
   - Sesi login bisa dibuat via `login_helper.py` di laptop atau diimpor langsung berupa JSON cookies lewat Web UI.
3. **Mobile-First Experience**:
   - Tampilan responsif Stripe/Linear dark theme di layar HP (360px - 480px).
   - Tombol satu-ketukan **"📋 Tempel"** dari clipboard.
   - **Floating Download Bar**: Tombol unduh ZIP melayang di bagian bawah layar HP agar tidak perlu repot scroll ke atas.
   - Simpan langsung format `.webp` / `.gif` atau bundel semua dalam `.zip`.
4. **Production Docker Ready**:
   - Disediakan `Dockerfile` resmi berbasis `mcr.microsoft.com/playwright/python` dan `docker-compose.yml`.

---

## 📂 Struktur Project

```
TikTok Sticker/
├── web_app/
│   ├── app.py              # Backend FastAPI (Headless Playwright Singleton)
│   ├── requirements.txt    # Dependensi produksi (FastAPI, Uvicorn, Playwright, HTTPX)
│   ├── templates/          # index.html (Responsive mobile-friendly)
│   └── static/             # style.css & app.js (Linear dark UI & clipboard helper)
├── extension/              # Browser extension alternatif (Chrome / Brave / Edge)
├── login_helper.py         # Skrip interaktif 1-kali untuk login TikTok & dump auth.json
├── Dockerfile              # Container image siap hosting
├── docker-compose.yml      # 1-klik deploy di VPS / Cloud
├── start.bat               # Runner lokal Windows
├── tests/                  # Pytest unit & integration tests
└── README.md
```

---

## 📱 Cara Login Akun TikTok (Agar Bebas CAPTCHA)

Pilih salah satu cara yang paling mudah:

### Cara A: Pakai Skrip Lokal (Rekomendasi)
1. Jalankan skrip ini di terminal laptop:
   ```bash
   python login_helper.py
   ```
2. Jendela browser akan terbuka. Login ke akun TikTok (bebas pakai QR code HP, Google, atau username/password).
3. Setelah masuk, tekan `ENTER` di terminal.
4. File `auth.json` otomatis terbuat dan langsung dibaca oleh server.

### Cara B: Lewat Web UI (Bisa dari HP / Browser Mana Saja)
1. Buka dashboard web app.
2. Klik tombol status sesi di kanan atas (ikon ⚙️).
3. Paste JSON cookies (bisa diekspor pakai extension seperti *Cookie-Editor* di browser).
4. Klik **Simpan Cookies ke Server**.

---

## 🚀 Menjalankan di Lokal (Development / Tes HP via WiFi)

1. Jalankan:
   ```cmd
   .\start.bat
   ```
2. Buka di laptop: `http://127.0.0.1:5000`
3. Buka di HP (pastikan satu jaringan WiFi): `http://[IP-LAPTOP]:5000` (contoh: `http://192.168.1.10:5000`)

---

## 🌐 Panduan Deploy ke VPS / Cloud (Production)

### Menggunakan Docker Compose (Paling Simpel)
Di server VPS Ubuntu/Debian kamu:
```bash
# 1. Masuk ke direktori
cd "TikTok Sticker"

# 2. (Opsional) Salin auth.json jika sudah login di lokal
# scp auth.json user@ip-vps:/path/to/TikTok\ Sticker/

# 3. Jalankan container
docker compose up -d --build
```
Aplikasi langsung live di port `8000`. Tinggal arahkan reverse proxy (Nginx / Caddy / Cloudflare Tunnel) dengan SSL ke `http://127.0.0.1:8000`.

---

## 🧪 Testing

Jalankan pengujian sistem:
```bash
pytest
```
Semua endpoint validasi, lifecyle headless browser, dan template parsing telah lolos pengujian.
