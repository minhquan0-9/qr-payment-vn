"""Adapter cho TPBank web banking (ebank.tpb.vn).

Port logic từ thư viện npm ``tpbank-api`` (chuanghiduoc/api_tpbank_free, MIT)
sang Python httpx.

Quy trình:
  1. Lấy ``deviceId`` từ browser sau khi đăng nhập web banking 1 lần
     (xem docs/tpbank-setup.md). deviceId này chứng minh "thiết bị đã verify"
     để bypass xác minh khuôn mặt.
  2. POST /gateway/api/auth/login/v4/non-trust với username/password/deviceId
     → trả về access_token + expires_in (giây).
  3. POST /gateway/api/smart-search-presentation-service/v2/account-transactions/find
     với accountNo + fromDate (YYYYMMDD) + toDate → trả về danh sách giao dịch.

CẢNH BÁO: TPBank có thể block IP nếu poll quá nhanh hoặc đổi format API.
Khuyến nghị: POLL_INTERVAL_SECONDS >= 10s, dùng proxy xoay nếu cần.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timedelta

import httpx

from app.services.banking.base import BankClient, TxRecord

logger = logging.getLogger("payment.tpb")

API_BASE = "https://ebank.tpb.vn"
LOGIN_URL = f"{API_BASE}/gateway/api/auth/login/v4/non-trust"
TX_URL = f"{API_BASE}/gateway/api/smart-search-presentation-service/v2/account-transactions/find"

DEFAULT_HEADERS = {
    "APP_VERSION": "2026.01.30",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "DEVICE_NAME": "Chrome",
    "Origin": API_BASE,
    "PLATFORM_NAME": "WEB",
    "PLATFORM_VERSION": "145",
    "SOURCE_APP": "HYDRO",
    "USER_NAME": "HYD",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

TOKEN_REFRESH_BUFFER_SECONDS = 60


def _to_int_amount(v: float | int | str | None) -> int:
    if v is None:
        return 0
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return 0


class TPBankAuthError(RuntimeError):
    pass


class TPBankClient(BankClient):
    bank_code = "TPB"

    def __init__(
        self,
        *,
        username: str,
        password: str,
        device_id: str,
        account_id: str,
        timeout: float = 30.0,
    ) -> None:
        if not username or not password:
            raise ValueError("TPB_USERNAME / TPB_PASSWORD chưa cấu hình")
        if not device_id:
            raise ValueError(
                "TPB_DEVICE_ID chưa cấu hình. Lấy từ browser: F12 → Console → "
                "localStorage.deviceId (xem docs/tpbank-setup.md)"
            )
        if not account_id:
            raise ValueError("TPB_ACCOUNT_ID chưa cấu hình (số tài khoản TPBank)")
        self._username = username
        self._password = password
        self._device_id = device_id
        self._account_id = account_id
        self._access_token: str | None = None
        self._token_expiry: datetime | None = None
        self._http: httpx.AsyncClient = httpx.AsyncClient(timeout=timeout)

    def _build_headers(self, token: str | None) -> dict[str, str]:
        h = {**DEFAULT_HEADERS, "DEVICE_ID": self._device_id}
        if token:
            h["Authorization"] = f"Bearer {token}"
        else:
            h["Authorization"] = "Bearer"
            h["Referer"] = f"{API_BASE}/retail/vX/"
        return h

    def _token_valid(self) -> bool:
        if not self._access_token or self._token_expiry is None:
            return False
        return datetime.now() < self._token_expiry - timedelta(
            seconds=TOKEN_REFRESH_BUFFER_SECONDS
        )

    async def _login(self) -> None:
        body = {
            "username": self._username,
            "password": self._password,
            "deviceId": self._device_id,
            "transactionId": "",
        }
        r = await self._http.post(LOGIN_URL, headers=self._build_headers(None), json=body)
        if r.status_code != 200:
            raise TPBankAuthError(f"TPB login failed {r.status_code}: {r.text[:200]}")
        data = r.json()
        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 900))
        if not token:
            raise TPBankAuthError(f"TPB login no access_token: {data}")
        self._access_token = token
        self._token_expiry = datetime.now() + timedelta(seconds=expires_in)
        logger.info("TPB login OK, expires in %ds", expires_in)

    async def _ensure_auth(self) -> str:
        if not self._token_valid():
            await self._login()
        assert self._access_token is not None
        return self._access_token

    async def fetch_incoming_transactions(
        self, *, since: datetime, until: datetime
    ) -> Iterable[TxRecord]:
        token = await self._ensure_auth()

        # TPBank chỉ hỗ trợ fromDate/toDate format YYYYMMDD
        # → query 1 ngày bao trùm cửa sổ + filter Python sau
        from_date = since.strftime("%Y%m%d")
        to_date = until.strftime("%Y%m%d")
        body = {
            "pageNumber": 1,
            "pageSize": 400,
            "accountNo": self._account_id,
            "currency": "VND",
            "maxAcentrysrno": "",
            "fromDate": from_date,
            "toDate": to_date,
            "keyword": "",
        }

        r = await self._http.post(TX_URL, headers=self._build_headers(token), json=body)
        if r.status_code == 401:
            self._access_token = None
            token = await self._ensure_auth()
            r = await self._http.post(TX_URL, headers=self._build_headers(token), json=body)
        if r.status_code != 200:
            logger.error("TPB tx fetch failed %s: %s", r.status_code, r.text[:200])
            return []

        data = r.json()
        # Format response phổ biến của TPBank: data có thể nằm ở "transactionInfos"
        # hoặc "data" tuỳ phiên bản API. Thử các key thường gặp.
        items = (
            data.get("transactionInfos")
            or data.get("transactions")
            or data.get("data")
            or []
        )

        out: list[TxRecord] = []
        for tx in items:
            # TPBank: creditAmount = tiền vào, debitAmount = tiền ra
            credit = _to_int_amount(tx.get("creditAmount") or tx.get("amountCredit"))
            if credit <= 0:
                continue
            ref = (
                tx.get("transactionId")
                or tx.get("transactionRefNo")
                or tx.get("acentrysrno")
                or tx.get("traceTransfer")
                or ""
            )
            if not ref:
                continue
            content = (tx.get("description") or tx.get("content") or "").strip()
            posted_at = _parse_tpb_datetime(tx.get("transactionDate") or tx.get("postingDate"))
            if posted_at and (posted_at < since or posted_at > until):
                continue
            out.append(
                TxRecord(
                    external_ref=f"tpb:{ref}",
                    amount=credit,
                    content=content,
                    posted_at=posted_at or datetime.now(),
                    bank_code=self.bank_code,
                    raw=dict(tx),
                )
            )
        return out

    async def verify_login(self) -> dict:
        await self._login()  # raise nếu fail
        return {"ok": True, "accounts": [self._account_id]}

    async def aclose(self) -> None:
        await self._http.aclose()


def _parse_tpb_datetime(s: str | None) -> datetime | None:
    """TPBank trả date kiểu '20250318' hoặc '18/03/2025 14:30:00'."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in (
        "%Y%m%d %H:%M:%S",
        "%Y%m%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None
