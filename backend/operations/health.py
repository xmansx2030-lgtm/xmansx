from datetime import datetime, timedelta

from celery import current_app
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from common.health import _check_database, _check_redis
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
    }
