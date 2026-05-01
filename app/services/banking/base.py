"""Abstraction cho các nguồn dữ liệu giao dịch ngân hàng.

Mục đích: tách phần "lấy giao dịch từ NH X" khỏi phần "match order + emit SSE",
để sau này dễ chuyển từ MB Bank sang Sepay/Casso/SMS forwarder mà không phải
sửa logic order.

Mọi BankClient chỉ cần trả về danh sách `TxRecord` (đã filter chỉ tiền vào)
trong 1 cửa sổ thời gian; phần còn lại do `app.services.poller` đảm nhiệm.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class TxRecord:
    """1 giao dịch tiền vào, đã chuẩn hoá từ format gốc của NH."""

    external_ref: str  # mã unique từ NH (ví dụ refNo của MB) — dùng để dedupe
    amount: int  # VND, > 0
    content: str  # nội dung chuyển khoản (đã merge description + addDescription)
    posted_at: datetime  # thời điểm posting (theo giờ NH)
    bank_code: str
    raw: dict  # giữ nguyên payload gốc để log / debug


class BankClient(ABC):
    """Interface cho mọi adapter NH."""

    bank_code: str = "GENERIC"

    @abstractmethod
    async def fetch_incoming_transactions(
        self, *, since: datetime, until: datetime
    ) -> Iterable[TxRecord]:
        """Trả về các giao dịch tiền vào trong [since, until]."""
        ...

    async def aclose(self) -> None:
        """Hook cleanup nếu adapter có session/connection cần đóng."""
        return None
