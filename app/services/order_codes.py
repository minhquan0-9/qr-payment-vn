"""Sinh order_code ngắn, dễ gõ, không trùng dấu phụ tiếng Việt."""

from __future__ import annotations

import secrets
import string

# Bỏ các ký tự dễ nhầm: 0, O, 1, I, L
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
assert all(c in string.ascii_uppercase + string.digits for c in _ALPHABET)


def generate_order_code(prefix: str = "PAY", length: int = 8) -> str:
    body = "".join(secrets.choice(_ALPHABET) for _ in range(length))
    return f"{prefix}{body}"
