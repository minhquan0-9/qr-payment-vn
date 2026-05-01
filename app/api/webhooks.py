from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import BankTransaction
from app.schemas import SMSPayload, SMSWebhookResult
from app.services.events import bus
from app.services.matcher import find_and_match_order
from app.services.parsers import get_parser

logger = logging.getLogger("payment.webhook")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _check_secret(provided: str | None) -> None:
    settings = get_settings()
    if not settings.webhook_secret:
        return
    if not provided or not hmac.compare_digest(provided, settings.webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


@router.post("/sms", response_model=SMSWebhookResult)
async def receive_sms(
    payload: SMSPayload,
    db: AsyncSession = Depends(get_db),
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> SMSWebhookResult:
    """Nhận SMS biến động số dư từ Android SMS forwarder.

    Cấu hình app forwarder gửi POST với header `X-Webhook-Secret: <WEBHOOK_SECRET>`
    và JSON body: {"message": "<nội dung SMS>", "sender": "<tên gửi>"}.
    """
    _check_secret(x_webhook_secret)
    settings = get_settings()

    bank_code = (payload.bank_code or settings.bank_code or "GENERIC").upper()
    parser = get_parser(bank_code)
    parsed = parser.parse(payload.message)

    if parsed is None or not parsed.is_incoming:
        return SMSWebhookResult(
            accepted=True,
            parsed=False,
            reason="Not an incoming-credit SMS",
        )

    # Dedupe
    dedupe_hash = hashlib.sha256(payload.message.strip().encode("utf-8")).hexdigest()
    existing_q = await db.execute(
        select(BankTransaction).where(BankTransaction.dedupe_hash == dedupe_hash)
    )
    existing = existing_q.scalar_one_or_none()
    if existing is not None:
        return SMSWebhookResult(
            accepted=True,
            parsed=True,
            amount=existing.amount,
            content=existing.content,
            matched_order_code=existing.matched_order_code,
            reason="duplicate",
        )

    tx = BankTransaction(
        bank_code=bank_code,
        amount=parsed.amount,
        content=parsed.content,
        raw_message=payload.message,
        dedupe_hash=dedupe_hash,
    )
    db.add(tx)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return SMSWebhookResult(
            accepted=True,
            parsed=True,
            amount=parsed.amount,
            content=parsed.content,
            reason="race-duplicate",
        )

    matched = await find_and_match_order(db, tx)
    await db.commit()

    if matched:
        await bus.publish(
            matched.order_code,
            {
                "event": "paid",
                "status": matched.status,
                "order_code": matched.order_code,
                "amount": matched.amount,
                "paid_at": matched.paid_at.isoformat() if matched.paid_at else None,
            },
        )
        logger.info("Matched order %s with tx %s", matched.order_code, tx.id)
        return SMSWebhookResult(
            accepted=True,
            parsed=True,
            matched_order_code=matched.order_code,
            amount=parsed.amount,
            content=parsed.content,
        )

    return SMSWebhookResult(
        accepted=True,
        parsed=True,
        amount=parsed.amount,
        content=parsed.content,
        reason="no-matching-order",
    )
