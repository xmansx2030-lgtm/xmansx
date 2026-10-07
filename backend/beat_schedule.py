"""Periodic task definitions shared by Django and the lightweight scheduler."""

from __future__ import annotations


def build_beat_schedule(
    *,
    heartbeat_interval_seconds: int,
    backup_enabled: bool,
    backup_interval_seconds: int,
    ministry_calendar_enabled: bool = True,
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
    if ministry_calendar_enabled:
        schedule["sync-ministry-calendar"] = {
            "task": "academics.sync_ministry_calendar",
            "schedule": 6 * 60 * 60,
            "options": {"expires": 60 * 60},
        }
        schedule["activate-ministry-calendars"] = {
            "task": "academics.apply_ministry_calendars",
            "schedule": 5 * 60,
            "options": {"expires": 4 * 60},
        }
    return schedule
