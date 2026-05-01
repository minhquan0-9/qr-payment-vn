"""Test factory build_client_from_settings."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.banking import build_client_from_settings


def _settings(**overrides):
    base = {
        "bank_type": "mb",
        "mb_username": "mb_user",
        "mb_password": "mb_pass",
        "mb_account_no": "",
        "acb_username": "acb_user",
        "acb_password": "acb_pass",
        "acb_account_no": "",
        "tpb_username": "tpb_user",
        "tpb_password": "tpb_pass",
        "tpb_device_id": "DEV",
        "tpb_account_id": "0123",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_factory_unknown_bank_type():
    with pytest.raises(ValueError, match="Unknown BANK_TYPE"):
        build_client_from_settings(_settings(bank_type="vcb"))


def test_factory_builds_acb():
    with patch("acb_api.ACBClient"):
        c = build_client_from_settings(_settings(bank_type="acb"))
    assert c.bank_code == "ACB"


def test_factory_builds_tpb():
    c = build_client_from_settings(_settings(bank_type="tpb"))
    assert c.bank_code == "TPB"


def test_factory_explicit_overrides_settings():
    with patch("acb_api.ACBClient"):
        c = build_client_from_settings(_settings(bank_type="mb"), bank_type="acb")
    assert c.bank_code == "ACB"
