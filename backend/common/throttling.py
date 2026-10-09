"""Atomic account limits shared by replicas, independent of a school's NAT IP."""

from django.conf import settings
from django.core.cache import caches
from redis.exceptions import RedisError
from rest_framework.throttling import BaseThrottle

_COUNTER = """
local now = redis.call('TIME')
local seconds = tonumber(now[1])
local key = KEYS[1] .. ':' .. math.floor(seconds / 60)
local count = redis.call('INCR', key)
if count == 1 then redis.call('EXPIRE', key, 61 - (seconds % 60)) end
return {count, 60 - (seconds % 60)}
"""


class AccountPressureThrottle(BaseThrottle):
    """Keep runaway sessions/exports bounded without blocking a shared school IP.

    Public login/registration retain their stricter existing limits. Health and
    readiness explicitly opt out so Redis failure remains observable. This
    guard uses only the security Redis and never falls back to a database counter.
    """

    def allow_request(self, request, view):
        self.retry_after = 0
        path = request.path.rstrip("/")
        # Always let an authenticated person clear the session, including while
        # the security store is unavailable or the account budget is exhausted.
        if path in {"/api/v1/auth/logout", "/api/v1/auth/csrf"}:
            return True
        if not settings.API_RATE_LIMIT_ENABLED or not request.user.is_authenticated:
            return True
        limits = [("requests", settings.API_USER_REQUESTS_PER_MINUTE)]
        if path.startswith("/api/v1/reports/") and (
            path.endswith("/export.xlsx") or request.query_params.get("_export_all") == "1"
        ):
            limits.append(("exports", settings.API_USER_EXPORTS_PER_MINUTE))
        backend = caches["security"]
        try:
            for kind, limit in limits:
                key = backend.make_and_validate_key(f"pressure:{kind}:user:{request.user.pk}")
                client = backend._cache.get_client(key, write=True)
                count, remaining = client.eval(_COUNTER, 1, key)
                if count > limit:
                    self.retry_after = remaining
                    return False
        except (RedisError, OSError, TimeoutError) as exc:
            from common.errors import ApiError

            error = ApiError(
                "SERVICE_TEMPORARILY_UNAVAILABLE",
                "الخدمة غير متاحة مؤقتاً، حاول بعد قليل.",
                status_code=503,
            )
            error.wait = 2
            raise error from exc
        return True

    def wait(self):
        return self.retry_after
