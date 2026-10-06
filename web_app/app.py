import os
import io
import re
import time
import json
import zipfile
import asyncio
from typing import Optional, List
from urllib.parse import urljoin, urlsplit
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from playwright.async_api import async_playwright, Browser, BrowserContext

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
AUTH_FILE_ENV = os.getenv("AUTH_FILE", "")
AUTH_FILE = AUTH_FILE_ENV if AUTH_FILE_ENV else os.path.join(PROJECT_ROOT, "auth.json")
MAX_CONCURRENT_SCRAPES = int(os.getenv("MAX_CONCURRENT", "3"))

semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCRAPES)
browser_instance: Optional[Browser] = None
playwright_instance = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global browser_instance, playwright_instance
    print("[Lifecycle] Starting Playwright Headless Browser Singleton...")
    playwright_instance = await async_playwright().start()

    # Search for Brave/Chrome if on Windows, else default chromium
    brave_path = "C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe"
    # Launch with modern --headless=new
    launch_args = {
        "headless": False,
        "args": [
            "--headless=new",
            "--mute-audio",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1280,850"
        ]
    }
    if os.name == "nt" and os.path.exists(brave_path):
        launch_args["executable_path"] = brave_path

    browser_instance = await playwright_instance.chromium.launch(**launch_args)
    print("[Lifecycle] Browser Singleton Ready!")
    yield
    print("[Lifecycle] Shutting down browser...")
    if browser_instance:
        await browser_instance.close()
    if playwright_instance:
        await playwright_instance.stop()
    print("[Lifecycle] Browser stopped.")

app = FastAPI(title="TikTok Sticker Grabber API", lifespan=lifespan)

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

def extract_sticker_urls(sticker_struct) -> list:
    if not isinstance(sticker_struct, dict):
        return []
    for key in ["animated_url", "static_url"]:
        val = sticker_struct.get(key)
        if isinstance(val, dict):
            for subkey in ["high_resolution_url", "mid_resolution_url", "low_resolution_url"]:
                sub = val.get(subkey)
                if isinstance(sub, dict) and sub.get("url_list"):
                    return [sub["url_list"][0]]
            if val.get("url_list"):
                return [val["url_list"][0]]
    return []

def extract_image_urls(img_obj) -> list:
    if not isinstance(img_obj, dict):
        return []
    for key in ["origin_url", "crop_url"]:
        sub = img_obj.get(key)
        if isinstance(sub, dict) and sub.get("url_list"):
            return [sub["url_list"][0]]
    return []

MEDIA_HOST_SUFFIXES = (
    "tiktokcdn.com",
    "tiktokcdn-us.com",
    "tiktokcdn-eu.com",
    "tiktokcdn-in.com",
    "byteimg.com",
    "ibytedtos.com",
    "ibyteimg.com",
    "byteoversea.com",
    "giphy.com",
    "tenor.com",
)

def is_allowed_media_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        return (
            parsed.scheme == "https"
            and not parsed.username
            and not parsed.password
            and any(host == suffix or host.endswith("." + suffix) for suffix in MEDIA_HOST_SUFFIXES)
        )
    except ValueError:
        return False

def is_media_response(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    return bool(response.content) and (
        content_type.startswith("image/")
        or content_type in {"application/octet-stream", "application/binary"}
        or not content_type
    )

async def fetch_media(client: httpx.AsyncClient, url: str, headers: Optional[dict] = None) -> httpx.Response:
    current_url = url
    for _ in range(6):
        if not is_allowed_media_url(current_url):
            raise HTTPException(status_code=502, detail="CDN mengarahkan ke domain yang tidak diizinkan.")
        response = await client.get(current_url, headers=headers)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("location")
        if not location:
            return response
        current_url = urljoin(current_url, location)
    raise HTTPException(status_code=502, detail="Terlalu banyak pengalihan saat mengambil media.")

class ExtractRequest(BaseModel):
    url: str
    scrolls: Optional[int] = 5

class DownloadZipItem(BaseModel):
    url: str
    user: Optional[str] = "user"
    id: Optional[str] = "item"
    ext: Optional[str] = "webp"

class DownloadZipRequest(BaseModel):
    items: List[DownloadZipItem]

class CookieImportRequest(BaseModel):
    cookies_json: str

def check_auth_exists() -> dict:
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                cookies = data.get("cookies", [])
                user_hint = "Terhubung"
                for c in cookies:
                    if "user" in c.get("name", "").lower() or c.get("name") == "sessionid":
                        user_hint = "Aktif (Logged In)"
                        break
                return {"authenticated": True, "cookies_count": len(cookies), "status": user_hint}
        except Exception:
            return {"authenticated": False, "status": "Error reading auth.json"}
    return {"authenticated": False, "status": "Mode Tamu (Guest)"}

@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    auth_info = check_auth_exists()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"auth": auth_info}
    )

@app.get("/api/auth/status")
async def get_auth_status():
    return check_auth_exists()

@app.post("/api/auth/import")
async def import_cookies(payload: CookieImportRequest):
    try:
        raw = payload.cookies_json.strip()
        parsed = json.loads(raw)
        
        # Format can be raw array of cookies or playwright storage_state dict
        if isinstance(parsed, list):
            state = {"cookies": parsed, "origins": []}
        elif isinstance(parsed, dict) and "cookies" in parsed:
            state = parsed
        else:
            raise ValueError("Format JSON tidak valid. Harus array cookies atau object storage_state.")

        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        return {"success": True, "message": f"Berhasil menyimpan {len(state.get('cookies', []))} cookies!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gagal mengimpor cookies: {str(e)}")

@app.delete("/api/auth/logout")
async def logout_auth():
    if os.path.exists(AUTH_FILE):
        os.remove(AUTH_FILE)
    return {"success": True, "message": "Session berhasil dihapus. Kembali ke mode tamu."}

@app.get("/api/proxy-img")
async def proxy_image(url: str):
    if not is_allowed_media_url(url):
        raise HTTPException(status_code=400, detail="URL media tidak valid atau domain tidak diizinkan.")

    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        "Referer": "https://www.tiktok.com/"
    }

    async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
        try:
            resp = await fetch_media(client, url, headers=headers)
            if resp.status_code != 200 or not is_media_response(resp):
                raise HTTPException(status_code=502, detail=f"CDN gagal mengirim gambar (HTTP {resp.status_code}).")
            content_type = resp.headers.get("content-type", "image/webp")
            return Response(content=resp.content, media_type=content_type)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch image: {e}")
@app.post("/api/extract")
async def extract_stickers(payload: ExtractRequest):
    url = payload.url.strip()
    try:
        parsed_url = urlsplit(url)
        hostname = (parsed_url.hostname or "").lower().rstrip(".")
    except ValueError:
        raise HTTPException(status_code=400, detail="Harap masukkan URL video TikTok yang valid.")
    if parsed_url.scheme not in {"http", "https"} or not (hostname == "tiktok.com" or hostname.endswith(".tiktok.com")):
        raise HTTPException(status_code=400, detail="Harap masukkan URL video TikTok yang valid.")

    scrolls = max(1, min(payload.scrolls or 5, 20))

    if not browser_instance:
        raise HTTPException(status_code=503, detail="Browser belum siap.")

    async with semaphore:
        context_opts = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "viewport": {"width": 1280, "height": 850}
        }

        if os.path.exists(AUTH_FILE):
            try:
                context_opts["storage_state"] = AUTH_FILE
                print(f"[Extractor] Memuat session login dari: {AUTH_FILE}")
            except Exception as e:
                print(f"[Extractor] Gagal memuat auth file: {e}")

        context: BrowserContext = await browser_instance.new_context(**context_opts)
        page = await context.new_page()
        total_comments_seen = 0

        captured_payloads = []
        async def on_response(resp):
            if "/api/comment/list/" in resp.url and resp.status == 200:
                try:
                    payload = await resp.json()
                    captured_payloads.append(payload)
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            print(f"[Extractor] Membuka URL: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=35000)
            await asyncio.sleep(1)

            # 1. Dismiss any overlay with Escape
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)

            # 2. Switch tab from 'You may like' to 'Comments'
            tab_locator = page.locator('button[data-testid="tux-web-tab-bar"]').filter(has_text=re.compile(r"comment|komentar", re.I))
            try:
                await tab_locator.first.wait_for(state="visible", timeout=20000)
                await tab_locator.first.click()
                print("[Extractor] Comments tab clicked.")
            except Exception as tab_err:
                print(f"[Extractor] Tux tab bar not found, trying fallback: {tab_err}")
                await page.evaluate('''() => {
                    const tabs = Array.from(document.querySelectorAll('button[data-testid="tux-web-tab-bar"], [class*="tabbar"] button, button'));
                    const commentTab = tabs.find(t => {
                        const txt = t.innerText.trim().toLowerCase();
                        return (txt === 'comments' || txt.startsWith('comment') || txt === 'komentar') && t.offsetWidth > 0;
                    });
                    if (commentTab) commentTab.click();
                }''')

            # Wait for first comments batch to land
            for _ in range(25):
                if captured_payloads:
                    break
                await asyncio.sleep(0.3)

            # 3. Auto-scroll comments container to fetch more batches
            for _ in range(scrolls):
                await page.evaluate('''() => {
                    const container = document.querySelector(
                        '[class*="DivCommentListContainer"], [class*="DivCommentContainer"], [data-e2e="search-comment-container"]'
                    );
                    if (container) {
                        container.scrollTop += 1200;
                    }
                }''')
                await asyncio.sleep(1.2)

            print(f"[Extractor] Intercepted payloads count: {len(captured_payloads)}")

            # 4. Extract stickers from rendered DOM as complement
            dom_stickers = await page.evaluate('''() => {
                const results = [];
                const seenUrls = new Set();

                function isAvatar(img) {
                    const parent = img.closest('[class*="Avatar"], [data-e2e*="avatar"], a[href^="/@"]');
                    if (parent && !img.closest('p, [class*="CommentText"], [class*="comment-text"]')) {
                        return true;
                    }
                    const w = img.naturalWidth || img.width || 0;
                    const h = img.naturalHeight || img.height || 0;
                    if (w > 0 && w <= 48 && h > 0 && h <= 48) {
                        if (img.className.toLowerCase().includes("avatar")) return true;
                    }
                    return false;
                }

                const commentNodes = document.querySelectorAll(
                    '[data-e2e="comment-item"], [class*="DivCommentItemContainer"], [class*="CommentItem"], [class*="DivCommentContentContainer"]'
                );

                commentNodes.forEach(node => {
                    if (node.closest('[class*="DivVideoList"], [class*="recommend"], [data-e2e*="recommend"]')) {
                        return;
                    }

                    const userEl = node.querySelector('[data-e2e*="comment-username"], a[href*="/@"] span, [class*="SpanUserName"]');
                    const user = userEl ? userEl.innerText.trim().replace(/^@/, '') : 'user';

                    const textEl = node.querySelector('p[data-e2e*="comment-level"], [class*="PCommentText"], p');
                    const text = textEl ? textEl.innerText.trim() : '';

                    const imgs = node.querySelectorAll('img');
                    imgs.forEach(img => {
                        const src = img.src;
                        if (!src || !src.startsWith('http') || isAvatar(img)) return;

                        const isMedia = src.includes('tiktokcdn') || src.includes('byteimg') || src.includes('giphy') || src.includes('tenor') || src.includes('tos-');
                        const cleanUrl = src.split('?')[0];

                        if (isMedia && !seenUrls.has(cleanUrl)) {
                            seenUrls.add(cleanUrl);
                            let ext = 'webp';
                            if (src.includes('.gif')) ext = 'gif';
                            else if (src.includes('.png')) ext = 'png';
                            else if (src.includes('.jpg') || src.includes('.jpeg')) ext = 'jpg';

                            results.push({
                                url: src,
                                cleanUrl: cleanUrl,
                                user: user,
                                text: text,
                                ext: ext
                            });
                        }
                    });
                });

                return results;
            }''')

            # Parse intercepted API payloads
            api_stickers = []
            seen_urls = set()

            for payload in captured_payloads:
                try:
                    comments = payload.get("comments", [])
                    print(f"[Extractor] Comments in payload: {len(comments)}")
                    for c in comments:
                        user = c.get("user", {}).get("unique_id", "user")
                        text = c.get("text", "")

                        # 1. TikTok official comment stickers
                        stk_urls = extract_sticker_urls(c.get("cmt_sticker_struct"))
                        for u in stk_urls:
                            clean_u = u.split("?")[0]
                            if clean_u not in seen_urls:
                                seen_urls.add(clean_u)
                                ext = "webp"
                                if ".gif" in u: ext = "gif"
                                elif ".png" in u: ext = "png"
                                api_stickers.append({
                                    "url": u,
                                    "cleanUrl": clean_u,
                                    "user": user,
                                    "text": text,
                                    "ext": ext,
                                    "type": "sticker"
                                })

                        # 2. Photo / GIF reply attachments
                        for img_obj in (c.get("image_list") or []):
                            img_urls = extract_image_urls(img_obj)
                            for u in img_urls:
                                clean_u = u.split("?")[0]
                                if clean_u not in seen_urls:
                                    seen_urls.add(clean_u)
                                    ext = "webp"
                                    if ".gif" in u: ext = "gif"
                                    elif ".png" in u: ext = "png"
                                    elif ".jpg" in u or ".jpeg" in u: ext = "jpg"
                                    api_stickers.append({
                                        "url": u,
                                        "cleanUrl": clean_u,
                                        "user": user,
                                        "text": text,
                                        "ext": ext,
                                        "type": "photo"
                                    })
                except Exception as ex:
                    print(f"[Extractor] Error parsing response: {ex}")

            # Merge API stickers + DOM stickers
            for ds in dom_stickers:
                if ds["cleanUrl"] not in seen_urls:
                    seen_urls.add(ds["cleanUrl"])
                    api_stickers.append(ds)

            for idx, s in enumerate(api_stickers):
                s["id"] = f"stk_{idx + 1}"

            total_comments_seen = sum(
                len(p.get("comments", []))
                for p in captured_payloads
                if isinstance(p, dict) and isinstance(p.get("comments", []), list)
            )
            print(f"[Extractor] Selesai: payloads={len(captured_payloads)}, comments={total_comments_seen}, DOM={len(dom_stickers)}, stickers={len(api_stickers)}")
            return {
                "success": True,
                "count": len(api_stickers),
                "stickers": api_stickers,
                "diagnostics": {
                    "comment_payloads": len(captured_payloads),
                    "comments_seen": total_comments_seen,
                    "dom_stickers": len(dom_stickers),
                }
            }

        except Exception as e:
            print(f"[Extractor] Error: {e}")
            raise HTTPException(status_code=500, detail=f"Gagal memproses video: {str(e)}")
        finally:
            await context.close()

@app.post("/api/download-zip")
async def create_download_zip(payload: DownloadZipRequest):
    items = payload.items
    if not items:
        raise HTTPException(status_code=400, detail="Daftar item kosong.")
    if any(not is_allowed_media_url(item.url) for item in items):
        raise HTTPException(status_code=400, detail="URL media tidak valid atau domain tidak diizinkan.")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.tiktok.com/"
    }

    zip_buffer = io.BytesIO()
    succeeded = 0
    failed = 0

    async with httpx.AsyncClient(headers=headers, follow_redirects=False, timeout=15.0) as client:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for idx, item in enumerate(items):
                user = re.sub(r"[^A-Za-z0-9_-]", "_", item.user or "user")[:64] or "user"
                ext = re.sub(r"[^A-Za-z0-9]", "", (item.ext or "webp").lower())[:8] or "webp"
                filename = f"sticker_{str(idx + 1).zfill(2)}_{user}.{ext}"

                try:
                    res = await fetch_media(client, item.url, headers=headers)
                    if res.status_code == 200 and is_media_response(res):
                        zip_file.writestr(filename, res.content)
                        succeeded += 1
                    else:
                        failed += 1
                        print(f"[ZIP] CDN rejected {item.url}: HTTP {res.status_code}, content-type={res.headers.get('content-type', 'unknown')}")
                except Exception as ex:
                    failed += 1
                    print(f"[ZIP] Gagal download {item.url}: {ex}")

    if succeeded == 0:
        raise HTTPException(status_code=502, detail="Semua file gagal diunduh dari CDN TikTok. Coba lagi atau gunakan tautan lain.")

    zip_buffer.seek(0)
    filename = f"tiktok_stickers_{int(time.time())}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Download-Succeeded": str(succeeded),
            "X-Download-Failed": str(failed),
        }
    )
