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
        return True
    except Exception:
        logger.exception("readiness: database check failed")
        return False


def _check_redis() -> bool:
    timeout = settings.READINESS_CHECK_TIMEOUT_SECONDS
    try:
        client = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
        )
        try:
            return bool(client.ping())
        finally:
            client.close()
    except Exception:
        logger.exception("readiness: redis check failed")
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
