"""Factory + exports cho các adapter ngân hàng."""
from __future__ import annotations

from app.services.banking.base import BankClient, TxRecord


def build_client_from_settings(settings, *, bank_type: str | None = None) -> BankClient:
    """Tạo ``BankClient`` tương ứng với ``BANK_TYPE`` env (mb/acb/tpb)."""
    bank = (bank_type or settings.bank_type or "mb").lower()
    if bank == "mb":
        from app.services.banking.mbbank_client import MBBankClient
        return MBBankClient(
            username=settings.mb_username,
            password=settings.mb_password,
            account_no=settings.mb_account_no,
        )
    if bank == "acb":
        from app.services.banking.acb_client import ACBClient
        return ACBClient(
            username=settings.acb_username,
            password=settings.acb_password,
            account_no=settings.acb_account_no,
        )
    if bank == "tpb":
        from app.services.banking.tpbank_client import TPBankClient
        return TPBankClient(
            username=settings.tpb_username,
            password=settings.tpb_password,
            device_id=settings.tpb_device_id,
            account_id=settings.tpb_account_id,
        )
    raise ValueError(f"Unknown BANK_TYPE: {bank!r} (expected: mb / acb / tpb)")


__all__ = ["BankClient", "TxRecord", "build_client_from_settings"]
