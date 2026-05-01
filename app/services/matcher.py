"""Khớp một biến động số dư (BankTransaction) với một Order pending.

Quy tắc match:
  1. Chuẩn hoá nội dung SMS: bỏ dấu tiếng Việt + uppercase + giữ A-Z 0-9.
  2. Tìm chuỗi order_code (đã uppercase) bên trong nội dung đã chuẩn hoá.
  3. Số tiền giao dịch >= số tiền order (cho phép chuyển dư, nhưng không cho thiếu).
  4. Order phải còn ở trạng thái pending và chưa hết hạn.

Trả về Order đã được mark paid, hoặc None nếu không khớp.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from unidecode import unidecode

from app.models import BankTransaction, Order, OrderStatus

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def normalize(text: str) -> str:
    return _NON_ALNUM.sub("", unidecode(text).upper())


async def find_and_match_order(db: AsyncSession, tx: BankTransaction) -> Order | None:
    normalized_content = normalize(tx.content)
    if not normalized_content:
        return None

    now = datetime.now(UTC)
    stmt = select(Order).where(
        Order.status == OrderStatus.PENDING.value,
        Order.expires_at > now,
    )
    result = await db.execute(stmt)
    candidates = result.scalars().all()

    for order in candidates:
        if order.order_code.upper() in normalized_content and tx.amount >= order.amount:
            order.status = OrderStatus.PAID.value
            order.paid_at = now
            order.matched_transaction_id = tx.id
            tx.matched_order_code = order.order_code
            await db.flush()
            return order
    return None
