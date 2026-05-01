"""Worker poll lịch sử giao dịch từ ``BankClient`` và match với order.

Mỗi vòng:
  1. Hỏi BankClient các giao dịch đã posting trong cửa sổ [last_seen, now].
  2. Với mỗi tx có ``external_ref`` chưa thấy: lưu BankTransaction, gọi matcher.
  3. Nếu matcher tìm ra order → publish event "paid" qua bus.

Cấu hình:
  - POLL_INTERVAL_SECONDS: chu kỳ poll
  - POLL_LOOKBACK_MINUTES: cửa sổ lùi quá khứ ở lần poll đầu

Lưu ý:
  - Dùng external_ref của NH (ví dụ refNo của MB) để dedupe → không lưu trùng dù
    poll trùng cửa sổ.
  - Worker này có thể chạy trong cùng FastAPI process (lifespan) HOẶC trong 1
    container worker riêng (xem ``app/worker.py``). Giữ idempotent để chịu được
    restart đột ngột.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import SessionLocal
from app.models import BankTransaction
from app.services.banking import BankClient, TxRecord
from app.services.events import bus
from app.services.matcher import find_and_match_order

logger = logging.getLogger("payment.poller")


class BankPoller:
    def __init__(
        self,
        client: BankClient,
        *,
        interval_seconds: int = 10,
        lookback_minutes: int = 30,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.client = client
        self.interval = interval_seconds
        self.lookback = timedelta(minutes=lookback_minutes)
        self._session_factory = session_factory or SessionLocal
        self._last_run: datetime | None = None
        self._stop = asyncio.Event()

    async def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        logger.info(
            "Poller started: bank=%s interval=%ss lookback=%s",
            self.client.bank_code,
            self.interval,
            self.lookback,
        )
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("Poller tick failed; will retry next interval")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except TimeoutError:
                pass
        await self.client.aclose()
        logger.info("Poller stopped")

    async def _tick(self) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        since = self._last_run or (now - self.lookback)
        # Cộng buffer 30s để chắc ăn không miss tx gần biên
        since_buffered = since - timedelta(seconds=30)
        records = await self.client.fetch_incoming_transactions(since=since_buffered, until=now)
        n_new = 0
        for tx in records:
            if await self._ingest_one(tx):
                n_new += 1
        if n_new:
            logger.info("Poller tick: %d new tx ingested", n_new)
        self._last_run = now

    async def _ingest_one(self, tx: TxRecord) -> bool:
        """Trả về True nếu là tx mới (đã ingest), False nếu duplicate."""
        async with self._session_factory() as db:
            existing = await db.execute(
                select(BankTransaction).where(BankTransaction.dedupe_hash == tx.external_ref)
            )
            if existing.scalar_one_or_none() is not None:
                return False

            row = BankTransaction(
                bank_code=tx.bank_code,
                amount=tx.amount,
                content=tx.content,
                raw_message=_safe_str(tx.raw),
                dedupe_hash=tx.external_ref,
            )
            db.add(row)
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                return False

            matched = await find_and_match_order(db, row)
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
                logger.info(
                    "MATCH order=%s amount=%s tx_ref=%s",
                    matched.order_code,
                    tx.amount,
                    tx.external_ref,
                )
            else:
                logger.info(
                    "Ingested tx ref=%s amount=%s content=%r (no match)",
                    tx.external_ref,
                    tx.amount,
                    tx.content[:80],
                )
            return True


def _safe_str(d: object) -> str:
    try:
        import json

        return json.dumps(d, ensure_ascii=False, default=str)[:4000]
    except Exception:
        return str(d)[:4000]
