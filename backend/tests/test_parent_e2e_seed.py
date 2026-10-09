import json
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.db import connection

from attendance.models import AttendanceSession
from attendance.services.admin_preparation import resolve_today_period
from common.errors import ApiError
from common.tenant_rls import tenant_context
from schools.models import School


@pytest.mark.django_db
def test_parent_seed_before_second_period_starts_keeps_real_time_guard(settings, tmp_path):
    settings.DEBUG = True
    connection.ensure_connection()
    output = tmp_path / "parent-fixture.json"
    midnight = datetime(2026, 10, 10, 0, 5, tzinfo=ZoneInfo("Asia/Riyadh"))
    # The command requires an explicitly local database; the test connection is
    # already open and remains the isolated pytest database.
    with patch.dict(settings.DATABASES["default"], {"HOST": "localhost"}):
        with patch("django.utils.timezone.now", return_value=midnight):
            call_command("seed_parent_e2e", password="synthetic-seed-test-only", output=str(output))
            fixture = json.loads(output.read_text(encoding="utf-8"))
            school = School.objects.get(id=fixture["schools"][0]["id"])
            with tenant_context(school_id=school.id):
                assert AttendanceSession.objects.filter(
                    school=school, attendance_date=midnight.date(), period_sequence=2,
                    status="SUBMITTED",
                ).exists()
                with pytest.raises(ApiError) as failure:
                    resolve_today_period(
                        school=school, attendance_date=midnight.date(), period_sequence=2,
                    )
                assert failure.value.code == "ATTENDANCE_PERIOD_NOT_STARTED"
