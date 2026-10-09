import os
import sys
from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx
import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from web_app.app import app

@pytest.fixture
def client():
    @asynccontextmanager
    async def test_lifespan(_app):
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = test_lifespan
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.router.lifespan_context = original_lifespan


def test_index_route(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "TikTok Sticker" in res.text

def test_api_auth_status(client):
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    data = res.json()
    assert "authenticated" in data
    assert "status" in data

def test_api_extract_validation(client):
    res = client.post("/api/extract", json={"url": ""})
    assert res.status_code == 400
    assert "detail" in res.json()

def test_api_zip_validation(client):
    res = client.post("/api/download-zip", json={"items": []})
    assert res.status_code == 400
    assert "detail" in res.json()

class FakeAsyncClient:
    def __init__(self, response, **kwargs):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, **kwargs):
        return self.response

def test_proxy_rejects_non_media_upstream_response(client):
    upstream = httpx.Response(403, content=b"blocked", headers={"content-type": "text/html"})
    with patch("web_app.app.httpx.AsyncClient", lambda **kwargs: FakeAsyncClient(upstream)):
        res = client.get("/api/proxy-img", params={"url": "https://example.tiktokcdn.com/sticker.webp"})

    assert res.status_code == 502
    assert "CDN gagal" in res.json()["detail"]


def test_zip_all_failed_reports_error(client):
    upstream = httpx.Response(403, content=b"blocked", headers={"content-type": "text/html"})
    payload = {"items": [{"url": "https://example.tiktokcdn.com/sticker.webp"}]}
    with patch("web_app.app.httpx.AsyncClient", lambda **kwargs: FakeAsyncClient(upstream)):
        res = client.post("/api/download-zip", json=payload)

    assert res.status_code == 502
    assert "Semua file gagal" in res.json()["detail"]

def test_zip_partial_success_reports_counts(client):
    responses = iter([
        httpx.Response(200, content=b"image-bytes", headers={"content-type": "image/webp"}),
        httpx.Response(403, content=b"blocked", headers={"content-type": "text/html"}),
    ])

    class SequenceAsyncClient(FakeAsyncClient):
        async def get(self, url, **kwargs):
            return next(responses)

    payload = {"items": [
        {"url": "https://example.tiktokcdn.com/one.webp"},
        {"url": "https://example.tiktokcdn.com/two.webp"},
    ]}
    with patch("web_app.app.httpx.AsyncClient", lambda **kwargs: SequenceAsyncClient(None)):
        res = client.post("/api/download-zip", json=payload)

    assert res.status_code == 200
    assert res.headers["x-download-succeeded"] == "1"
    assert res.headers["x-download-failed"] == "1"


def test_video_sticker_invalid_url(client):
    res = client.post("/api/video-sticker", json={"url": "https://example.com/not-tiktok"})
    assert res.status_code == 400
    assert "valid" in res.json()["detail"].lower()

def test_video_sticker_conversion_logic():
    import tempfile, subprocess
    from web_app.app import convert_video_file_to_sticker

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        vpath = f.name
    f.close()

    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
            vpath
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        sticker_data = convert_video_file_to_sticker(vpath, max_duration=1.0, fps=10)
        assert isinstance(sticker_data, bytes)
        assert len(sticker_data) > 0
        # WhatsApp sticker size limit is 500 KB
        assert len(sticker_data) < 500 * 1024
        # WebP header signature RIFF....WEBP
        assert sticker_data[:4] == b"RIFF"
        assert sticker_data[8:12] == b"WEBP"
    finally:
        if os.path.exists(vpath):
            os.remove(vpath)

def test_video_sticker_endpoint_flow(client):
    with patch("web_app.app.convert_video_file_to_sticker", return_value=b"RIFF\x00\x00\x00\x00WEBPtest"):
        class ResolverClient(FakeAsyncClient):
            async def get(self, url, **kwargs):
                if "tikwm.com" in url:
                    return httpx.Response(200, json={"code": 0, "data": {"play": "https://example.tiktokcdn.com/test.mp4", "title": "funny"}})
                return httpx.Response(200, content=b"fake-video-content-" * 100, headers={"content-type": "video/mp4"})

        with patch("web_app.app.httpx.AsyncClient", lambda **kwargs: ResolverClient(None)):
            res = client.post("/api/video-sticker", json={"url": "https://www.tiktok.com/@user/video/1234567890"})

        assert res.status_code == 200
        assert res.headers["content-type"] == "image/webp"
        assert "attachment" in res.headers["content-disposition"]
        assert res.headers["x-whatsapp-compliant"] == "true"
