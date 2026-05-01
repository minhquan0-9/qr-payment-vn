"""Adapter cho ACB private mobile API.

Wrap thư viện ``makky-acb-api`` (https://pypi.org/project/makky-acb-api/, MIT).
Lib này dùng requests (sync) — wrap qua ``asyncio.to_thread`` để hoà với
event loop chung.

Endpoint chính:
  - POST https://apiapp.acb.com.vn/mb/v2/auth/tokens (login)
  - POST .../mb/v2/auth/refresh (refresh token)
  - GET  .../mb/legacy/ss/cs/bankservice/transfers/list/account-payment (balance)
  - GET  .../mb/legacy/ss/cs/bankservice/saving/tx-history (history)

CẢNH BÁO: lib unofficial; ACB có thể thay đổi API/headers/clientId bất kỳ lúc
nào. Nếu break, update ``makky-acb-api`` hoặc tự fork.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from datetime import datetime

from app.services.banking.base import BankClient, TxRecord

logger = logging.getLogger("payment.acb")


def _to_int_amount(v: float | int | str | None) -> int:
    if v is None:
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _ts_to_dt(v: int | float | str | None) -> datetime:
    """ACB trả ``postingDate`` / ``activeDatetime`` dưới dạng unix epoch ms."""
    if not v:
        return datetime.now()
    try:
        ts = float(v)
    except (TypeError, ValueError):
        return datetime.now()
    # Heuristic: > 10^11 → ms, ngược lại = s
    if ts > 1e11:
        ts /= 1000.0
    return datetime.fromtimestamp(ts)


class ACBClient(BankClient):
    bank_code = "ACB"

    def __init__(self, *, username: str, password: str, account_no: str = "") -> None:
        from acb_api import ACBClient as _Lib

        if not username or not password:
            raise ValueError("ACB_USERNAME / ACB_PASSWORD chưa cấu hình")
        self._account_no = account_no.strip()
        self._client = _Lib(username=username, password=password)
        self._discovered_accounts: list[str] = []

    async def _accounts_to_query(self, *, raise_on_error: bool = False) -> list[str]:
        if self._account_no:
            return [self._account_no]
        if self._discovered_accounts:
            return self._discovered_accounts
        try:
            balances_resp = await asyncio.to_thread(self._client.get_balances)
        except Exception:
            if raise_on_error:
                raise
            logger.exception("ACB get_balances() failed")
            return []
        accts: list[str] = []
        for acct in balances_resp.get("balances", []):
            no = acct.get("accountNumber")
            if no:
                accts.append(str(no))
        self._discovered_accounts = accts
        if accts:
            logger.info("ACB discovered accounts: %s", accts)
        return accts

    async def verify_login(self) -> dict:
        accts = await self._accounts_to_query(raise_on_error=True)
        return {"ok": True, "accounts": accts}

    async def fetch_incoming_transactions(
        self, *, since: datetime, until: datetime
    ) -> Iterable[TxRecord]:
        accounts = await self._accounts_to_query()
        if not accounts:
            return []

        out: list[TxRecord] = []
        for acct_no in accounts:
            try:
                # ACB chỉ hỗ trợ rows; không hỗ trợ since/until → lấy 50 tx
                # gần nhất rồi filter trong Python.
                txs = await asyncio.to_thread(
                    self._client.get_transactions, 50, acct_no
                )
            except Exception:
                logger.exception("ACB get_transactions(%s) failed", acct_no)
                continue

            for tx in txs:
                amount = _to_int_amount(tx.get("amount"))
                if amount <= 0:
                    continue  # bỏ giao dịch tiền ra (negative) hoặc 0
                # ACB dùng ``transactionNumber`` làm unique
                tx_no = tx.get("transactionNumber")
                if not tx_no:
                    continue
                posted_at = _ts_to_dt(tx.get("postingDate") or tx.get("activeDatetime"))
                if posted_at < since or posted_at > until:
                    continue
                content = (tx.get("description") or "").strip()
                out.append(
                    TxRecord(
                        external_ref=f"acb:{tx_no}",
                        amount=amount,
                        content=content,
                        posted_at=posted_at,
                        bank_code=self.bank_code,
                        raw=dict(tx),
                    )
                )
        return out

    async def aclose(self) -> None:
        # makky-acb-api dùng requests.Session — đóng để giải phóng socket
        try:
            await asyncio.to_thread(self._client.session.close)
        except Exception:
            pass
