"""Prepared academic years must not replace current or saved attendance rosters."""

from datetime import timedelta

import pytest
from django.utils import timezone

from academics.models import AcademicYear, AcademicYearStatus
from attendance.models import AttendanceDayContext, DailyAttendanceSummary
from students.models import EnrollmentStatus, Grade, Section, StudentEnrollment
from tests import test_parent_portal as journeys

portal_env = journeys.portal_env
pytestmark = pytest.mark.django_db


def _next_enrollment(env, *, enrolled_at, status=AcademicYearStatus.UPCOMING):
    year = AcademicYear.objects.create(
        school=env["school"],
        name="عام نور المحضر",
        start_date=enrolled_at,
        end_date=enrolled_at + timedelta(days=300),
        status=status,
    )
    grade = Grade.objects.create(
        school=env["school"],
        code="PREPARED",
        name="صف العام القادم",
        sequence=20,
    )
    section = Section.objects.create(
        school=env["school"],
        grade=grade,
        code="NEXT",
        name="فصل العام القادم",
        department="قسم العام القادم",
    )
    enrollment = StudentEnrollment.objects.create(
        school=env["school"],
        student=env["student"],
        academic_year=year,
        grade=grade,
        section=section,
        status=EnrollmentStatus.ACTIVE,
        enrolled_at=enrolled_at,
    )
    return year, enrollment


def _context(env, day, *, year=None):
    return AttendanceDayContext.objects.create(
        school=env["school"],
        academic_year=year or env["year"],
        attendance_date=day,
        timezone_snapshot="Asia/Riyadh",
        schedule_snapshot={
            "periods": [
                {
                    "sequence": 3,
                    "name": "الحصة المحفوظة",
                    "start_time": "00:00",
                    "end_time": "23:59",
                    "is_attendance_period": True,
                },
            ]
        },
    )


def _history(env, relation, day):
    response = env["parent"].get(
        f"/api/v1/parent/children/{relation.id}/history/?from_date={day}&to_date={day}"
    )
    assert response.status_code == 200, response.content
    return response.json()


def test_prepared_future_year_does_not_replace_current_child_header(portal_env):
    env = portal_env
    relation, _, _ = journeys.activate(env)
    future = env["local_now"].date() + timedelta(days=365)
    year, prepared = _next_enrollment(env, enrolled_at=future)
    detail = env["parent"].get(f"/api/v1/parent/children/{relation.id}/")
    assert detail.status_code == 200, detail.content
    header = detail.json()["child"]["student"]
    assert header["grade_name"] == env["grade"].name
    assert header["section_name"] == env["section"].name
    assert header["department"] == env["section"].department
    cards = env["parent"].get("/api/v1/parent/children/").json()["results"]
    assert cards[0]["student"]["section_name"] == env["section"].name
    year.refresh_from_db()
    prepared.refresh_from_db()
    assert year.status == AcademicYearStatus.UPCOMING
    assert prepared.status == EnrollmentStatus.ACTIVE


def test_frozen_day_year_keeps_actual_draft_during_late_noor_preparation(portal_env):
    env = portal_env
    relation, _, _ = journeys.activate(env)
    today = env["local_now"].date()
    env["year"].end_date = today - timedelta(days=1)
    env["year"].save(update_fields=["end_date"])
    draft = journeys.make_session(env, status="IN_PROGRESS")
    _context(env, today)
    _next_enrollment(env, enrolled_at=today)
    assert not DailyAttendanceSummary.objects.filter(student=env["student"]).exists()
    detail = env["parent"].get(f"/api/v1/parent/children/{relation.id}/")
    assert detail.status_code == 200, detail.content
    period = detail.json()["periods"][0]
    assert period["session_id"] == draft.id
    assert period["status"] == "IN_PROGRESS"
    assert detail.json()["today"]["submitted_periods"] == 0
    history = _history(env, relation, today)
    assert len(history["results"]) == 1
    day = history["results"][0]
    assert day["absence_status"] == "UNDETERMINED"
    assert day["submitted_periods"] == day["absent_periods"] == 0
    assert day["updated_at"] == draft.updated_at.isoformat()


def test_today_without_saved_context_uses_active_year_before_prepared_date_cover(portal_env):
    env = portal_env
    relation, _, _ = journeys.activate(env)
    today = env["local_now"].date()
    env["year"].end_date = today - timedelta(days=1)
    env["year"].save(update_fields=["end_date"])
    submitted = journeys.make_session(env)
    _next_enrollment(env, enrolled_at=today)
    detail = env["parent"].get(f"/api/v1/parent/children/{relation.id}/").json()
    assert detail["periods"][0]["session_id"] == submitted.id
    assert detail["periods"][0]["status"] == "ABSENT"
    assert detail["today"]["absent_periods"] == 1
    history = _history(env, relation, today)
    assert history["results"][0]["absent_periods"] == 1
    assert history["results"][0]["completeness_status"] == "INCOMPLETE"
    assert not AttendanceDayContext.objects.filter(school=env["school"]).exists()
    assert not DailyAttendanceSummary.objects.filter(student=env["student"]).exists()


def test_saved_summary_year_precedes_conflicting_day_context_year(portal_env):
    env = portal_env
    relation, _, _ = journeys.activate(env)
    today = env["local_now"].date()
    submitted = journeys.make_session(env)
    next_year, _ = _next_enrollment(env, enrolled_at=today)
    _context(env, today, year=next_year)
    DailyAttendanceSummary.objects.create(
        school=env["school"],
        student=env["student"],
        academic_year=env["year"],
        section=env["section"],
        attendance_date=today,
        expected_periods=7,
        submitted_periods=1,
        present_periods=0,
        absent_periods=1,
        unexcused_absent_periods=1,
        absence_status="FULL",
        completeness_status="INCOMPLETE",
        calculated_at=timezone.now(),
    )
    detail = env["parent"].get(f"/api/v1/parent/children/{relation.id}/").json()
    assert detail["periods"][0]["session_id"] == submitted.id
    assert detail["periods"][0]["status"] == "ABSENT"
    assert detail["today"]["expected_periods"] == 7
    assert _history(env, relation, today)["results"][0]["absent_periods"] == 1


def test_closed_year_transfer_history_keeps_original_section_without_context_or_summary(portal_env):
    env = portal_env
    relation, _, _ = journeys.activate(env)
    today = env["local_now"].date()
    historical = today - timedelta(days=10)
    transfer_date = today - timedelta(days=5)
    first = StudentEnrollment.objects.get(student=env["student"], academic_year=env["year"])
    first.status = EnrollmentStatus.TRANSFERRED
    first.ended_at = transfer_date
    first.save(update_fields=["status", "ended_at"])
    transferred_section = Section.objects.create(
        school=env["school"],
        grade=env["grade"],
        code="TRANSFER",
        name="فصل النقل السابق",
    )
    StudentEnrollment.objects.create(
        school=env["school"],
        student=env["student"],
        academic_year=env["year"],
        grade=env["grade"],
        section=transferred_section,
        enrolled_at=transfer_date,
    )
    env["year"].status = AcademicYearStatus.CLOSED
    env["year"].end_date = today - timedelta(days=3)
    env["year"].save(update_fields=["status", "end_date"])
    _, current = _next_enrollment(
        env,
        enrolled_at=today - timedelta(days=2),
        status=AcademicYearStatus.ACTIVE,
    )
    old_session = journeys.make_session(env)
    old_session.attendance_date = historical
    old_session.save(update_fields=["attendance_date"])
    detail = env["parent"].get(f"/api/v1/parent/children/{relation.id}/?date={historical}").json()
    assert detail["child"]["student"]["section_name"] == current.section.name
    assert detail["periods"][0]["session_id"] == old_session.id
    assert detail["periods"][0]["status"] == "ABSENT"
    history = _history(env, relation, historical)
    assert history["results"][0]["absent_periods"] == 1
    assert history["results"][0]["completeness_status"] == "INCOMPLETE"


def test_historical_recorded_year_preserves_facts_when_date_cover_points_to_prepared_year(
    portal_env,
):
    env = portal_env
    relation, _, _ = journeys.activate(env)
    historical = env["local_now"].date() - timedelta(days=2)
    next_year, prepared = _next_enrollment(env, enrolled_at=historical)
    env["year"].end_date = historical - timedelta(days=1)
    env["year"].status = AcademicYearStatus.CLOSED
    env["year"].save(update_fields=["end_date", "status"])
    next_year.status = AcademicYearStatus.ACTIVE
    next_year.save(update_fields=["status"])
    recorded = journeys.make_session(env)
    recorded.attendance_date = historical
    recorded.save(update_fields=["attendance_date"])
    assert not AttendanceDayContext.objects.filter(school=env["school"]).exists()
    assert not DailyAttendanceSummary.objects.filter(student=env["student"]).exists()
    response = env["parent"].get(f"/api/v1/parent/children/{relation.id}/?date={historical}")
    assert response.status_code == 200, response.content
    detail = response.json()
    assert detail["child"]["student"]["section_name"] == prepared.section.name
    assert detail["periods"][0]["session_id"] == recorded.id
    assert detail["periods"][0]["status"] == "ABSENT"
    assert detail["today"]["completeness_status"] == "INCOMPLETE"
    history = _history(env, relation, historical)
    assert history["results"][0]["absent_periods"] == 1
    assert history["results"][0]["completeness_status"] == "INCOMPLETE"
