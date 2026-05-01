"""Smoke test cho SMS parser với mẫu của các NH VN phổ biến."""

from __future__ import annotations

import pytest

from app.services.parsers import get_parser

CASES_INCOMING = [
    # Vietcombank
    (
        "VCB",
        "VCB 18/04 12:34 TK 0123456789 +500,000VND. SD: 1,234,567 VND. ND: PAY3F7K2X9A chuyen tien",
        500_000,
        "PAY3F7K2X9A",
    ),
    # MB Bank
    (
        "MB",
        "TK 0123 GD: +500,000VND luc 18/04 12:34. ND: PAYABCDEF12. So du: 1,234,567VND",
        500_000,
        "PAYABCDEF12",
    ),
    # Techcombank dùng dấu chấm phân cách nghìn
    (
        "TCB",
        "TK 1903xxxx +1.500.000 VND luc 12:34 18/04. SD: 5.234.567 VND. ND CK: PAY9X8YZW7B chuyen khoan",
        1_500_000,
        "PAY9X8YZW7B",
    ),
    # ACB
    (
        "ACB",
        "ACB Bank, 18/04 12:34, TK 1234, GD +200,000 VND, SD 1,234,567 VND, ND: PAYAAA111",
        200_000,
        "PAYAAA111",
    ),
    # BIDV
    (
        "BIDV",
        "BIDV thong bao TK 1234 GD: +750,000VND. ND: PAYBBB222 chuyen tien. SDC: 1,000,000VND",
        750_000,
        "PAYBBB222",
    ),
    # VietinBank
    (
        "VTB",
        "VietinBank: TK 1234 GD +50,000VND. ND CK: PAYCCC333. SDC 100,000",
        50_000,
        "PAYCCC333",
    ),
    # TPBank
    (
        "TPB",
        "TPBank: TK xxx1234 GD: +20,000VND. ND: PAYDDD444. SD: 1,234,567VND",
        20_000,
        "PAYDDD444",
    ),
    # Sacombank
    (
        "STB",
        "Sacombank: TK 0123 GD +99,000VND. ND: PAYEEE555. SDC 1,234,567",
        99_000,
        "PAYEEE555",
    ),
    # Agribank
    (
        "AGR",
        "AGRIBANK +123,000VND TK 1234 18/04 12:34 ND: PAYFFF666 SDC 1,234,567",
        123_000,
        "PAYFFF666",
    ),
    # Format không có dấu phẩy nghìn
    (
        "GENERIC",
        "+10000 VND. ND: PAYNODECIMAL. SD: 50000",
        10_000,
        "PAYNODECIMAL",
    ),
]


@pytest.mark.parametrize("bank_code,sms,expected_amount,expected_code", CASES_INCOMING)
def test_parse_incoming(bank_code: str, sms: str, expected_amount: int, expected_code: str) -> None:
    parser = get_parser(bank_code)
    parsed = parser.parse(sms)
    assert parsed is not None, f"parser returned None for {sms!r}"
    assert parsed.is_incoming, f"expected incoming, got direction={parsed.direction}"
    assert parsed.amount == expected_amount
    assert expected_code in parsed.content


def test_parse_outgoing_is_not_incoming() -> None:
    sms = "VCB 18/04 12:34 TK 0123456789 -100,000VND. SD: 234,567 VND. ND: ATM withdraw"
    parsed = get_parser("VCB").parse(sms)
    assert parsed is not None
    assert not parsed.is_incoming
    assert parsed.amount == 100_000


def test_parse_unrelated_text_returns_none() -> None:
    assert get_parser("GENERIC").parse("Hello world, no transaction here") is None
    assert get_parser("GENERIC").parse("") is None
