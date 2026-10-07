"""Preview binding and read-only recovery across period boundaries."""

from datetime import timedelta

import pytest

from academics.models import BellPeriod
from attendance.models import AttendanceSession
from attendance.services.periods import school_now
from audit.models import AuditAction, AuditLog
from tests.attendance_helpers import setup_attendance_env

START = "/api/v1/attendance/sessions/start/"
PENDING = "/api/v1/attendance/sessions/pending/"


@pytest.fixture
def env(role_client):
    client, school, user = role_client(["TEACHER"])
    return {**setup_attendance_env(school), "client": client, "school": school, "user": user}


def start(env, **extra):
    return env["client"].post(
        START, {"section_id": env["section"].id, **extra}, content_type="application/json",
    )


@pytest.mark.django_db
@pytest.mark.parametrize("change", ["period", "date", "ended"])
def test_stale_preview_never_creates_a_session_or_audit(env, monkeypatch, change):
    preview = env["client"].get(
        f"/api/v1/attendance/sections/{env['section'].id}/preview/"
    ).json()
    period = env["period"]
    local_date = school_now(env["school"]).date()
    if change == "period":
        period = BellPeriod.objects.create(
            school=env["school"], bell_schedule=env["schedule"], sequence=4,
            name="الحصة التالية", start_time=period.start_time, end_time=period.end_time,
        )
    elif change == "date":
        local_date += timedelta(days=1)
    else:
        period = None
    monkeypatch.setattr(
        "attendance.services.sessions.get_current_attendance_period",
        lambda school: (period, local_date),
    )
    response = start(env, expected_date=preview["attendance_date"],
                     expected_period_sequence=preview["period"]["sequence"])
    assert response.status_code == 409
    assert response.json()["code"] == "ATTENDANCE_PERIOD_CHANGED"
    assert not AttendanceSession.objects.filter(school=env["school"]).exists()
    assert not AuditLog.objects.filter(action=AuditAction.ATTENDANCE_STARTED).exists()


@pytest.mark.django_db
def test_matching_preview_starts_and_resumes_the_same_session(env):
    preview = env["client"].get(
        f"/api/v1/attendance/sections/{env['section'].id}/preview/"
    ).json()
    target = {"expected_date": preview["attendance_date"],
              "expected_period_sequence": preview["period"]["sequence"]}
    first, second = start(env, **target), start(env, **target)
    assert [first.status_code, second.status_code] == [201, 200]
    assert first.json()["id"] == second.json()["id"]
    assert AuditLog.objects.filter(action=AuditAction.ATTENDANCE_STARTED).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("extra", [
    {"expected_date": "2026-10-07"}, {"expected_period_sequence": 1},
    {"expected_date": "bad", "expected_period_sequence": 1},
    {"expected_date": "2026-10-07", "expected_period_sequence": 0},
])
def test_preview_expectations_are_validated_together(env, extra):
    assert start(env, **extra).status_code == 400
    assert not AttendanceSession.objects.exists()


@pytest.mark.django_db
def test_pending_sessions_are_read_only_and_scoped_to_teacher_school_and_day(env, role_client):
    session_id = start(env).json()["id"]
    session = AttendanceSession.objects.get(pk=session_id)
    AttendanceSession.objects.create(
        school=session.school, academic_year=session.academic_year, section=session.section,
        attendance_date=session.attendance_date - timedelta(days=1), period_sequence=3,
        bell_period_snapshot=session.bell_period_snapshot,
        started_by_membership=session.started_by_membership,
        unprepared_alert_minutes_snapshot=session.unprepared_alert_minutes_snapshot,
    )
    other_teacher, _, _ = role_client(["TEACHER"], school=env["school"])
    other_school_teacher, _, _ = role_client(["TEACHER"])
    before = AuditLog.objects.count()
    response = env["client"].get(PENDING)
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [session_id]
    assert "roster" not in response.json()[0]
    assert other_teacher.get(PENDING).json() == []
    assert other_school_teacher.get(PENDING).json() == []
    assert other_school_teacher.get(f"/api/v1/attendance/sessions/{session_id}/").status_code == 404
    assert AuditLog.objects.count() == before


@pytest.mark.django_db
def test_pending_session_can_be_resumed_and_submitted_after_period_ends(env, monkeypatch):
    session_id = start(env).json()["id"]
    local_date = school_now(env["school"]).date()
    monkeypatch.setattr(
        "attendance.api.views.get_current_attendance_period", lambda school: (None, local_date)
    )
    assert env["client"].get(
        f"/api/v1/attendance/sections/{env['section'].id}/preview/"
    ).status_code == 409
    assert [row["id"] for row in env["client"].get(PENDING).json()] == [session_id]
    resumed = env["client"].get(f"/api/v1/attendance/sessions/{session_id}/").json()
    assert resumed["period"]["sequence"] == 3
    response = env["client"].post(
        f"/api/v1/attendance/sessions/{session_id}/submit/",
        {"marks": [{"student_id": env["students"][0].id, "status": "ABSENT"}]},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["period"]["sequence"] == 3
    assert response.json()["status"] == "SUBMITTED"
    assert env["client"].get(PENDING).json() == []
    assert AuditLog.objects.filter(action=AuditAction.ATTENDANCE_SUBMITTED).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["COUNSELOR", "SCHOOL_MANAGER", "VICE_PRINCIPAL"])
def test_pending_teacher_sessions_require_teacher_role(role_client, role):
    client, _, _ = role_client([role])
    assert client.get(PENDING).status_code == 403
