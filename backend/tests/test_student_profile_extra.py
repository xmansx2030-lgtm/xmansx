"""تدقيق مستقل م9 — تغطية ناقصة: البحث بالاسم، الترقيم، الخط الزمني، الفصل التاريخي."""

from datetime import UTC, date, datetime, time, timedelta

import pytest

from attendance.models import (
    AttendanceDayContext,
    AttendanceMark,
    AttendanceSession,
    DailyAttendanceSummary,
)
from memberships.models import SchoolMembership
from students.models import Section
from tests.test_students_api import _enroll, _make_student


def _summary_row(school, enrollment, day, *, absent=0, late=0, minutes=0,
                 status="PARTIAL", section=None):
    return DailyAttendanceSummary.objects.create(
        school=school, student=enrollment.student,
        academic_year=enrollment.academic_year,
        section=section or enrollment.section,
        attendance_date=day, expected_periods=7, submitted_periods=7,
        absent_periods=absent, late_periods=late,
        present_periods=max(7 - absent - late, 0),
        total_late_minutes=minutes,
        completeness_status="COMPLETE", absence_status=status,
        calculated_at=datetime.now(UTC),
    )


@pytest.mark.django_db
def test_search_by_name_returns_active_matches(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    target = _make_student(school, "1012345678", "عبدالله الفريد")
    _make_student(school, "1012345679", "اسم آخر تمامًا")
    _enroll(school, target)

    response = client.get("/api/v1/students/search/?search=الفريد")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["results"][0]["id"] == target.id
    assert body["results"][0]["national_id_masked"].startswith("******")


@pytest.mark.django_db
def test_attendance_days_pagination(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    student = _make_student(school, "1012345678", "محمد")
    enrollment = _enroll(school, student)
    base = date(2026, 8, 23)
    for i in range(3):
        _summary_row(school, enrollment, base + timedelta(days=i), absent=1)

    url = (
        f"/api/v1/students/{student.id}/attendance-days/"
        f"?from_date=2026-08-23&to_date=2026-08-30&page_size=2"
    )
    first = client.get(url).json()
    assert first["count"] == 3
    assert len(first["results"]) == 2
    assert first["next"] is not None
    second = client.get(url + "&page=2").json()
    assert len(second["results"]) == 1


@pytest.mark.django_db
def test_day_detail_timeline_statuses(role_client):
    """الخط الزمني: ‏ABSENT من العلامة، PRESENT بلا علامة في جلسة معتمدة،
    ‏NOT_RECORDED لحصة بلا جلسة — لا افتراض حضور."""
    client, school, user = role_client(["SCHOOL_MANAGER"])
    student = _make_student(school, "1012345678", "محمد")
    enrollment = _enroll(school, student)
    day = date(2026, 8, 23)
    AttendanceDayContext.objects.create(
        school=school, academic_year=enrollment.academic_year, attendance_date=day,
        timezone_snapshot="Asia/Riyadh",
        schedule_snapshot={
            "schedule_name": "ع", "is_school_day": True,
            "periods": [
                {"sequence": 1, "name": "الأولى", "start_time": "07:00",
                 "end_time": "07:45", "is_attendance_period": True},
                {"sequence": 2, "name": "الثانية", "start_time": "08:00",
                 "end_time": "08:45", "is_attendance_period": True},
                {"sequence": 3, "name": "الثالثة", "start_time": "09:00",
                 "end_time": "09:45", "is_attendance_period": True},
            ],
        },
    )
    _summary_row(school, enrollment, day, absent=1, status="PARTIAL")
    membership = SchoolMembership.objects.get(user=user, school=school)
    session = AttendanceSession.objects.create(
        school=school, academic_year=enrollment.academic_year,
        section=enrollment.section, attendance_date=day, period_sequence=1,
        bell_period_snapshot={"sequence": 1, "name": "الأولى", "start_time": "07:00",
                              "end_time": "07:45", "timezone": "Asia/Riyadh",
                              "attendance_date": day.isoformat()},
        status="SUBMITTED", roster_fingerprint="fp",
        unprepared_alert_minutes_snapshot=25,
        started_by_membership=membership, submitted_by_membership=membership,
        submitted_at=datetime.now(UTC),
    )
    AttendanceMark.objects.create(
        school=school, session=session, student=student, status="ABSENT"
    )
    AttendanceSession.objects.create(
        school=school, academic_year=enrollment.academic_year,
        section=enrollment.section, attendance_date=day, period_sequence=2,
        bell_period_snapshot={"sequence": 2, "name": "الثانية", "start_time": "08:00",
                              "end_time": "08:45", "timezone": "Asia/Riyadh",
                              "attendance_date": day.isoformat()},
        status="SUBMITTED", roster_fingerprint="fp",
        unprepared_alert_minutes_snapshot=25,
        started_by_membership=membership, submitted_by_membership=membership,
        submitted_at=datetime.now(UTC),
    )

    response = client.get(
        f"/api/v1/students/{student.id}/attendance-days/{day.isoformat()}/"
    )
    assert response.status_code == 200
    periods = {p["sequence"]: p["status"] for p in response.json()["periods"]}
    assert periods == {1: "ABSENT", 2: "PRESENT", 3: "NOT_RECORDED"}


@pytest.mark.django_db
def test_days_history_keeps_historical_section_after_transfer(role_client):
    """صف الملخص يحمل فصل يومه — النقل لاحقًا لا يغير تقرير الماضي."""
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    student = _make_student(school, "1012345678", "محمد")
    enrollment = _enroll(school, student)
    old_section = enrollment.section
    new_section = Section.objects.create(
        school=school, grade=enrollment.grade, code="9", name="9"
    )
    _summary_row(school, enrollment, date(2026, 8, 23), absent=1, section=old_section)
    _summary_row(school, enrollment, date(2026, 8, 25), absent=1, section=new_section)

    response = client.get(
        f"/api/v1/students/{student.id}/attendance-days/"
        "?from_date=2026-08-23&to_date=2026-08-26"
    ).json()
    by_date = {row["date"]: row["section"]["name"] for row in response["results"]}
    assert by_date["2026-08-23"] == old_section.name
    assert by_date["2026-08-25"] == new_section.name


@pytest.mark.django_db
def test_morning_history_endpoint_separate_from_period_lates(role_client):
    """مساران منفصلان: ‏morning-attendance من SchoolArrival وattendance-period-lates
    من العلامات — لا عداد موحد."""
    from devices.models import SchoolArrival

    client, school, _ = role_client(["SCHOOL_MANAGER"])
    student = _make_student(school, "1012345678", "محمد")
    enrollment = _enroll(school, student)
    day = date(2026, 8, 24)
    SchoolArrival.objects.create(
        school=school, student=student, attendance_date=day,
        first_arrival_at=datetime(2026, 8, 24, 4, 13, tzinfo=UTC),
        raw_late_minutes=18, counted_late_minutes=13, status="LATE", source="BIOMETRIC",
    )
    membership = SchoolMembership.objects.filter(school=school).first()
    session = AttendanceSession.objects.create(
        school=school, academic_year=enrollment.academic_year,
        section=enrollment.section, attendance_date=day, period_sequence=2,
        bell_period_snapshot={"sequence": 2, "name": "الثانية", "start_time": "08:00",
                              "end_time": "08:45", "timezone": "Asia/Riyadh",
                              "attendance_date": day.isoformat()},
        status="SUBMITTED", roster_fingerprint="fp",
        unprepared_alert_minutes_snapshot=25,
        started_by_membership=membership, submitted_by_membership=membership,
        submitted_at=datetime.now(UTC),
    )
    AttendanceMark.objects.create(
        school=school, session=session, student=student, status="LATE",
        arrival_time=time(8, 8), late_minutes=8,
    )
    # ملخص اليوم (مصدر مجاميع الملف) — تأخر حصة واحدة بـ8 دقائق، بلا غياب
    _summary_row(school, enrollment, day, late=1, minutes=8, status="NONE")

    query = f"?from_date={day}&to_date={day}"
    morning = client.get(
        f"/api/v1/students/{student.id}/morning-attendance/{query}"
    ).json()
    lates = client.get(
        f"/api/v1/students/{student.id}/attendance-period-lates/{query}"
    ).json()
    profile = client.get(
        f"/api/v1/students/{student.id}/attendance-profile/{query}"
    ).json()

    assert len(morning) == 1 and morning[0]["counted_late_minutes"] == 13
    late_rows = lates["results"] if isinstance(lates, dict) else lates
    assert len(late_rows) == 1 and late_rows[0]["late_minutes"] == 8
    # الفصل الصارم: 1+13 صباحي و1+8 حصص — لا 2+21 موحدة
    assert profile["morning_attendance"]["morning_late_occurrences"] == 1
    assert profile["morning_attendance"]["morning_late_minutes"] == 13
    assert profile["attendance"]["period_late_occurrences"] == 1
    assert profile["attendance"]["period_late_minutes"] == 8
