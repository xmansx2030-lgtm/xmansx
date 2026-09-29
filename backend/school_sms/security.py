"""تشفير اعتماد مزود الرسائل باستخدام مفاتيح الحقول الحالية ودعم تدويرها."""

import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings

from common.errors import ApiError


def _cipher() -> MultiFernet:
    return MultiFernet([Fernet(key) for key in settings.FIELD_ENCRYPTION_KEYS])


def encrypt_secret(value: str) -> str:
    return _cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    try:
        return _cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ApiError(
            "SMS_CREDENTIAL_UNAVAILABLE", "تعذر قراءة اعتماد مزود الرسائل. تواصل مع الدعم.",
            status_code=503,
        ) from exc


def recipient_hash(mobile: str) -> str:
    key = settings.NATIONAL_ID_HMAC_KEY.encode("utf-8")
    return hmac.new(key, f"sms-recipient:{mobile}".encode(), hashlib.sha256).hexdigest()
