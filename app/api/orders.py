from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.database import get_db
from app.models import Order, OrderStatus
from app.schemas import OrderCreate, OrderRead
from app.services.events import bus
from app.services.order_codes import generate_order_code
from app.services.qr import build_vietqr_url

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("", response_model=OrderRead, status_code=201)
async def create_order(payload: OrderCreate, db: AsyncSession = Depends(get_db)) -> Order:
    settings = get_settings()
    now = datetime.now(UTC)

    # Sinh order_code không trùng (rất hiếm trùng nhưng vẫn check)
    for _ in range(5):
        code = generate_order_code()
        existing = await db.execute(select(Order).where(Order.order_code == code))
        if existing.scalar_one_or_none() is None:
            break
    else:
        raise HTTPException(status_code=500, detail="Could not generate unique order_code")

    qr_url = build_vietqr_url(
        bank_bin=settings.bank_bin,
        account_number=settings.bank_account_number,
        account_name=settings.bank_account_name,
        amount=payload.amount,
        add_info=code,
    )

    order = Order(
        order_code=code,
        amount=payload.amount,
        description=payload.description,
        status=OrderStatus.PENDING.value,
        qr_url=qr_url,
        created_at=now,
        expires_at=now + timedelta(minutes=settings.order_expires_minutes),
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


@router.get("/{order_code}", response_model=OrderRead)
async def get_order(order_code: str, db: AsyncSession = Depends(get_db)) -> Order:
    order = await _get_order_or_404(db, order_code)
    await _expire_if_needed(db, order)
    return order


@router.post("/{order_code}/cancel", response_model=OrderRead)
async def cancel_order(order_code: str, db: AsyncSession = Depends(get_db)) -> Order:
    order = await _get_order_or_404(db, order_code)
    if order.status == OrderStatus.PAID.value:
        raise HTTPException(status_code=409, detail="Order already paid")
    order.status = OrderStatus.CANCELED.value
    await db.commit()
    await db.refresh(order)
    await bus.publish(order.order_code, {"event": "canceled", "status": order.status})
    return order


@router.get("/{order_code}/stream")
async def stream_order(order_code: str, request: Request, db: AsyncSession = Depends(get_db)):
    """SSE stream: phát event mỗi khi order đổi trạng thái.

    Client phía web bán hàng có thể subscribe để hiện 'Đã thanh toán' tức thời
    mà không cần poll.
    """
    order = await _get_order_or_404(db, order_code)
    queue = await bus.subscribe(order_code)

    async def event_gen():
        # Gửi snapshot hiện tại ngay khi connect
        yield {
            "event": "snapshot",
            "data": json.dumps(
                {
                    "order_code": order.order_code,
                    "status": order.status,
                    "amount": order.amount,
                    "paid_at": order.paid_at.isoformat() if order.paid_at else None,
                }
            ),
        }
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {"event": payload.get("event", "update"), "data": json.dumps(payload)}
                    if payload.get("status") in (
                        OrderStatus.PAID.value,
                        OrderStatus.CANCELED.value,
                        OrderStatus.EXPIRED.value,
                    ):
                        break
                except TimeoutError:
                    # Heartbeat để giữ connection sống qua proxy
                    yield {"event": "ping", "data": "{}"}
        finally:
            await bus.unsubscribe(order_code, queue)

    return EventSourceResponse(event_gen())


async def _get_order_or_404(db: AsyncSession, order_code: str) -> Order:
    result = await db.execute(select(Order).where(Order.order_code == order_code))
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


async def _expire_if_needed(db: AsyncSession, order: Order) -> None:
    if order.status == OrderStatus.PENDING.value and order.expires_at < datetime.now(UTC):
        order.status = OrderStatus.EXPIRED.value
        await db.commit()
        await db.refresh(order)
        await bus.publish(order.order_code, {"event": "expired", "status": order.status})
