from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
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

    run = create_database_backup()
    if settings.BACKUP_REMOTE_ENABLED and settings.BACKUP_KEEP_LATEST_ONLY:
        call_command("cleanup_backups", "--dry-run", "--latest-only")
        call_command("cleanup_backups", "--apply", "--latest-only")
    return run.id
