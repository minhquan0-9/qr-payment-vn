"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bank_transactions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("bank_code", sa.String(16), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("raw_message", sa.Text, nullable=False),
        sa.Column("dedupe_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("matched_order_code", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_bank_transactions_matched_order_code",
        "bank_transactions",
        ["matched_order_code"],
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("order_code", sa.String(64), nullable=False, unique=True),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("qr_url", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "matched_transaction_id",
            sa.Integer,
            sa.ForeignKey("bank_transactions.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_orders_order_code", "orders", ["order_code"], unique=True)
    op.create_index("ix_orders_status", "orders", ["status"])


def downgrade() -> None:
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_order_code", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_bank_transactions_matched_order_code", table_name="bank_transactions")
    op.drop_table("bank_transactions")
