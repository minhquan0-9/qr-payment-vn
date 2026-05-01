"""Test ACBClient adapter (mock thư viện makky-acb-api)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.services.banking.acb_client import ACBClient


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


@pytest.mark.asyncio
async def test_acb_filters_outgoing_and_dedupes_by_tx_no():
    now = datetime.now()
    fake_inner = MagicMock()
    fake_inner.get_balances.return_value = {
        "balances": [{"accountNumber": "19527581"}]
    }
    fake_inner.get_transactions.return_value = [
        # incoming, in window
        {
            "amount": 25000,
            "transactionNumber": 1001,
            "description": "ABC123 thanh toan",
            "postingDate": _ms(now - timedelta(seconds=5)),
        },
        # outgoing (negative amount) → bỏ
        {
            "amount": -50000,
            "transactionNumber": 1002,
            "description": "rut tien",
            "postingDate": _ms(now - timedelta(seconds=10)),
        },
        # incoming nhưng ngoài window → bỏ
        {
            "amount": 99000,
            "transactionNumber": 1003,
            "description": "OLD",
            "postingDate": _ms(now - timedelta(hours=2)),
        },
        # missing transactionNumber → bỏ
        {"amount": 10000, "description": "no_id", "postingDate": _ms(now)},
    ]

    with patch("acb_api.ACBClient", return_value=fake_inner):
        client = ACBClient(username="u", password="p")
        client._client = fake_inner  # ensure use of mock

        since = now - timedelta(minutes=1)
        until = now + timedelta(minutes=1)
        txs = list(await client.fetch_incoming_transactions(since=since, until=until))

    assert len(txs) == 1
    assert txs[0].external_ref == "acb:1001"
    assert txs[0].amount == 25000
    assert txs[0].content == "ABC123 thanh toan"
    assert txs[0].bank_code == "ACB"


@pytest.mark.asyncio
async def test_acb_uses_configured_account_no_skips_balance_call():
    fake_inner = MagicMock()
    fake_inner.get_transactions.return_value = []

    with patch("acb_api.ACBClient", return_value=fake_inner):
        client = ACBClient(username="u", password="p", account_no="19527581")
        client._client = fake_inner

        await client.fetch_incoming_transactions(
            since=datetime.now() - timedelta(minutes=1),
            until=datetime.now(),
        )

    fake_inner.get_balances.assert_not_called()
    fake_inner.get_transactions.assert_called_once_with(50, "19527581")


@pytest.mark.asyncio
async def test_acb_close_closes_session():
    fake_inner = MagicMock()
    with patch("acb_api.ACBClient", return_value=fake_inner):
        client = ACBClient(username="u", password="p")
        client._client = fake_inner
        await client.aclose()
    fake_inner.session.close.assert_called_once()


def test_acb_requires_credentials():
    with patch("acb_api.ACBClient", return_value=MagicMock()):
        with pytest.raises(ValueError):
            ACBClient(username="", password="")


@pytest.mark.asyncio
async def test_acb_verify_login_raises_on_auth_failure():
    fake_inner = MagicMock()
    fake_inner.get_balances.side_effect = RuntimeError("auth failed")
    with patch("acb_api.ACBClient", return_value=fake_inner):
        client = ACBClient(username="u", password="p")
        client._client = fake_inner
        with pytest.raises(RuntimeError, match="auth failed"):
            await client.verify_login()


@pytest.mark.asyncio
async def test_acb_verify_login_returns_accounts():
    fake_inner = MagicMock()
    fake_inner.get_balances.return_value = {
        "balances": [{"accountNumber": "19527581"}, {"accountNumber": "19527582"}]
    }
    with patch("acb_api.ACBClient", return_value=fake_inner):
        client = ACBClient(username="u", password="p")
        client._client = fake_inner
        info = await client.verify_login()
    assert info == {"ok": True, "accounts": ["19527581", "19527582"]}
