"""اختبارات تطبيع رقم الجوال السعودي — المصدر المركزي."""

import pytest
from django.core.exceptions import ValidationError

from accounts.mobile import mask_mobile, normalize_mobile, validate_mobile

EXPECTED = "+966551234567"


@pytest.mark.parametrize(
    "raw",
    [
        "0551234567",
        "551234567",
        "966551234567",
        "+966551234567",
        "00966551234567",
        "055 123 4567",
        "055-123-4567",
        "٠٥٥١٢٣٤٥٦٧",  # أرقام عربية
        " +966551234567 ",
    ],
)
def test_normalize_accepts_common_formats(raw):
    assert normalize_mobile(raw) == EXPECTED


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "abc",
        "05512345",        # قصير
        "05512345678",     # طويل
        "0441234567",      # ليس جوال (لا يبدأ بـ 5)
        "+971551234567",   # دولة أخرى
        "0096650123456789",
        "055123456a",
        "+9660551234567",  # صفر زائد بعد كود الدولة
    ],
)
def test_normalize_rejects_invalid_numbers(raw):
    with pytest.raises(ValidationError):
        normalize_mobile(raw)


def test_validate_mobile_accepts_only_normalized_form():
    validate_mobile(EXPECTED)
    with pytest.raises(ValidationError):
        validate_mobile("0551234567")  # التخزين يجب أن يكون مطبعًا دائمًا


def test_mask_mobile_hides_middle_digits():
    masked = mask_mobile(EXPECTED)
    assert masked == "+9665****4567"
    assert "551234" not in masked
