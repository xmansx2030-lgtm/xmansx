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
import uuid
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from threading import Lock

from django.conf import settings
from django.core.cache import cache
from redis.exceptions import RedisError

from common.cache import delete_if_value
from common.errors import ApiError

#: آجال قصيرة: التشغيل اليومي يتغير كل لحظة، والتاريخ أبطأ تغيرًا
TTL_TODAY = 15
TTL_OVERVIEW = 45
TTL_TREND = 180

# Keep a recently expired response briefly so a burst at a TTL boundary does
# not send every polling client to PostgreSQL. Fresh values are always used
# when available; stale data is returned only while one request revalidates.
STALE_GRACE_SECONDS = 30
INITIAL_FILL_WAIT_STEP_SECONDS = 0.05
_flight_lock = Lock()
_flights: dict[str, Future] = {}
_MAX_FLIGHTS = 256

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
    """Share cold fills locally and across replicas; never stampede on timeout."""
    if ttl <= 0:
        return builder()
    hit = cache.get(key)
    if hit is not None:
        return hit

    with _flight_lock:
        flight = _flights.get(key)
        owner = flight is None
        if owner:
            if len(_flights) >= _MAX_FLIGHTS:
                raise _busy()
            flight = _flights[key] = Future()
    if not owner:
        stale = cache.get(f"{key}:stale")
        if stale is not None:
            return stale
        try:
            return flight.result(timeout=settings.DASHBOARD_CACHE_WAIT_SECONDS)
        except FutureTimeout as exc:
            raise _busy() from exc
    try:
        value = _fill(key=key, ttl=ttl, builder=builder, stale_grace=stale_grace_seconds)
        flight.set_result(value)
        return value
    except BaseException as exc:
        flight.set_exception(exc)
        raise
    finally:
        with _flight_lock:
            _flights.pop(key, None)


def _busy():
    error = ApiError(
        "DATA_REFRESH_BUSY", "جاري تحديث البيانات، حاول بعد قليل.", status_code=503
    )
    error.wait = 2
    return error


def _cache_available():
    check = getattr(cache, "is_available", None)
    return check is None or check()


def _release(key, token):
    try:
        release = getattr(cache, "delete_if_value", None)
        if release is not None:
            release(key, token)
        elif hasattr(cache, "_cache"):
            delete_if_value(cache, key, token)
        # Other backends leave the bounded lease to expire; never compare/delete
        # non-atomically, which could delete a successor's lock.
    except (RedisError, OSError, TimeoutError):
        pass


def _fill(*, key, ttl, builder, stale_grace):
    hit = cache.get(key)
    if hit is not None:
        return hit

    stale_key = f"{key}:stale"
    stale = cache.get(stale_key)
    lock_key = f"{key}:refresh-lock"
    token = uuid.uuid4().hex
    deadline = time.monotonic() + settings.DASHBOARD_CACHE_WAIT_SECONDS
    while True:
        acquired = cache.add(lock_key, token, timeout=settings.DASHBOARD_CACHE_LEASE_SECONDS)
        if acquired or not _cache_available():
            try:
                value = builder()
                cache.set(key, value, timeout=ttl)
                cache.set(stale_key, value, timeout=ttl + stale_grace)
                return value
            finally:
                if acquired:
                    _release(lock_key, token)
        if stale is not None:
            return stale
        if time.monotonic() >= deadline:
            raise _busy()
        time.sleep(INITIAL_FILL_WAIT_STEP_SECONDS)
        hit = cache.get(key)
        if hit is not None:
            return hit


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
