"""Adapter cho MB Bank private API.

Wrap thư viện ``mbbank-lib`` (https://github.com/thedtvn/MBBank, MIT). Lib này:
  - Đăng nhập username/password qua endpoint mobile của MB.
  - Tự giải captcha bằng ONNX OCR.
  - Lấy lịch sử giao dịch theo khoảng thời gian.

Class này quy đổi ``mbbank.modals.Transaction`` thành ``TxRecord`` thống nhất.

CẢNH BÁO: lib không official; MB có thể đổi API/captcha bất kỳ lúc nào hoặc
từ chối nếu phát hiện automation. Luôn log tx thô để dễ debug khi parser break.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from datetime import datetime

from app.services.banking.base import BankClient, TxRecord

logger = logging.getLogger("payment.mbbank")


def _parse_amount(s: str) -> int:
    """'500,000' / '500.000' / '500000' / '500,000.00' -> 500000."""
    if not s:
        return 0
    s = s.strip()
    # nếu có cả ',' và '.', '.' thường là decimal -> bỏ phần sau '.'
    if "," in s and "." in s:
        s = s.split(".")[0]
    return (
        int(s.replace(",", "").replace(".", ""))
        if s.replace(",", "").replace(".", "").isdigit()
        else 0
    )


def _parse_mb_datetime(s: str) -> datetime:
    """MB trả postingDate kiểu '21/02/2025 10:34:12' (giờ VN)."""
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.now()


class MBBankClient(BankClient):
    bank_code = "MB"

    def __init__(self, *, username: str, password: str, account_no: str = "") -> None:
        # Lazy import để tests không yêu cầu lib khi mock
        from mbbank import MBBankAsync

        if not username or not password:
            raise ValueError("MB_USERNAME / MB_PASSWORD chưa cấu hình")
        self._account_no = account_no.strip()
        self._client = MBBankAsync(username=username, password=password)
        self._discovered_accounts: list[str] = []

    async def _accounts_to_query(self) -> list[str]:
        if self._account_no:
            return [self._account_no]
        if self._discovered_accounts:
            return self._discovered_accounts
        try:
            balance = await self._client.getBalance()
        except Exception:
            logger.exception("MB getBalance() failed")
            return []
        accts: list[str] = []
        for acct in getattr(balance, "acct_list", []) or []:
            no = getattr(acct, "acctNo", None) or getattr(acct, "accountNo", None)
            if no:
                accts.append(str(no))
        self._discovered_accounts = accts
        if accts:
            logger.info("MB discovered accounts: %s", accts)
        return accts

    async def fetch_incoming_transactions(
        self, *, since: datetime, until: datetime
    ) -> Iterable[TxRecord]:
        accounts = await self._accounts_to_query()
        if not accounts:
            return []

        out: list[TxRecord] = []
        for acct_no in accounts:
            try:
                resp = await self._client.getTransactionAccountHistory(
                    account_no=acct_no, from_date=since, to_date=until
                )
            except TypeError:
                # Một số version lib dùng tham số khác
                resp = await self._client.getTransactionAccountHistory(
                    accountNo=acct_no, fromDate=since, toDate=until
                )
            except Exception:
                logger.exception("MB getTransactionAccountHistory(%s) failed", acct_no)
                continue

            txs = getattr(resp, "transactionHistoryList", None) or []
            for tx in txs:
                credit = _parse_amount(getattr(tx, "creditAmount", "0") or "0")
                if credit <= 0:
                    continue  # bỏ giao dịch tiền ra
                ref_no = getattr(tx, "refNo", "") or ""
                if not ref_no:
                    continue
                desc = getattr(tx, "description", "") or ""
                add_desc = getattr(tx, "addDescription", "") or ""
                content = (add_desc + " " + desc).strip()
                posted_at = _parse_mb_datetime(getattr(tx, "postingDate", "") or "")
                out.append(
                    TxRecord(
                        external_ref=f"mb:{ref_no}",
                        amount=credit,
                        content=content,
                        posted_at=posted_at,
                        bank_code=self.bank_code,
                        raw=tx.model_dump() if hasattr(tx, "model_dump") else dict(tx),
                    )
                )
        return out

    async def aclose(self) -> None:
        # mbbank-lib không expose explicit close; aiohttp session được tạo per-request
        await asyncio.sleep(0)
