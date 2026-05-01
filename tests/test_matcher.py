"""Test matching engine với DB SQLite in-memory."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models import BankTransaction, Order, OrderStatus
from app.services.matcher import find_and_match_order, normalize


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


def test_normalize() -> None:
    assert normalize("Chuyển khoản PAY-123 ABC.") == "CHUYENKHOANPAY123ABC"
    assert normalize("") == ""


@pytest.mark.asyncio
async def test_match_happy_path(session) -> None:
    now = datetime.now(UTC)
    order = Order(
        order_code="PAY3F7K2X",
        amount=100_000,
        status=OrderStatus.PENDING.value,
        created_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    session.add(order)
    await session.flush()

    tx = BankTransaction(
        bank_code="VCB",
        amount=100_000,
        content="chuyen tien PAY3F7K2X xin cam on",
        raw_message="raw",
        dedupe_hash="h1",
    )
    session.add(tx)
    await session.flush()

    matched = await find_and_match_order(session, tx)
    assert matched is not None
    assert matched.order_code == "PAY3F7K2X"
    assert matched.status == OrderStatus.PAID.value


@pytest.mark.asyncio
async def test_no_match_when_amount_less(session) -> None:
    now = datetime.now(UTC)
    order = Order(
        order_code="PAYAMOUNT",
        amount=200_000,
        status=OrderStatus.PENDING.value,
        created_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    session.add(order)
    await session.flush()

    tx = BankTransaction(
        bank_code="VCB",
        amount=100_000,  # thiếu tiền
        content="PAYAMOUNT",
        raw_message="raw",
        dedupe_hash="h2",
    )
    session.add(tx)
    await session.flush()

    matched = await find_and_match_order(session, tx)
    assert matched is None


@pytest.mark.asyncio
async def test_amount_overpay_still_matches(session) -> None:
    now = datetime.now(UTC)
    order = Order(
        order_code="PAYOVER",
        amount=50_000,
        status=OrderStatus.PENDING.value,
        created_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    session.add(order)
    await session.flush()

    tx = BankTransaction(
        bank_code="VCB", amount=100_000, content="ck PAYOVER", raw_message="r", dedupe_hash="h3"
    )
    session.add(tx)
    await session.flush()

    matched = await find_and_match_order(session, tx)
    assert matched is not None
    assert matched.status == OrderStatus.PAID.value


@pytest.mark.asyncio
async def test_expired_order_not_matched(session) -> None:
    now = datetime.now(UTC)
    order = Order(
        order_code="PAYEXPIRED",
        amount=10_000,
        status=OrderStatus.PENDING.value,
        created_at=now - timedelta(hours=1),
        expires_at=now - timedelta(minutes=1),  # đã hết hạn
    )
    session.add(order)
    await session.flush()

    tx = BankTransaction(
        bank_code="VCB", amount=10_000, content="PAYEXPIRED", raw_message="r", dedupe_hash="h4"
    )
    session.add(tx)
    await session.flush()

    assert await find_and_match_order(session, tx) is None


@pytest.mark.asyncio
async def test_normalize_handles_diacritics_and_punctuation(session) -> None:
    now = datetime.now(UTC)
    order = Order(
        order_code="PAYZ123",
        amount=1_000,
        status=OrderStatus.PENDING.value,
        created_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    session.add(order)
    await session.flush()

    tx = BankTransaction(
        bank_code="VCB",
        amount=1_000,
        content="Chuyển khoản: PAY-Z.123 - cảm ơn bạn",
        raw_message="r",
        dedupe_hash="h5",
    )
    session.add(tx)
    await session.flush()

    matched = await find_and_match_order(session, tx)
    assert matched is not None
