"""Debug endpoints để kiểm tra credentials NH và xem 5 phút giao dịch gần nhất."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.services.banking import build_client_from_settings

logger = logging.getLogger("payment.api.bank")

router = APIRouter(prefix="/api/bank", tags=["bank-debug"])


@router.get("/health")
async def bank_health() -> dict:
    """Trạng thái config NH (không gọi NH thật)."""
    s = get_settings()
    return {
        "bank_type": s.bank_type,
        "poll_interval_seconds": s.poll_interval_seconds,
        "poll_lookback_minutes": s.poll_lookback_minutes,
        "mb": {
            "username_configured": bool(s.mb_username),
            "password_configured": bool(s.mb_password),
            "account_no": s.mb_account_no or "(auto-discover)",
        },
        "acb": {
            "username_configured": bool(s.acb_username),
            "password_configured": bool(s.acb_password),
            "account_no": s.acb_account_no or "(auto-discover)",
        },
        "tpb": {
            "username_configured": bool(s.tpb_username),
            "password_configured": bool(s.tpb_password),
            "device_id_configured": bool(s.tpb_device_id),
            "account_id": s.tpb_account_id or "(missing)",
        },
    }


@router.post("/test-login")
async def test_login(bank_type: str | None = None) -> dict:
    """Thử đăng nhập + lấy 30p giao dịch gần nhất.

    Query param ``bank_type`` (mb/acb/tpb) để chọn NH cần test. Nếu không truyền,
    dùng giá trị ``BANK_TYPE`` trong settings.

    Endpoint này KHÔNG nên expose ra public.
    """
    s = get_settings()
    try:
        client = build_client_from_settings(s, bank_type=bank_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        # Bước 1: verify login — raise nếu credentials sai
        login_info = await client.verify_login()
        # Bước 2: lấy 30p giao dịch gần nhất để xem
        now = datetime.now(UTC).replace(tzinfo=None)
        since = now - timedelta(minutes=30)
        txs = list(await client.fetch_incoming_transactions(since=since, until=now))
        return {
            "ok": True,
            "bank_code": client.bank_code,
            "accounts": login_info.get("accounts", []),
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
        logger.exception("test_login failed for bank=%s", bank_type or s.bank_type)
        raise HTTPException(status_code=502, detail=f"Login/fetch failed: {exc}") from exc
    finally:
        await client.aclose()
