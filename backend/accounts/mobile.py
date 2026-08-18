"""تطبيع رقم الجوال السعودي والتحقق منه — المصدر المركزي الوحيد.

ممنوع تكرار هذا المنطق في Serializers أو Views. الصيغة الموحدة: +9665XXXXXXXX
"""

import re

from django.core.exceptions import ValidationError

# الأرقام العربية-الهندية → لاتينية
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# أي فواصل شائعة داخل الرقم
_SEPARATORS = re.compile(r"[\s\-().]")

NORMALIZED_MOBILE_RE = re.compile(r"^\+9665\d{8}$")

INVALID_MOBILE_MESSAGE = "رقم الجوال غير صحيح. أدخل رقم جوال سعودي مثل 05XXXXXXXX."


def normalize_mobile(raw: str) -> str:
    """يحول أي صيغة إدخال شائعة إلى ‎+9665XXXXXXXX أو يرفع ValidationError.

    المدخلات المقبولة (بعد إزالة الفواصل وتحويل الأرقام العربية):
    05XXXXXXXX / 5XXXXXXXX / 9665XXXXXXXX / +9665XXXXXXXX / 009665XXXXXXXX
    """
    if not isinstance(raw, str):
        raise ValidationError(INVALID_MOBILE_MESSAGE, code="invalid_mobile")

    value = _SEPARATORS.sub("", raw.strip()).translate(_ARABIC_DIGITS)

    if value.startswith("+"):
        digits = value[1:]
    elif value.startswith("00"):
        digits = value[2:]
    else:
        digits = value

    if not digits.isdigit():
        raise ValidationError(INVALID_MOBILE_MESSAGE, code="invalid_mobile")

    if digits.startswith("966"):
        rest = digits[3:]
    elif digits.startswith("05"):
        rest = digits[1:]
    elif digits.startswith("5"):
        rest = digits
    else:
        raise ValidationError(INVALID_MOBILE_MESSAGE, code="invalid_mobile")

    normalized = f"+966{rest}"
    if not NORMALIZED_MOBILE_RE.match(normalized):
        raise ValidationError(INVALID_MOBILE_MESSAGE, code="invalid_mobile")
    return normalized


def validate_mobile(value: str) -> None:
    """Validator لنموذج Django: يقبل الصيغة الموحدة فقط (التخزين مطبّع دائمًا)."""
    if not NORMALIZED_MOBILE_RE.match(value):
        raise ValidationError(INVALID_MOBILE_MESSAGE, code="invalid_mobile")


def mask_mobile(value: str) -> str:
    """تمثيل آمن للسجلات: ‎+9665****6789 — لا يكشف الرقم كاملًا."""
    if len(value) < 6:
        return "****"
    return f"{value[:5]}****{value[-4:]}"
