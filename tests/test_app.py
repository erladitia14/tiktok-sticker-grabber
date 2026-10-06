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

