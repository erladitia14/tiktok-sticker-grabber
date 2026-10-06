@echo off
title TikTok Sticker Grabber (Headless Server)
echo ========================================================
echo     TikTok Sticker Grabber - Headless Production Engine
echo ========================================================
echo.
cd /d "%~dp0"

echo [1/2] Memeriksa dependensi Python...
python -c "import fastapi, uvicorn, playwright" 2>nul
if %errorlevel% neq 0 (
    echo Menginstall paket yang dibutuhkan...
    pip install -r web_app\requirements.txt
    playwright install chromium
)

echo [2/2] Menjalankan server lokal (Headless mode)...
echo.
echo Server aktif di: http://127.0.0.1:5000
echo HP di WiFi yang sama bisa buka via IP laptop: http://[IP-KAMU]:5000
echo Tekan CTRL+C untuk mematikan server.
echo.
start http://127.0.0.1:5000
python -m uvicorn web_app.app:app --host 0.0.0.0 --port 5000
pause
