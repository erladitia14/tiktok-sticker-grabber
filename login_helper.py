"""
TikTok Login & Session Exporter
Jalankan script ini di PC/laptop lokal sekali saja:
1. Browser akan terbuka secara visual (headful).
2. Login ke akun TikTok kamu secara manual (bisa lewat Google, QR, atau password).
3. Setelah berhasil masuk ke beranda / profil TikTok, tekan ENTER di terminal.
4. File 'auth.json' akan tersimpan otomatis dan bisa kamu bawa/upload ke server produksi!
"""

import sys
import os
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_PATH = os.path.join(BASE_DIR, "auth.json")
BRAVE_PATH = "C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe"

def login_and_save_session():
    print("==================================================")
    print("       TIKTOK LOGIN & SESSION EXPORTER            ")
    print("==================================================")
    
    launch_args = {
        "headless": False,
        "args": ["--disable-blink-features=AutomationControlled"]
    }
    if os.path.exists(BRAVE_PATH):
        launch_args["executable_path"] = BRAVE_PATH

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_args)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 850}
        )
        page = context.new_page()

        print("\n[1/3] Membuka halaman login TikTok...")
        page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded")

        print("\n[2/3] Silakan login di jendela browser yang terbuka.")
        print("      (Bebas mau pake QR code HP, akun Google, atau email/password)")
        input("\n>>> Setelah berhasil login dan masuk ke TikTok, TEKAN [ENTER] DI SINI... <<<")

        print("\n[3/3] Menyimpan session & cookies ke 'auth.json'...")
        context.storage_state(path=AUTH_PATH)
        print(f"BERHASIL! File session tersimpan di:\n-> {AUTH_PATH}")
        print("\nFile 'auth.json' ini bisa langsung dibaca oleh server produksi secara headless.")
        browser.close()

if __name__ == "__main__":
    login_and_save_session()
