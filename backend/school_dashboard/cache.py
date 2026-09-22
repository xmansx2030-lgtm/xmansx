"""تخزين مؤقت قصير للوحة الإدارة.

قاعدة أمنية أولى: **مفتاح الكاش يبدأ بمعرف المدرسة دائمًا** (بند 68/69/91).
لا يمكن لطلب مدرسة أن يقرأ نتيجة مدرسة أخرى ولو تطابقت بقية المعاملات، ولا
لدور أن يقرأ نتيجة دور آخر إن كان النطاق يعتمد الدور.

آجال قصيرة عمدًا بدل نظام إبطال معقد (بند 71) — وهذا أيضًا ما يمنع عودة بيانات
طالب محذوف نهائيًا من الكاش بعد الحذف (بند 135).
"""

import hashlib
import json
import time

from django.core.cache import cache

#: آجال قصيرة: التشغيل اليومي يتغير كل لحظة، والتاريخ أبطأ تغيرًا
TTL_TODAY = 15
TTL_OVERVIEW = 45
TTL_TREND = 180

# Keep a recently expired response briefly so a burst at a TTL boundary does
# not send every polling client to PostgreSQL. Fresh values are always used
# when available; stale data is returned only while one request revalidates.
STALE_GRACE_SECONDS = 30
LOCK_TTL_SECONDS = 10
INITIAL_FILL_WAIT_SECONDS = 1.0
INITIAL_FILL_WAIT_STEP_SECONDS = 0.05

_NAMESPACE = "dash"


def _version_key(school_id: int) -> str:
    return f"{_NAMESPACE}:{school_id}:version"


def build_key(*, school_id: int, section: str, parts: dict) -> str:
    """مفتاح مستقر: المدرسة أولًا ثم بصمة بقية المعاملات."""
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:20]
    version = cache.get(_version_key(school_id), 0)
    return f"{_NAMESPACE}:{school_id}:{section}:v{version}:{digest}"


def cached(
    *,
    key: str,
    ttl: int,
    builder,
    stale_grace_seconds: int = STALE_GRACE_SECONDS,
):
    """Return a fresh value, or briefly stale data while one request refreshes it.

    ``cache.add`` is atomic in Redis. Its short lease coalesces TTL-boundary
    misses without making a failed cache a correctness dependency: when Redis
    is unavailable the function still calls ``builder`` as before.
    """
    if ttl <= 0:
        return builder()
    hit = cache.get(key)
    if hit is not None:
        return hit

    stale_key = f"{key}:stale"
    stale = cache.get(stale_key)
    lock_key = f"{key}:refresh-lock"
    lock_timeout = min(max(ttl, 1), LOCK_TTL_SECONDS)

    if cache.add(lock_key, "1", timeout=lock_timeout):
        value = builder()
        cache.set(key, value, timeout=ttl)
        cache.set(stale_key, value, timeout=ttl + stale_grace_seconds)
        return value

    if stale is not None:
        return stale

    # A cold cache has no safe stale value. Let the lock owner fill it first;
    # if it is unavailable or slow, preserve availability with one fallback
    # build instead of returning an incomplete dashboard response.
    deadline = time.monotonic() + INITIAL_FILL_WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(INITIAL_FILL_WAIT_STEP_SECONDS)
        hit = cache.get(key)
        if hit is not None:
            return hit

    value = builder()
    cache.set(key, value, timeout=ttl)
    cache.set(stale_key, value, timeout=ttl + stale_grace_seconds)
    return value


def invalidate_school(school_id: int) -> None:
    """يبطل كاش المدرسة فورًا بعد أي تغيير تشغيلي مؤثر في اللوحة.

    تغيير النسخة يتجنب مسحًا عامًا غير مدعوم في كل محركات الكاش، ويبقي مفاتيح
    المدارس الأخرى سليمة. المفاتيح القديمة تنتهي تلقائيًا وفق آجالها القصيرة.
    """
    key = _version_key(school_id)
    if cache.add(key, 1, timeout=None):
        return
    try:
        cache.incr(key)
    except ValueError:
        # قد ينتهي المفتاح بين add وincr في محرك كاش خارجي؛ أعد إنشاءه بأمان.
        cache.set(key, 1, timeout=None)
