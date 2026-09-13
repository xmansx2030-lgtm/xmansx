import logging
import time
from threading import Lock

from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.redis import RedisCache
from redis.exceptions import RedisError

logger = logging.getLogger("xmansx.cache")

_FAILURE_LOG_INTERVAL_SECONDS = 60
_failure_log_lock = Lock()
_last_failure_log_at = 0.0


def _log_cache_unavailable() -> None:
    """Emit one outage warning per process per interval, not per cache call."""
    global _last_failure_log_at
    now = time.monotonic()
    with _failure_log_lock:
        if now - _last_failure_log_at < _FAILURE_LOG_INTERVAL_SECONDS:
            return
        _last_failure_log_at = now
    logger.warning("performance_cache_unavailable")


class ResilientRedisCache(RedisCache):
    """Fail open for performance caches while readiness still reports Redis outages."""

    def _fallback(self, operation, default, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except (RedisError, OSError, TimeoutError):
            _log_cache_unavailable()
            return default

    def get(self, key, default=None, version=None):
        return self._fallback(super().get, default, key, default, version)

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        return self._fallback(super().set, False, key, value, timeout, version)

    def add(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        return self._fallback(super().add, False, key, value, timeout, version)

    def delete(self, key, version=None):
        return self._fallback(super().delete, False, key, version)

    def get_many(self, keys, version=None):
        return self._fallback(super().get_many, {}, keys, version)

    def set_many(self, data, timeout=DEFAULT_TIMEOUT, version=None):
        return self._fallback(super().set_many, [], data, timeout, version)

    def delete_many(self, keys, version=None):
        return self._fallback(super().delete_many, False, keys, version)

    def clear(self):
        return self._fallback(super().clear, False)
