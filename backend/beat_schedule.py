"""Periodic task definitions shared by Django and the lightweight scheduler."""

from __future__ import annotations


def build_beat_schedule(
    *, heartbeat_interval_seconds: int, backup_enabled: bool, backup_interval_seconds: int
) -> dict[str, dict]:
    schedule = {
        "system-operational-heartbeat": {
            "task": "operations.system_heartbeat",
            "schedule": heartbeat_interval_seconds,
            "options": {"expires": 110},
        },
    }
    if backup_enabled:
        schedule["scheduled-database-backup"] = {
            "task": "operations.scheduled_database_backup",
            "schedule": backup_interval_seconds,
            "options": {"expires": 60 * 60},
        }
    return schedule
