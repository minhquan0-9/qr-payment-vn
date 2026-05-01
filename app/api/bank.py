"""Debug endpoints để kiểm tra credentials MB Bank và xem balance."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.services.banking import MBBankClient

logger = logging.getLogger("payment.api.bank")

router = APIRouter(prefix="/api/bank", tags=["bank-debug"])


@router.get("/health")
async def bank_health() -> dict:
    """Kiểm tra config có MB credentials hay chưa (không gọi MB)."""
    s = get_settings()
    return {
        "mb_username_configured": bool(s.mb_username),
        "mb_password_configured": bool(s.mb_password),
        "mb_account_no": s.mb_account_no or "(auto-discover)",
        "poll_interval_seconds": s.poll_interval_seconds,
        "poll_lookback_minutes": s.poll_lookback_minutes,
    }


@router.post("/test-login")
async def test_login() -> dict:
    """Thử đăng nhập + lấy balance + lấy 5p giao dịch gần nhất.

    Endpoint này KHÔNG nên expose ra public. Dùng để verify credentials
    và parser khi setup ban đầu. Sau setup nên xoá hoặc bảo vệ bằng auth.
    """
    s = get_settings()
    if not s.mb_username or not s.mb_password:
        raise HTTPException(status_code=400, detail="MB credentials not configured")

    client = MBBankClient(
        username=s.mb_username, password=s.mb_password, account_no=s.mb_account_no
    )
    try:
        accounts = await client._accounts_to_query()  # noqa: SLF001
        now = datetime.now(UTC).replace(tzinfo=None)
        since = now - timedelta(minutes=5)
        txs = list(await client.fetch_incoming_transactions(since=since, until=now))
        return {
            "ok": True,
            "accounts": accounts,
            "recent_incoming_count": len(txs),
            "recent": [
                {
                    "external_ref": t.external_ref,
                    "amount": t.amount,
                    "content": t.content[:200],
                    "posted_at": t.posted_at.isoformat(),
                }
                for t in txs[:10]
            ],
        }
    except Exception as exc:
        logger.exception("test_login failed")
        raise HTTPException(status_code=502, detail=f"MB login/fetch failed: {exc}") from exc
    finally:
        await client.aclose()
