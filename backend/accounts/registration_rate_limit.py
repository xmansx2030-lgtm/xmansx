"""تحديد محاولات تسجيل المدارس ذاتيًا حسب عنوان الشبكة ورقم الجوال."""

import hashlib

from django.conf import settings
from django.core.cache import caches

from common.errors import ApiError

cache = caches["security"]
RATE_LIMITED_MESSAGE = "تجاوزت محاولات التسجيل الحد المسموح. حاول لاحقًا أو تواصل مع الدعم."


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def _key(kind: str, value: str) -> str:
    return f"self-registration:{kind}:{_digest(value)}"


def _count(key: str) -> int:
    return int(cache.get(key) or 0)


def _increment(key: str, window_seconds: int) -> None:
    if cache.add(key, 1, timeout=window_seconds):
        return
    try:
        cache.incr(key)
    except ValueError:
        cache.add(key, 1, timeout=window_seconds)


def precheck(ip: str, mobile: str) -> None:
    ip_limit, _ = settings.SELF_REGISTRATION_RATE_LIMIT_IP
    mobile_limit, _ = settings.SELF_REGISTRATION_RATE_LIMIT_MOBILE
    if _count(_key("ip", ip)) >= ip_limit or _count(_key("mobile", mobile)) >= mobile_limit:
        raise ApiError("SELF_REGISTRATION_RATE_LIMITED", RATE_LIMITED_MESSAGE, status_code=429)


def register_attempt(ip: str, mobile: str) -> None:
    _, ip_window = settings.SELF_REGISTRATION_RATE_LIMIT_IP
    _, mobile_window = settings.SELF_REGISTRATION_RATE_LIMIT_MOBILE
    _increment(_key("ip", ip), ip_window)
    _increment(_key("mobile", mobile), mobile_window)
