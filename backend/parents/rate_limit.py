"""Bounded, atomic Redis counters without storing raw account/token values."""

from django.core.cache import caches

from common.errors import ApiError
from parents.security import token_hash


def consume(*, kind: str, value: str, limit: int, seconds: int = 3600):
    cache = caches["security"]
    key = f"parent:{kind}:{token_hash(value)}"
    try:
        if cache.add(key, 1, timeout=seconds):
            count = 1
        else:
            try:
                count = cache.incr(key)
            except ValueError:
                # A second request may have recreated an expired key first.
                # Count that request atomically instead of silently resetting it.
                count = 1 if cache.add(key, 1, timeout=seconds) else cache.incr(key)
    except Exception as exc:
        raise ApiError(
            "REGISTRATION_UNAVAILABLE", "الخدمة غير متاحة مؤقتاً.", status_code=503
        ) from exc
    if count > limit:
        raise ApiError("RATE_LIMITED", "تجاوزت الحد المسموح. حاول لاحقاً.", status_code=429)
