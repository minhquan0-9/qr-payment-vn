"""Test BankPoller end-to-end với fake BankClient (không cần MB thật)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models import BankTransaction, Order, OrderStatus
from app.services.banking import BankClient, TxRecord
from app.services.events import bus
from app.services.poller import BankPoller


class FakeBankClient(BankClient):
    bank_code = "FAKE"

    def __init__(self) -> None:
        self.queues: list[list[TxRecord]] = []
        self.calls = 0

    def push(self, txs: list[TxRecord]) -> None:
        self.queues.append(txs)

    async def fetch_incoming_transactions(
        self, *, since: datetime, until: datetime
    ) -> Iterable[TxRecord]:
        self.calls += 1
        if not self.queues:
            return []
        return self.queues.pop(0)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _tx(ref: str, amount: int, content: str) -> TxRecord:
    return TxRecord(
        external_ref=ref,
        amount=amount,
        content=content,
        posted_at=datetime.now(UTC).replace(tzinfo=None),
        bank_code="FAKE",
        raw={"refNo": ref},
    )


@pytest.mark.asyncio
async def test_poller_ingests_and_matches_order(session_factory) -> None:
    # Tạo trước 1 order pending
    async with session_factory() as db:
        order = Order(
            order_code="PAYHELLO",
            amount=10_000,
            status=OrderStatus.PENDING.value,
            created_at=datetime.now(UTC).replace(tzinfo=None),
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=15),
        )
        db.add(order)
        await db.commit()

    # Sub vào event bus để đảm bảo event "paid" được phát
    queue = await bus.subscribe("PAYHELLO")

    fake = FakeBankClient()
    fake.push([_tx("MBREF1", 10_000, "chuyen tien PAYHELLO cam on")])

    poller = BankPoller(
        client=fake,
        interval_seconds=999,
        lookback_minutes=30,
        session_factory=session_factory,
    )
    await poller._tick()  # noqa: SLF001 — direct tick for test

    # Order phải đã chuyển sang paid
    async with session_factory() as db:
        from sqlalchemy import select

        r = await db.execute(select(Order).where(Order.order_code == "PAYHELLO"))
        order = r.scalar_one()
        assert order.status == OrderStatus.PAID.value
        assert order.paid_at is not None

        # Tx phải được lưu với dedupe_hash đúng
        r = await db.execute(select(BankTransaction))
        txs = r.scalars().all()
        assert len(txs) == 1
        assert txs[0].dedupe_hash == "mb:MBREF1" or txs[0].dedupe_hash == "MBREF1"

    # Event "paid" phải được publish
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event["event"] == "paid"
    assert event["order_code"] == "PAYHELLO"

    await bus.unsubscribe("PAYHELLO", queue)


@pytest.mark.asyncio
async def test_poller_dedupes_repeated_tx(session_factory) -> None:
    fake = FakeBankClient()
    fake.push([_tx("MBREFDUP", 5_000, "no-match")])
    fake.push([_tx("MBREFDUP", 5_000, "no-match")])  # cùng ref ở tick 2

    poller = BankPoller(
        client=fake,
        interval_seconds=999,
        lookback_minutes=30,
        session_factory=session_factory,
    )
    await poller._tick()  # noqa: SLF001
    await poller._tick()  # noqa: SLF001

    async with session_factory() as db:
        from sqlalchemy import select

        r = await db.execute(select(BankTransaction))
        txs = r.scalars().all()
        assert len(txs) == 1, "duplicate ref must be ingested only once"


@pytest.mark.asyncio
async def test_poller_unmatched_tx_still_recorded(session_factory) -> None:
    fake = FakeBankClient()
    fake.push([_tx("MBREFNOMATCH", 7_000, "random text no order code")])

    poller = BankPoller(
        client=fake,
        interval_seconds=999,
        lookback_minutes=30,
        session_factory=session_factory,
    )
    await poller._tick()  # noqa: SLF001

    async with session_factory() as db:
        from sqlalchemy import select

        r = await db.execute(select(BankTransaction))
        txs = r.scalars().all()
        assert len(txs) == 1
        assert txs[0].matched_order_code is None
