"""اختبارات أمان رقم الهوية — التطبيع والتشفير وHMAC والتقنيع."""

import pytest
from django.core.exceptions import ValidationError

from common.security.identifiers import (
    decrypt_national_id,
    encrypt_national_id,
    mask_national_id,
    national_id_lookup_hash,
    normalize_national_id,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1012345678", "1012345678"),
        ("2098765432", "2098765432"),
        (" 1012345678 ", "1012345678"),
        ("101-234-5678", "1012345678"),
        ("١٠١٢٣٤٥٦٧٨", "1012345678"),  # أرقام عربية
        ("10 12 34 56 78", "1012345678"),
    ],
)
def test_normalize_accepts_valid_formats(raw, expected):
    assert normalize_national_id(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "abc", "3012345678", "101234567", "10123456789", "0012345678", None],
)
def test_normalize_rejects_invalid(raw):
    with pytest.raises(ValidationError):
        normalize_national_id(raw)


def test_encrypted_value_differs_from_plaintext():
    encrypted = encrypt_national_id("1012345678")
    assert "1012345678" not in encrypted
    assert len(encrypted) > 20


def test_decrypt_roundtrip():
    assert decrypt_national_id(encrypt_national_id("2098765432")) == "2098765432"


def test_hmac_deterministic_and_distinct():
    h1 = national_id_lookup_hash("1012345678")
    h2 = national_id_lookup_hash("1012345678")
    h3 = national_id_lookup_hash("1012345679")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64
    assert "1012345678" not in h1


def test_mask_shows_last_four_only():
    assert mask_national_id("1012345678") == "******5678"
