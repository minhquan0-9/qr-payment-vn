"""Test TPBankClient adapter (mock httpx)."""
from __future__ import annotations

from datetime import datetime, timedelta

import httpx
import pytest

from app.services.banking.tpbank_client import (
    TPBankAuthError,
    TPBankClient,
    _parse_tpb_datetime,
    _to_int_amount,
)


def _make_client() -> TPBankClient:
    return TPBankClient(
        username="u", password="p", device_id="DEV-XYZ", account_id="0123456789"
    )


def test_to_int_amount_handles_strings_and_commas():
    assert _to_int_amount("25,000") == 25000
    assert _to_int_amount(25000.0) == 25000
    assert _to_int_amount(None) == 0
    assert _to_int_amount("abc") == 0


def test_parse_tpb_datetime_formats():
    assert _parse_tpb_datetime("20250318") == datetime(2025, 3, 18)
    assert _parse_tpb_datetime("18/03/2025 14:30:00") == datetime(2025, 3, 18, 14, 30)
    assert _parse_tpb_datetime("2025-03-18T14:30:00") == datetime(2025, 3, 18, 14, 30)
    assert _parse_tpb_datetime(None) is None
    assert _parse_tpb_datetime("garbage") is None


def test_tpbank_requires_device_id():
    with pytest.raises(ValueError, match="TPB_DEVICE_ID"):
        TPBankClient(username="u", password="p", device_id="", account_id="0123")


def test_tpbank_requires_account_id():
    with pytest.raises(ValueError, match="TPB_ACCOUNT_ID"):
        TPBankClient(username="u", password="p", device_id="DEV", account_id="")


@pytest.mark.asyncio
async def test_tpbank_login_then_fetch_filters_credits():
    now = datetime.now()
    in_window = now - timedelta(minutes=5)
    out_of_window = now - timedelta(days=2)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/non-trust"):
            assert request.headers["DEVICE_ID"] == "DEV-XYZ"
            return httpx.Response(
                200, json={"access_token": "TOK-123", "expires_in": 900}
            )
        if request.url.path.endswith("/find"):
            assert request.headers["Authorization"] == "Bearer TOK-123"
            return httpx.Response(
                200,
                json={
                    "transactionInfos": [
                        {
                            "creditAmount": "30000",
                            "transactionId": "TXN-A",
                            "description": "ORD12345 thanh toan",
                            "transactionDate": in_window.strftime("%Y%m%d %H:%M:%S"),
                        },
                        # debit only → bỏ
                        {
                            "creditAmount": 0,
                            "debitAmount": 50000,
                            "transactionId": "TXN-B",
                            "description": "rut tien",
                            "transactionDate": in_window.strftime("%Y%m%d %H:%M:%S"),
                        },
                        # quá xa → bỏ
                        {
                            "creditAmount": 99000,
                            "transactionId": "TXN-C",
                            "description": "OLD",
                            "transactionDate": out_of_window.strftime("%Y%m%d %H:%M:%S"),
                        },
                    ]
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = _make_client()
    client._http = httpx.AsyncClient(transport=transport)

    since = now - timedelta(minutes=30)
    until = now + timedelta(minutes=1)
    txs = list(await client.fetch_incoming_transactions(since=since, until=until))

    assert len(txs) == 1
    assert txs[0].external_ref == "tpb:TXN-A"
    assert txs[0].amount == 30000
    assert txs[0].content == "ORD12345 thanh toan"
    assert txs[0].bank_code == "TPB"

    await client.aclose()


@pytest.mark.asyncio
async def test_tpbank_verify_login_returns_account():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/non-trust"):
            return httpx.Response(
                200, json={"access_token": "TOK-1", "expires_in": 900}
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = _make_client()
    client._http = httpx.AsyncClient(transport=transport)

    info = await client.verify_login()
    assert info == {"ok": True, "accounts": ["0123456789"]}

    await client.aclose()


@pytest.mark.asyncio
async def test_tpbank_login_failure_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad creds")

    transport = httpx.MockTransport(handler)
    client = _make_client()
    client._http = httpx.AsyncClient(transport=transport)

    with pytest.raises(TPBankAuthError):
        await client.fetch_incoming_transactions(
            since=datetime.now() - timedelta(minutes=1),
            until=datetime.now(),
        )

    await client.aclose()


@pytest.mark.asyncio
async def test_tpbank_retries_on_401():
    """Khi token expired (401), client phải re-login và retry 1 lần."""
    now = datetime.now()
    state = {"login_calls": 0, "tx_calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/non-trust"):
            state["login_calls"] += 1
            return httpx.Response(
                200, json={"access_token": f"TOK-{state['login_calls']}", "expires_in": 900}
            )
        if request.url.path.endswith("/find"):
            state["tx_calls"] += 1
            if state["tx_calls"] == 1:
                return httpx.Response(401, text="expired")
            return httpx.Response(200, json={"transactionInfos": []})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = _make_client()
    client._http = httpx.AsyncClient(transport=transport)

    txs = list(
        await client.fetch_incoming_transactions(
            since=now - timedelta(minutes=1), until=now
        )
    )
    assert txs == []
    assert state["login_calls"] == 2
    assert state["tx_calls"] == 2

    await client.aclose()
