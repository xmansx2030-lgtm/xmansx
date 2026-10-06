"""Excuse eligibility follows student evidence, regardless of overlapping years."""

from datetime import datetime, timedelta

import pytest

from academics.models import AcademicYear, AcademicYearStatus
from attendance.models import AttendanceMark, DailyAttendanceSummary
from attendance.services.day_context import get_or_create_attendance_day_context
from audit.models import AuditAction, AuditLog
from excuses.models import AbsenceExcuseCoverage
from tests.excuse_env import TZ
from tests.test_excuses import DAY, PERIOD_COUNT, full_day_absent
from tests.test_excuses_api import _build_env, _create_excuse


@pytest.fixture
def api_env(role_client, make_user, make_membership):
    client, school, user = role_client(["VICE_PRINCIPAL"])
    env = _build_env(school, make_user, make_membership)
    env.update(client=client, vice=user.memberships.get(school=school))
    return env


def overlapping_year_for_student(env, student, other_status):
    # The unrelated year existed first. Database row order must not decide
    # whether a student with a valid enrollment can have an excuse recorded.
    other = env["year"]
    other.status = other_status
    other.save(update_fields=["status"])
    actual = AcademicYear.objects.create(
        school=env["school"],
        name="عام القيد الفعلي",
        start_date=other.start_date,
        end_date=other.end_date,
        status=AcademicYearStatus.ACTIVE,
    )
    student.enrollments.update(academic_year=actual)
    env["year"] = actual
    return other, actual


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["SCHOOL_MANAGER", "VICE_PRINCIPAL"])
@pytest.mark.parametrize("other_status", ["UPCOMING", "CLOSED", "ARCHIVED"])
def test_overlapping_year_does_not_hide_student_enrollment(
    api_env, role_client, role, other_status
):
    student = api_env["students"][0]
    overlapping_year_for_student(api_env, student, other_status)
    client, _, user = role_client([role], school=api_env["school"])
    sessions = full_day_absent(api_env, student)
    created = _create_excuse(client, student)
    assert created.status_code == 201, created.content
    assert created.json()["status"] == "APPROVED"
    assert created.json()["active_coverage_count"] == PERIOD_COUNT
    summary = DailyAttendanceSummary.objects.get(student=student, attendance_date=DAY)
    assert summary.absence_status == "FULL"
    assert summary.excused_absent_periods == PERIOD_COUNT
    assert summary.unexcused_absent_periods == 0
    assert (
        AttendanceMark.objects.filter(session__in=sessions, status="ABSENT").count() == PERIOD_COUNT
    )
    assert AuditLog.objects.filter(action=AuditAction.EXCUSE_CREATED, actor=user).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["SCHOOL_MANAGER", "VICE_PRINCIPAL"])
def test_overlapping_year_accepts_recorded_absence_before_import(api_env, role_client, role):
    student = api_env["students"][0]
    overlapping_year_for_student(api_env, student, "CLOSED")
    student.enrollments.update(enrolled_at=DAY + timedelta(days=1))
    full_day_absent(api_env, student)
    client, _, _ = role_client([role], school=api_env["school"])
    created = _create_excuse(client, student)
    assert created.status_code == 201, created.content
    assert created.json()["active_coverage_count"] == PERIOD_COUNT


@pytest.mark.django_db
def test_period_excuse_uses_student_history_when_context_belongs_to_other_year(api_env):
    student = api_env["students"][0]
    other, actual = overlapping_year_for_student(api_env, student, "CLOSED")
    full_day_absent(api_env, student)
    context = get_or_create_attendance_day_context(school=api_env["school"], attendance_date=DAY)
    # A stale context from another year cannot authorize its fictitious period.
    context.academic_year = other
    context.schedule_snapshot = {"periods": [{"sequence": 29, "is_attendance_period": True}]}
    context.save(update_fields=["academic_year", "schedule_snapshot"])
    actual.status = "CLOSED"
    actual.save(update_fields=["status"])
    other.status = "ACTIVE"
    other.save(update_fields=["status"])
    created = _create_excuse(
        api_env["client"],
        student,
        targets=[{"attendance_date": DAY.isoformat(), "period_sequence": 1}],
    )
    assert created.status_code == 201, created.content
    assert created.json()["active_coverage_count"] == 1
    invalid = _create_excuse(
        api_env["client"],
        student,
        targets=[{"attendance_date": DAY.isoformat(), "period_sequence": 29}],
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "EXCUSE_INVALID_TARGET"


@pytest.mark.django_db
@pytest.mark.parametrize("boundary", ["BEFORE_START", "ON_END"])
def test_overlapping_year_does_not_bypass_enrollment_dates(api_env, boundary):
    student = api_env["students"][0]
    overlapping_year_for_student(api_env, student, "UPCOMING")
    if boundary == "BEFORE_START":
        student.enrollments.update(enrolled_at=DAY + timedelta(days=1))
    else:
        student.enrollments.update(ended_at=DAY)
    created = _create_excuse(api_env["client"], student)
    assert created.status_code == 400
    assert created.json()["code"] == "EXCUSE_STUDENT_NOT_ENROLLED_ON_DATE"
    assert not AbsenceExcuseCoverage.objects.exists()


@pytest.mark.django_db
def test_future_recorded_absence_does_not_bypass_missing_enrollment(api_env, monkeypatch):
    monkeypatch.setattr(
        "excuses.services.excuses.school_now", lambda _: datetime(2026, 8, 19, 9, tzinfo=TZ)
    )
    student = api_env["students"][0]
    overlapping_year_for_student(api_env, student, "CLOSED")
    future_day = DAY + timedelta(days=7)
    student.enrollments.update(enrolled_at=future_day + timedelta(days=1))
    full_day_absent(api_env, student, day=future_day)
    created = _create_excuse(
        api_env["client"], student, targets=[{"attendance_date": future_day.isoformat()}]
    )
    assert created.status_code == 400
    assert created.json()["code"] == "EXCUSE_STUDENT_NOT_ENROLLED_ON_DATE"
