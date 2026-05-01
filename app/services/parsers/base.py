"""SMS parser cho biến động số dư các ngân hàng VN.

Hầu hết SMS biến động đều có chung 3 thông tin cốt lõi:
 1. Hướng giao dịch (+/-): chỉ quan tâm "+" (tiền vào)
 2. Số tiền: chuỗi số có dấu phẩy/chấm phân cách nghìn, có thể có "VND" / "đ"
 3. Nội dung chuyển khoản: thường nằm sau "ND:", "ND CK:", "Noi dung:", "Content:"

Chiến lược:
 - Một parser GENERIC dùng regex flexible, đủ mạnh để xử lý 80%+ format.
 - Cho phép override per-bank nếu format đặc biệt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class ParsedSMS:
    amount: int  # VND, > 0 nếu là tiền vào
    content: str  # nội dung chuyển khoản đã trim
    direction: str  # "in" | "out"
    raw: str

    @property
    def is_incoming(self) -> bool:
        return self.direction == "in"


# ----- Regex patterns dùng chung -----

# Khớp số tiền tiền vào: dấu "+" hoặc "GD +" hoặc "GT +" sau đó là chuỗi số
# có thể có dấu , hoặc . phân cách nghìn, kết thúc bằng VND/vnd/đ/d
_AMOUNT_IN_RE = re.compile(
    r"""
    (?:
        \+\s*
      | (?:GD|GT|PS|PSGD|GDC|GTRT|TT)\s*[:\-]?\s*\+\s*
      | (?:tang|TANG|increase|INCREASE)\s*[:\-]?\s*
    )
    (?P<amount>\d{1,3}(?:[.,]\d{3})+|\d+)
    \s*(?:VND|vnd|VNĐ|vnđ|đ|d|đồng|VNĐ\.)?
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Khớp số tiền tiền ra (để phát hiện và bỏ qua)
_AMOUNT_OUT_RE = re.compile(
    r"""
    (?:
        -\s*
      | (?:GD|GT|PS|PSGD|GDC|GTRT|TT)\s*[:\-]?\s*-\s*
      | (?:giam|GIAM|decrease|DECREASE)\s*[:\-]?\s*
    )
    (?P<amount>\d{1,3}(?:[.,]\d{3})+|\d+)
    \s*(?:VND|vnd|VNĐ|vnđ|đ|d|đồng)?
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Khớp nội dung chuyển khoản. Bắt phần text sau các nhãn phổ biến cho đến khi
# gặp nhãn khác (SD/SDC/Du/So du) hoặc hết chuỗi.
_CONTENT_RE = re.compile(
    r"""
    (?:
        ND\s*CK
      | ND\s*GD
      | NDCK
      | ND
      | Noi\s*dung
      | NDung
      | Noidung
      | Content
      | Description
      | Desc
      | Memo
    )
    \s*[:\-]\s*
    (?P<content>.+?)
    (?=
        \s*(?:
            SD\b | SDC\b | SDCK\b | SoDu\b | So\s*du\b | Du\s*no\b | Du\s*co\b
          | Balance\b | BAL\b | TKThe\b
        )
      | $
    )
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)


def _parse_amount(s: str) -> int:
    """Chuẩn hoá '500,000' / '500.000' / '500000' -> 500000."""
    return int(s.replace(",", "").replace(".", ""))


class SMSParser:
    """Parser mặc định, hoạt động với hầu hết NH VN."""

    bank_code: str = "GENERIC"

    def parse(self, message: str) -> ParsedSMS | None:
        text = message.strip()
        if not text:
            return None

        in_match = _AMOUNT_IN_RE.search(text)
        out_match = _AMOUNT_OUT_RE.search(text)

        # Nếu chỉ có "-" (tiền ra) thì bỏ qua
        if out_match and not in_match:
            return ParsedSMS(
                amount=_parse_amount(out_match.group("amount")),
                content=self._extract_content(text),
                direction="out",
                raw=message,
            )

        if not in_match:
            return None

        amount = _parse_amount(in_match.group("amount"))
        content = self._extract_content(text)
        return ParsedSMS(amount=amount, content=content, direction="in", raw=message)

    def _extract_content(self, text: str) -> str:
        m = _CONTENT_RE.search(text)
        if not m:
            return ""
        # cắt bỏ trailing punctuation phổ biến
        return m.group("content").strip().rstrip(".,;:")


# ----- Bank-specific overrides (thừa kế parser chung; chỉ override nếu cần) -----


class VCBParser(SMSParser):
    bank_code = "VCB"


class MBParser(SMSParser):
    bank_code = "MB"


class BIDVParser(SMSParser):
    bank_code = "BIDV"


class VTBParser(SMSParser):
    bank_code = "VTB"  # VietinBank


class ACBParser(SMSParser):
    bank_code = "ACB"


class TCBParser(SMSParser):
    bank_code = "TCB"  # Techcombank


class TPBParser(SMSParser):
    bank_code = "TPB"


class STBParser(SMSParser):
    bank_code = "STB"  # Sacombank


class AGRParser(SMSParser):
    bank_code = "AGR"  # Agribank


_PARSERS: dict[str, SMSParser] = {
    p.bank_code: p
    for p in (
        SMSParser(),
        VCBParser(),
        MBParser(),
        BIDVParser(),
        VTBParser(),
        ACBParser(),
        TCBParser(),
        TPBParser(),
        STBParser(),
        AGRParser(),
    )
}


def get_parser(bank_code: str | None) -> SMSParser:
    if not bank_code:
        return _PARSERS["GENERIC"]
    return _PARSERS.get(bank_code.upper(), _PARSERS["GENERIC"])
