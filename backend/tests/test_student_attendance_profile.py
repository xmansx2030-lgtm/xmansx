"""Phase 9: student attendance profile contracts over Phase 8 records."""

from datetime import UTC, date, datetime

import pytest

from attendance.models import DailyAbsenceStatus, DailyAttendanceSummary
from students.models import StudentStatus
from students.services.attendance_profile import get_profile_summary
from tests.test_students_api import _enroll, _make_student

PROFILE_URL = "/api/v1/students/{}/attendance-profile/"
SEARCH_URL = "/api/v1/students/search/"


def _summary(school, enrollment, attendance_date, status, absent, late, minutes):
    return DailyAttendanceSummary.objects.create(
        school=school,
        student=enrollment.student,
        academic_year=enrollment.academic_year,
        section=enrollment.section,
        attendance_date=attendance_date,
        expected_periods=7,
        submitted_periods=7 if status != DailyAbsenceStatus.UNDETERMINED else 3,
        absent_periods=absent,
        late_periods=late,
        present_periods=max(7 - absent - late, 0),
        total_late_minutes=minutes,
        completeness_status=(
            "COMPLETE" if status != DailyAbsenceStatus.UNDETERMINED else "INCOMPLETE"
        ),
        absence_status=status,
        calculated_at=datetime.now(UTC),
    )


@pytest.mark.django_db
def test_profile_summary_aggregates_phase8_daily_summaries(make_school):
    school = make_school()
    student = _make_student(school, "1012345678", "محمد")
    enrollment = _enroll(school, student)
    _summary(school, enrollment, date(2026, 8, 24), DailyAbsenceStatus.FULL, 7, 0, 0)
    _summary(school, enrollment, date(2026, 8, 25), DailyAbsenceStatus.PARTIAL, 2, 2, 35)
    _summary(school, enrollment, date(2026, 8, 26), DailyAbsenceStatus.UNDETERMINED, 1, 1, 8)

    result = get_profile_summary(
        school=school, student=student, from_date=date(2026, 8, 24), to_date=date(2026, 8, 26)
    )

    assert result == {
        "full_absence_days": 1,
        "partial_absence_days": 1,
        "undetermined_days": 1,
        "absent_periods": 10,
        "period_late_occurrences": 3,
        "period_late_minutes": 43,
    }


@pytest.mark.django_db
def test_profile_search_is_masked_tenant_scoped_and_inactive_filtered(role_client, make_school):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    active = _make_student(school, "1012345678", "محمد أحمد")
    inactive = _make_student(school, "1012345679", "محمد قديم")
    inactive.status = StudentStatus.TRANSFERRED
    inactive.save(update_fields=["status"])
    other_school = make_school()
    _make_student(other_school, "1012345678", "محمد في مدرسة أخرى")

    response = client.get(f"{SEARCH_URL}?national_id=١٠١٢٣٤٥٦٧٨")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["results"][0]["id"] == active.id
    assert body["results"][0]["national_id_masked"] == "******5678"
    assert "1012345678" not in str(body)


@pytest.mark.django_db
def test_profile_roles_and_morning_placeholder(role_client):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    student = _make_student(school, "1012345678", "محمد")
    teacher, _, _ = role_client(["TEACHER"], school=school)

    response = manager.get(PROFILE_URL.format(student.id))
    assert response.status_code == 200
    assert response.json()["morning_attendance"] == {"status": "NOT_AVAILABLE"}
    assert teacher.get(PROFILE_URL.format(student.id)).status_code == 403


@pytest.mark.django_db
def test_profile_idor_returns_404(role_client, make_school):
    client_a, school_a, _ = role_client(["SCHOOL_MANAGER"])
    _, school_b, _ = role_client(["SCHOOL_MANAGER"])
    student_b = _make_student(school_b, "1012345678", "طالب ب")

    assert client_a.get(PROFILE_URL.format(student_b.id)).status_code == 404
    assert school_a.id != school_b.id
