import time
import os
import sys
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_PATH = os.path.join(BASE_DIR, "auth.json")
BRAVE_PATH = "C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe"

def run_login():
    print("==================================================")
    print("      MEMBUKA BRAVE UNTUK LOGIN MASTER AKUN       ")
    print("==================================================")

    launch_opts = {
        "headless": False,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check"
        ]
    }
    if os.path.exists(BRAVE_PATH):
        launch_opts["executable_path"] = BRAVE_PATH

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_opts)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1200, "height": 800}
        )
        page = context.new_page()

        print("\n[+] Mengarahkan ke halaman login TikTok...")
        page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded")
        print("[+] Jendela Brave sudah terbuka di layar kamu.")
        print("[+] Silakan login (bisa scan QR via aplikasi TikTok di HP atau login biasa).")
        print("[+] Script ini otomatis memantau dan menyimpan sesi begitu kamu berhasil login...\n")

        # Poll cookies for login session (max 300 seconds / 5 minutes)
        start_time = time.time()
        logged_in = False

        while time.time() - start_time < 300:
            try:
                cookies = context.cookies()
                cookie_names = [c["name"] for c in cookies]

                # Check for TikTok session cookies
                if "sessionid" in cookie_names or "sid_guard" in cookie_names or "sessionid_ss" in cookie_names:
                    print("\n🎉 LOGIN BERHASIL TERDETEKSI!")
                    print(f"[+] Menemukan {len(cookies)} cookies aktif.")
                    print("[+] Menyimpan sesi ke 'auth.json'...")
                    context.storage_state(path=AUTH_PATH)
                    print(f"[+] Selesai! File tersimpan di: {AUTH_PATH}")
                    logged_in = True
                    break
            except Exception as e:
                pass

            time.sleep(2)

        if not logged_in:
            print("\n[-] Waktu tunggu habis (5 menit). Belum terdeteksi login.")

        try:
            browser.close()
        except Exception:
            pass

if __name__ == "__main__":
    run_login()
