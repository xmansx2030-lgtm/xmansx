"""Celery Beat app that publishes scheduled tasks without loading Django.

The worker still uses config.celery and imports the application tasks. Beat only
needs their names and broker routing; loading Django in both processes kept a
second full application copy in memory on the 512 MiB Render service.
"""

from __future__ import annotations

import os

from celery import Celery

from beat_schedule import build_beat_schedule


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return value.strip().lower() in {"1", "true", "yes", "on"} if value else default


broker_url = os.environ.get("CELERY_BROKER_URL") or os.environ.get("REDIS_URL")
if not broker_url:
    raise RuntimeError("CELERY_BROKER_URL or REDIS_URL is required for Celery Beat")

# Celery's default Django fixup imports the entire project whenever
# DJANGO_SETTINGS_MODULE is present, even if Beat only publishes task names.
app = Celery("xmansx", broker=broker_url, fixups=[])
backup_enabled = _env_bool("BACKUP_SCHEDULE_ENABLED", False)
app.conf.update(
    timezone="Asia/Riyadh",
    beat_schedule=build_beat_schedule(
        heartbeat_interval_seconds=_env_int("OPERATIONAL_HEARTBEAT_INTERVAL_SECONDS", 120),
        backup_enabled=backup_enabled,
        backup_interval_seconds=(
            _env_int("BACKUP_SCHEDULE_INTERVAL_SECONDS", 24 * 60 * 60)
            if backup_enabled
            else 24 * 60 * 60
        ),
    ),
    task_routes={
        "operations.scheduled_database_backup": {"queue": "maintenance"},
    },
)
