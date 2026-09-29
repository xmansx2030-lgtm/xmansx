"""The Render scheduler must stay small without changing periodic task delivery."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("backup_enabled", [False, True])
def test_lightweight_scheduler_does_not_load_django_or_change_routing(backup_enabled):
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "CELERY_BROKER_URL": "redis://localhost:6379/2",
        "BACKUP_SCHEDULE_ENABLED": str(backup_enabled).lower(),
        "OPERATIONAL_HEARTBEAT_INTERVAL_SECONDS": "121",
        "BACKUP_SCHEDULE_INTERVAL_SECONDS": "86401",
    }
    code = """
import json
import sys
from lightweight_beat import app

print(json.dumps({
    "loaded_settings": any(name.startswith("config.settings") for name in sys.modules),
    "loaded_tasks": "operations.tasks" in sys.modules,
    "schedule": app.conf.beat_schedule,
    "timezone": app.conf.timezone,
    "backup_queue": app.amqp.router.route({}, "operations.scheduled_database_backup")["queue"].name,
}))
"""
    result = subprocess.run(  # noqa: S603 - fixed interpreter and test program
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    data = json.loads(result.stdout)

    assert data["loaded_settings"] is False
    assert data["loaded_tasks"] is False
    assert data["timezone"] == "Asia/Riyadh"
    assert data["backup_queue"] == "maintenance"
    assert data["schedule"]["system-operational-heartbeat"] == {
        "task": "operations.system_heartbeat",
        "schedule": 121,
        "options": {"expires": 110},
    }
    if backup_enabled:
        assert data["schedule"]["scheduled-database-backup"] == {
            "task": "operations.scheduled_database_backup",
            "schedule": 86401,
            "options": {"expires": 3600},
        }
    else:
        assert "scheduled-database-backup" not in data["schedule"]
