"""Sinh URL QR thanh toán theo chuẩn VietQR.

Dùng dịch vụ ảnh tĩnh của VietQR.io (free, không cần đăng ký) để khỏi phải
generate ảnh server-side. Nếu cần tự generate, dùng EMVCo TLV + thư viện qrcode.
"""

from __future__ import annotations

from urllib.parse import quote_plus

VIETQR_BASE = "https://img.vietqr.io/image"


def build_vietqr_url(
    *,
    bank_bin: str,
    account_number: str,
    account_name: str,
    amount: int,
    add_info: str,
    template: str = "compact2",
) -> str:
    """Trả về URL ảnh QR có thể nhét trực tiếp vào <img src>.

    Tham khảo: https://www.vietqr.io/danh-sach-api/
    """
    qs = f"amount={amount}&addInfo={quote_plus(add_info)}&accountName={quote_plus(account_name)}"
    return f"{VIETQR_BASE}/{bank_bin}-{account_number}-{template}.png?{qs}"
