"""Test các helper parse trong MB Bank adapter (không cần đăng nhập thật)."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.services.banking.mbbank_client import _parse_amount, _parse_mb_datetime


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("500,000", 500_000),
        ("500.000", 500_000),
        ("500000", 500_000),
        ("1,500,000.00", 1_500_000),  # MB đôi khi trả có .00
        ("0", 0),
        ("", 0),
        ("abc", 0),
    ],
)
def test_parse_amount(raw: str, expected: int) -> None:
    assert _parse_amount(raw) == expected


def test_parse_mb_datetime_full() -> None:
    dt = _parse_mb_datetime("21/02/2025 10:34:12")
    assert dt == datetime(2025, 2, 21, 10, 34, 12)


def test_parse_mb_datetime_date_only() -> None:
    dt = _parse_mb_datetime("21/02/2025")
    assert dt == datetime(2025, 2, 21)


def test_parse_mb_datetime_invalid_returns_now_ish() -> None:
    dt = _parse_mb_datetime("not-a-date")
    # Không crash; trả về 1 datetime hợp lệ
    assert isinstance(dt, datetime)
