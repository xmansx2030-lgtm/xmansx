"""Rate limiting لتسجيل الدخول — حماية مزدوجة (IP + جوال) عبر Redis cache.

السياسة (قابلة للضبط من settings):
- لكل IP: حد أعلى لكل المحاولات داخل النافذة (ضد الرش الواسع).
- لكل جوال: حد أعلى للمحاولات الفاشلة داخل النافذة (ضد استهداف حساب)،
  ويصفر عند النجاح — لا lockout دائم يمكن استغلاله ضد المستخدم.
"""

import hashlib

from django.conf import settings
from django.core.cache import cache

from common.errors import ApiError

RATE_LIMITED_MESSAGE = "عدد المحاولات تجاوز الحد المسموح، حاول بعد قليل."


def _mobile_key(mobile: str) -> str:
    digest = hashlib.sha256(mobile.encode()).hexdigest()[:32]
    return f"login:mobile:{digest}"


def _ip_key(ip: str) -> str:
    return f"login:ip:{ip}"


def _count(key: str) -> int:
    return int(cache.get(key) or 0)


def _increment(key: str, window_seconds: int) -> None:
    if cache.add(key, 1, timeout=window_seconds):
        return
    try:
        cache.incr(key)
    except ValueError:  # انتهت صلاحية المفتاح بين add وincr
        cache.add(key, 1, timeout=window_seconds)


def precheck(ip: str, mobile: str) -> None:
    """يرفع 429 إذا تجاوز IP أو الجوال الحد — قبل أي authenticate."""
    ip_limit, _ = settings.LOGIN_RATE_LIMIT_IP
    mobile_limit, _ = settings.LOGIN_RATE_LIMIT_MOBILE
    if _count(_ip_key(ip)) >= ip_limit or _count(_mobile_key(mobile)) >= mobile_limit:
        raise ApiError("LOGIN_RATE_LIMITED", RATE_LIMITED_MESSAGE, status_code=429)


def register_attempt(ip: str) -> None:
    """كل محاولة دخول تحسب على الـ IP (نجحت أم فشلت)."""
    _, window = settings.LOGIN_RATE_LIMIT_IP
    _increment(_ip_key(ip), window)


def register_failure(mobile: str) -> None:
    _, window = settings.LOGIN_RATE_LIMIT_MOBILE
    _increment(_mobile_key(mobile), window)


def register_success(mobile: str) -> None:
    cache.delete(_mobile_key(mobile))
