from datetime import datetime, timedelta

import redis
from celery import current_app
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from common.health import _check_database, _check_redis
from common.redis_services import configured_redis_urls, unique_redis_urls
from devices.models import AttendanceDevice, DeviceBridgeInstallation
from operations.models import BackupRun, BackupStatus, BackupType
from operations.tasks import BEAT_HEARTBEAT_CACHE_KEY


def _age_seconds(value: str | datetime | None) -> float | None:
    if isinstance(value, str):
        value = parse_datetime(value)
    if value is None:
        return None
    return max((timezone.now() - value).total_seconds(), 0)


def check_worker() -> str:
    try:
        replies = current_app.control.inspect(timeout=1).ping() or {}
        return "ok" if replies else "unavailable"
    except Exception:
        return "unavailable"


def check_beat() -> tuple[str, float | None]:
    try:
        age = _age_seconds(cache.get(BEAT_HEARTBEAT_CACHE_KEY))
    except Exception:
        return "unavailable", None
    if age is None or age > settings.OPERATIONAL_HEARTBEAT_MAX_AGE_SECONDS:
        return "stale", age
    return "ok", age


def bridge_health() -> dict:
    now = timezone.now()
    stale_cutoff = now - timedelta(seconds=settings.BRIDGE_STALE_AFTER_SECONDS)
    offline_cutoff = now - timedelta(seconds=settings.BRIDGE_OFFLINE_AFTER_SECONDS)
    bridge_counts = DeviceBridgeInstallation.objects.aggregate(
        total=Count("id"),
        online=Count("id", filter=Q(last_seen_at__gte=stale_cutoff)),
        stale=Count(
            "id", filter=Q(last_seen_at__lt=stale_cutoff, last_seen_at__gte=offline_cutoff)
        ),
        offline=Count("id", filter=Q(last_seen_at__lt=offline_cutoff) | Q(last_seen_at=None)),
    )
    device_counts = AttendanceDevice.objects.filter(is_active=True).aggregate(
        total=Count("id"),
        online=Count("id", filter=Q(last_seen_at__gte=stale_cutoff)),
        stale=Count(
            "id", filter=Q(last_seen_at__lt=stale_cutoff, last_seen_at__gte=offline_cutoff)
        ),
        offline=Count("id", filter=Q(last_seen_at__lt=offline_cutoff) | Q(last_seen_at=None)),
    )
    return {"bridges": bridge_counts, "devices": device_counts}


def latest_backup() -> dict:
    latest = BackupRun.objects.filter(backup_type=BackupType.DATABASE).first()
    successful = (
        BackupRun.objects.filter(backup_type=BackupType.DATABASE, status=BackupStatus.SUCCEEDED)
        .order_by("-finished_at")
        .first()
    )
    age = _age_seconds(successful.finished_at if successful else None)
    if latest and latest.status == BackupStatus.FAILED:
        health = "failed"
    elif age is None:
        health = "missing"
    elif age > settings.BACKUP_MAX_AGE_SECONDS:
        health = "stale"
    else:
        health = "ok"
    return {
        "health": health,
        "latest_status": latest.status.lower() if latest else "never",
        "last_success_at": successful.finished_at if successful else None,
        "age_seconds": age,
    }


def database_resource_usage() -> dict | None:
    """Return low-cardinality connection pressure data for platform operators.

    The query is deliberately aggregate-only: it exposes no user, SQL, or
    tenant data and runs only when the protected operations endpoint is read.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*)::integer,
                    COUNT(*) FILTER (WHERE state = 'active')::integer,
                    COUNT(*) FILTER (
                        WHERE state = 'active' AND wait_event_type IS NOT NULL
                    )::integer
                FROM pg_stat_activity
                WHERE datname = current_database()
                """
            )
            total, active, waiting = cursor.fetchone()
    except Exception:
        return None
    return {"connections": total, "active_connections": active, "waiting_connections": waiting}


def redis_resource_usage() -> dict | None:
    """Return aggregate pressure across distinct Redis roles without secrets."""
    clients = []
    try:
        totals = {
            "used_memory_bytes": 0,
            "used_memory_peak_bytes": 0,
            "maxmemory_bytes": 0,
            "connected_clients": 0,
            "blocked_clients": 0,
        }
        for url in unique_redis_urls():
            client = redis.Redis.from_url(
                url,
                socket_connect_timeout=settings.READINESS_CHECK_TIMEOUT_SECONDS,
                socket_timeout=settings.READINESS_CHECK_TIMEOUT_SECONDS,
            )
            clients.append(client)
            memory = client.info("memory")
            client_info = client.info("clients")
            totals["used_memory_bytes"] += int(memory.get("used_memory", 0))
            totals["used_memory_peak_bytes"] += int(memory.get("used_memory_peak", 0))
            totals["maxmemory_bytes"] += int(memory.get("maxmemory", 0))
            totals["connected_clients"] += int(client_info.get("connected_clients", 0))
            totals["blocked_clients"] += int(client_info.get("blocked_clients", 0))

        broker = redis.Redis.from_url(
            configured_redis_urls()["celery_broker"],
            socket_connect_timeout=settings.READINESS_CHECK_TIMEOUT_SECONDS,
            socket_timeout=settings.READINESS_CHECK_TIMEOUT_SECONDS,
        )
        clients.append(broker)
        queues = {
            queue: int(broker.llen(queue))
            for queue in ("celery", "imports", "maintenance")
        }
    except Exception:
        return None
    finally:
        for client in clients:
            client.close()
    return {**totals, "queue_depths": queues}


def operational_snapshot() -> dict:
    database = "ok" if _check_database() else "unavailable"
    redis = "ok" if _check_redis() else "unavailable"
    worker = check_worker() if redis == "ok" else "unavailable"
    beat, beat_age = check_beat() if redis == "ok" else ("unavailable", None)
    try:
        bridges = bridge_health() if database == "ok" else None
        backup = latest_backup() if database == "ok" else None
    except Exception:
        bridges = None
        backup = None
    return {
        "backend": "ok",
        "database": database,
        "redis": redis,
        "worker": worker,
        "beat": beat,
        "beat_heartbeat_age_seconds": round(beat_age, 1) if beat_age is not None else None,
        "backup": backup,
        "bridge": bridges,
        "storage_integrity": cache.get("operations:storage-integrity") if redis == "ok" else None,
        "resources": {
            "postgres": database_resource_usage() if database == "ok" else None,
            "redis": redis_resource_usage() if redis == "ok" else None,
        },
    }
