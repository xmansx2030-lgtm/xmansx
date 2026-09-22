"""Health & Readiness.

- health: هل العملية تعمل؟ (بلا أي فحص خارجي)
- readiness: هل التطبيق جاهز؟ (PostgreSQL + Redis بمهلة قصيرة)

لا تكشف هذه النقاط أي credentials أو عناوين داخلية أو تفاصيل استثناءات.
"""

import logging

import redis
from django.conf import settings
from django.db import connection
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from common.redis_services import unique_redis_urls

logger = logging.getLogger("xmansx.health")


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request: Request) -> Response:
    return Response({"status": "ok"})


def _check_database() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
            if settings.DATABASE_RLS_ENFORCED:
                cursor.execute(
                    "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
                )
                privileged = cursor.fetchone()
                cursor.execute(
                    "SELECT COUNT(*) "
                    "FROM pg_class AS table_info "
                    "JOIN pg_namespace AS namespace "
                    "ON namespace.oid = table_info.relnamespace "
                    "WHERE namespace.nspname = current_schema() "
                    "AND table_info.relkind = 'r' "
                    "AND table_info.relrowsecurity "
                    "AND table_info.relforcerowsecurity"
                )
                policy_count = cursor.fetchone()[0]
                if privileged is None or any(privileged) or policy_count < 59:
                    logger.error("readiness_tenant_isolation_failed")
                    return False
        return True
    except Exception:
        logger.error("readiness_database_failed")
        return False


def _check_redis() -> bool:
    timeout = settings.READINESS_CHECK_TIMEOUT_SECONDS
    try:
        for url in unique_redis_urls():
            client = redis.Redis.from_url(
                url,
                socket_connect_timeout=timeout,
                socket_timeout=timeout,
            )
            try:
                if not client.ping():
                    return False
            finally:
                client.close()
        return True
    except Exception:
        logger.error("readiness_redis_failed")
        return False


@api_view(["GET"])
@permission_classes([AllowAny])
def readiness(request: Request) -> Response:
    checks = {
        "database": "ok" if _check_database() else "error",
        "redis": "ok" if _check_redis() else "error",
    }
    ready = all(value == "ok" for value in checks.values())
    return Response(
        {"status": "ready" if ready else "not_ready", "checks": checks},
        status=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
