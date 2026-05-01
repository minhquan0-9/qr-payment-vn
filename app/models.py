from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class OrderStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"
    CANCELED = "canceled"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # VND, integer
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default=OrderStatus.PENDING.value, nullable=False, index=True
    )

    qr_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    matched_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_transactions.id"), nullable=True
    )
    matched_transaction: Mapped[BankTransaction | None] = relationship(
        "BankTransaction", foreign_keys=[matched_transaction_id]
    )


class BankTransaction(Base):
    """Một biến động số dư đến từ SMS / webhook."""

    __tablename__ = "bank_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bank_code: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # số tiền vào (>0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    raw_message: Mapped[str] = mapped_column(Text, nullable=False)
    # khử trùng: hash của raw message để chống lưu lặp khi forwarder retry
    dedupe_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    matched_order_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
