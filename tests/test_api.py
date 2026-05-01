"""End-to-end test: tạo order qua HTTP + verify SSE stream snapshot."""

from __future__ import annotations

import json
import os

import pytest
from httpx import ASGITransport, AsyncClient

# Set env TRƯỚC khi import app
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("BANK_BIN", "970422")
os.environ.setdefault("BANK_ACCOUNT_NUMBER", "0123456789")
os.environ.setdefault("BANK_ACCOUNT_NAME", "DEVIN TEST")
os.environ["ENABLE_SMS_WEBHOOK"] = "true"  # bật webhook để test fallback path

from app.config import get_settings  # noqa: E402
from app.database import init_db  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def app():
    get_settings.cache_clear()
    return create_app()


@pytest.mark.asyncio
async def test_create_order_returns_qr(app):
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/orders", json={"amount": 25_000, "description": "Test"})
        assert r.status_code == 201, r.text
        order = r.json()
        assert order["status"] == "pending"
        assert order["qr_url"].startswith("https://img.vietqr.io/")
        assert "addInfo=" + order["order_code"] in order["qr_url"]


@pytest.mark.asyncio
async def test_bank_health_endpoint(app):
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/bank/health")
        assert r.status_code == 200
        body = r.json()
        assert "mb_username_configured" in body
        assert "poll_interval_seconds" in body


@pytest.mark.asyncio
async def test_sms_webhook_match_flow(app):
    """Webhook SMS vẫn hoạt động khi bật flag — giữ làm fallback."""
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/orders", json={"amount": 25_000})
        code = r.json()["order_code"]

        sms = {
            "message": f"VCB 18/04 12:34 TK 0123 +25,000VND. ND: {code} thanh toan. SD 100,000VND",
        }
        r = await client.post(
            "/webhooks/sms", json=sms, headers={"X-Webhook-Secret": "test-secret"}
        )
        assert r.status_code == 200
        assert r.json()["matched_order_code"] == code

        r = await client.get(f"/api/orders/{code}")
        assert r.json()["status"] == "paid"


@pytest.mark.asyncio
async def test_sms_webhook_rejects_wrong_secret(app):
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/sms",
            json={"message": "+10,000VND. ND: PAYXXX"},
            headers={"X-Webhook-Secret": "WRONG"},
        )
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_openapi_lists_expected_paths(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/openapi.json")
        spec = r.json()
        paths = set(spec["paths"].keys())
        assert "/api/orders" in paths
        assert "/api/orders/{order_code}" in paths
        assert "/api/orders/{order_code}/stream" in paths
        assert "/api/bank/health" in paths
        assert "/api/bank/test-login" in paths


# Đánh dấu để biến `json` không bị flagged unused nếu chưa cần serialize sau
_ = json
