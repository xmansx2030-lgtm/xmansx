"""أمان رقم الهوية/الإقامة — المصدر المركزي الوحيد (ADR-009).

- التخزين: تشفير متماثل Fernet (MultiFernet لدعم تدوير المفاتيح).
- البحث الدقيق: HMAC-SHA256 deterministic بمفتاح منفصل — لا فك تشفير جماعي أبدًا.
- العرض: مقنع `******1234` — الرقم الكامل لا يظهر في القوائم/السجلات/الأخطاء.

إدارة المفاتيح (موثق في docs/IDENTIFIER_SECURITY.md):
- FIELD_ENCRYPTION_KEYS: قائمة مفاتيح Fernet مفصولة بفواصل، الأحدث أولًا.
  التدوير: أضف الجديد أول القائمة → أعد تشفير السجلات بمهمة خلفية → أزل القديم.
- NATIONAL_ID_HMAC_KEY: مفتاح مستقل؛ تدويره يتطلب إعادة حساب كل الـ hashes (عملية مجدولة).
- الإنتاج يفشل عند غيابها (config/settings/production.py) — لا defaults غير آمنة.
"""

import hashlib
import hmac
import re
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ValidationError

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
# مسافات، فواصل، شرطات، ومحارف عرض صفرية
_STRIP_CHARS = re.compile(r"[\s\-.,/​‌‍‎‏﻿]")

# الهوية الوطنية تبدأ بـ 1، الإقامة تبدأ بـ 2 — عشر خانات
NATIONAL_ID_RE = re.compile(r"^[12]\d{9}$")

INVALID_NATIONAL_ID_MESSAGE = "رقم الهوية/الإقامة غير صحيح. يجب أن يكون 10 أرقام ويبدأ بـ 1 أو 2."


def normalize_national_id(raw: str) -> str:
    """يحول أي صيغة إدخال إلى 10 أرقام لاتينية أو يرفع ValidationError."""
    if not isinstance(raw, str):
        raise ValidationError(INVALID_NATIONAL_ID_MESSAGE, code="invalid_national_id")
    value = _STRIP_CHARS.sub("", raw.strip()).translate(_ARABIC_DIGITS)
    if not NATIONAL_ID_RE.match(value):
        raise ValidationError(INVALID_NATIONAL_ID_MESSAGE, code="invalid_national_id")
    return value


@lru_cache(maxsize=1)
def _fernet() -> MultiFernet:
    keys = settings.FIELD_ENCRYPTION_KEYS
    return MultiFernet([Fernet(key) for key in keys])


def encrypt_national_id(normalized: str) -> str:
    return _fernet().encrypt(normalized.encode()).decode()


def decrypt_national_id(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:  # مفتاح خاطئ/بيانات تالفة — لا نفاصيل للمستخدم
        raise ValidationError("تعذر قراءة رقم الهوية المخزن.", code="decrypt_failed") from exc


def national_id_lookup_hash(normalized: str) -> str:
    key = settings.NATIONAL_ID_HMAC_KEY.encode()
    return hmac.new(key, normalized.encode(), hashlib.sha256).hexdigest()


def mask_national_id(normalized: str) -> str:
    """`******1234` — آخر 4 أرقام فقط."""
    if len(normalized) < 4:
        return "****"
    return f"******{normalized[-4:]}"
