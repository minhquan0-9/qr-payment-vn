"""End-to-end test: tạo order -> bắn webhook SMS -> order chuyển sang paid."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

# Force SQLite in-memory test DB. Phải set TRƯỚC khi import app.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("BANK_BIN", "970422")
os.environ.setdefault("BANK_ACCOUNT_NUMBER", "0123456789")
os.environ.setdefault("BANK_ACCOUNT_NAME", "DEVIN TEST")

from app.config import get_settings
from app.database import init_db
from app.main import create_app


@pytest.fixture
def app():
    get_settings.cache_clear()
    return create_app()


@pytest.mark.asyncio
async def test_create_order_then_match_via_sms(app):
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Tạo đơn
        r = await client.post("/api/orders", json={"amount": 25_000, "description": "Test"})
        assert r.status_code == 201, r.text
        order = r.json()
        code = order["order_code"]
        assert order["status"] == "pending"
        assert order["qr_url"].startswith("https://img.vietqr.io/")

        # 2. Bắn webhook SMS với nội dung chứa đúng order_code
        sms = {
            "message": f"VCB 18/04 12:34 TK 0123 +25,000VND. SD: 100,000 VND. ND: {code} thanh toan",
            "sender": "Vietcombank",
        }
        r = await client.post(
            "/webhooks/sms", json=sms, headers={"X-Webhook-Secret": "test-secret"}
        )
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["parsed"] is True
        assert result["matched_order_code"] == code

        # 3. Kiểm tra order đã chuyển sang paid
        r = await client.get(f"/api/orders/{code}")
        assert r.status_code == 200
        o = r.json()
        assert o["status"] == "paid"
        assert o["paid_at"] is not None


@pytest.mark.asyncio
async def test_webhook_rejects_wrong_secret(app):
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
async def test_webhook_idempotent(app):
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/orders", json={"amount": 10_000})
        code = r.json()["order_code"]
        sms = {"message": f"+10,000VND. ND: {code}"}
        h = {"X-Webhook-Secret": "test-secret"}

        r1 = await client.post("/webhooks/sms", json=sms, headers=h)
        r2 = await client.post("/webhooks/sms", json=sms, headers=h)

        assert r1.status_code == 200
        assert r2.status_code == 200
        # Lần 2 phải báo duplicate, nhưng order_code đã match từ lần 1
        assert r2.json()["reason"] == "duplicate"


@pytest.mark.asyncio
async def test_unmatched_sms_does_not_crash(app):
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/sms",
            json={"message": "+5,000VND. ND: NOSUCHCODE random"},
            headers={"X-Webhook-Secret": "test-secret"},
        )
        assert r.status_code == 200
        assert r.json()["reason"] == "no-matching-order"
