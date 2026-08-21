from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

BEAT_HEARTBEAT_CACHE_KEY = "operations:beat-heartbeat"
WORKER_HEARTBEAT_CACHE_KEY = "operations:worker-heartbeat"


@shared_task(name="operations.system_heartbeat", ignore_result=True)
def system_heartbeat() -> str:
    timestamp = timezone.now().isoformat()
    timeout = 10 * 60
    cache.set(BEAT_HEARTBEAT_CACHE_KEY, timestamp, timeout=timeout)
    cache.set(WORKER_HEARTBEAT_CACHE_KEY, timestamp, timeout=timeout)
    return timestamp


@shared_task(name="operations.scheduled_database_backup", ignore_result=True)
def scheduled_database_backup() -> int:
    from operations.backups import create_database_backup

    return create_database_backup().id
