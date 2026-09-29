"""A school manager can review and reconcile one student's duplicate records."""

from datetime import date

import pytest
from django.utils import timezone

from attendance.models import AttendanceMark, AttendanceSession, DailyAttendanceSummary
from audit.models import AuditLog
from memberships.models import SchoolMembership
from students.models import (
    EnrollmentStatus,
    Grade,
    Section,
    Student,
    StudentEnrollment,
)
from tests.attendance_helpers import setup_attendance_env


def _summary(*, school, student, year, section, day, absent=False):
    return DailyAttendanceSummary.objects.create(
        school=school,
        student=student,
        academic_year=year,
        section=section,
        attendance_date=date(2026, 9, day),
        expected_periods=7,
        submitted_periods=1,
        present_periods=0 if absent else 1,
        absent_periods=1 if absent else 0,
        unexcused_absent_periods=1 if absent else 0,
        completeness_status="PARTIAL",
        absence_status="FULL" if absent else "NONE",
        calculated_at=timezone.now(),
    )


@pytest.fixture
def merge_case(make_school, role_client):
    school = make_school()
    client, _, actor = role_client(["SCHOOL_MANAGER"], school=school)
    env = setup_attendance_env(school, students_count=3)
    target, older, duplicate = env["students"]
    Student.objects.filter(pk__in=[row.pk for row in env["students"]]).update(
        full_name="الطالب نفسه", guardian_name="ولي الأمر"
    )
    old_grade = Grade.objects.create(school=school, code="OLD", name="صف سابق", sequence=1)
    old_section = Section.objects.create(
        school=school, grade=old_grade, code="OLD", name="فصل سابق"
    )
    StudentEnrollment.objects.filter(student=older).update(
        grade=old_grade, section=old_section, enrolled_at=date(2026, 9, 13)
    )
    StudentEnrollment.objects.filter(student_id__in=[target.pk, duplicate.pk]).update(
        enrolled_at=date(2026, 9, 16)
    )
    for day in [14, 15, 16]:
        _summary(school=school, student=older, year=env["year"], section=old_section, day=day)
    for student in [target, duplicate]:
        for day in [20, 21, 28, 29]:
            _summary(
                school=school,
                student=student,
                year=env["year"],
                section=env["section"],
                day=day,
                absent=day == 28,
            )
    membership = SchoolMembership.objects.get(user=actor, school=school)
    session = AttendanceSession.objects.create(
        school=school,
        academic_year=env["year"],
        section=env["section"],
        attendance_date=date(2026, 9, 28),
        period_sequence=1,
        bell_period_snapshot={},
        roster_fingerprint="a" * 64,
        unprepared_alert_minutes_snapshot=10,
        started_by_membership=membership,
    )
    AttendanceMark.objects.create(school=school, session=session, student=target, status="ABSENT")
    AttendanceMark.objects.create(
        school=school, session=session, student=duplicate, status="ABSENT"
    )
    return client, school, actor, target, older, duplicate, old_section


@pytest.mark.django_db
def test_manager_previews_and_merges_attendance_and_historical_section(merge_case):
    client, school, actor, target, older, duplicate, old_section = merge_case
    selection = {"target_id": target.pk, "source_ids": [older.pk, duplicate.pk]}
    preview_response = client.post(
        "/api/v1/students/merge/preview/", selection, content_type="application/json"
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["can_merge"] is True
    assert preview["summary"]["attendance_days"] == 7
    assert preview["summary"]["duplicate_daily_summaries"] == 4
    assert preview["summary"]["duplicate_attendance_marks"] == 1
    assert preview["history_adjustments"][0]["through_date"] == "2026-09-16"
    assert Student.objects.filter(pk__in=[older.pk, duplicate.pk], status="ACTIVE").count() == 2

    apply_response = client.post(
        "/api/v1/students/merge/",
        {"confirmation_token": preview["confirmation_token"], "confirmed_same_person": True},
        content_type="application/json",
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["archived_source_ids"] == [older.pk, duplicate.pk]
    assert (
        Student.objects.filter(
            pk__in=[older.pk, duplicate.pk], status="ARCHIVED", merged_into=target
        ).count()
        == 2
    )
    assert DailyAttendanceSummary.objects.filter(student=target).count() == 7
    assert (
        DailyAttendanceSummary.objects.filter(student_id__in=[older.pk, duplicate.pk]).count() == 0
    )
    assert AttendanceMark.objects.filter(student=target).count() == 1
    assert AttendanceMark.objects.filter(student_id__in=[older.pk, duplicate.pk]).count() == 0
    assert StudentEnrollment.objects.filter(student_id__in=[older.pk, duplicate.pk]).count() == 0
    assert StudentEnrollment.objects.get(
        student=target, status=EnrollmentStatus.ACTIVE
    ).enrolled_at == date(2026, 9, 17)
    historical = StudentEnrollment.objects.get(student=target, section=old_section)
    assert historical.status == EnrollmentStatus.TRANSFERRED
    assert historical.ended_at == date(2026, 9, 17)
    assert (
        AuditLog.objects.filter(
            school=school, actor=actor, metadata__operation="manual_student_merge"
        ).count()
        == 1
    )
    repeated = client.post(
        "/api/v1/students/merge/",
        {"confirmation_token": preview["confirmation_token"], "confirmed_same_person": True},
        content_type="application/json",
    )
    assert repeated.status_code == 409
    assert DailyAttendanceSummary.objects.filter(student=target).count() == 7


@pytest.mark.django_db
def test_manager_merge_requires_fresh_preview_and_explicit_confirmation(merge_case):
    client, _, _, target, older, duplicate, _ = merge_case
    preview = client.post(
        "/api/v1/students/merge/preview/",
        {"target_id": target.pk, "source_ids": [older.pk, duplicate.pk]},
        content_type="application/json",
    ).json()
    token = preview["confirmation_token"]
    denied = client.post(
        "/api/v1/students/merge/",
        {"confirmation_token": token, "confirmed_same_person": False},
        content_type="application/json",
    )
    assert denied.status_code == 400
    summary = DailyAttendanceSummary.objects.filter(student=duplicate).first()
    summary.submitted_periods = 2
    summary.present_periods = 2
    summary.save(update_fields=["submitted_periods", "present_periods", "updated_at"])
    stale = client.post(
        "/api/v1/students/merge/",
        {"confirmation_token": token, "confirmed_same_person": True},
        content_type="application/json",
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "MERGE_PREVIEW_EXPIRED"
    assert Student.objects.filter(pk__in=[older.pk, duplicate.pk], status="ACTIVE").count() == 2


@pytest.mark.django_db
def test_manager_merge_blocks_conflicting_attendance_and_other_school(
    merge_case, role_client, make_school
):
    client, _, _, target, older, duplicate, _ = merge_case
    conflict = DailyAttendanceSummary.objects.get(
        student=duplicate, attendance_date=date(2026, 9, 20)
    )
    conflict.absence_status = "FULL"
    conflict.absent_periods = 1
    conflict.present_periods = 0
    conflict.unexcused_absent_periods = 1
    conflict.save()
    blocked = client.post(
        "/api/v1/students/merge/preview/",
        {"target_id": target.pk, "source_ids": [older.pk, duplicate.pk]},
        content_type="application/json",
    ).json()
    assert blocked["can_merge"] is False
    assert blocked["confirmation_token"] is None
    assert any("تختلف بيانات الحضور" in message for message in blocked["blockers"])

    other_client, _, _ = role_client(["SCHOOL_MANAGER"], school=make_school())
    hidden = other_client.post(
        "/api/v1/students/merge/preview/",
        {"target_id": target.pk, "source_ids": [older.pk]},
        content_type="application/json",
    )
    assert hidden.status_code == 404


@pytest.mark.django_db
def test_vice_principal_cannot_preview_or_apply_merge(merge_case, role_client):
    _, school, _, target, older, _, _ = merge_case
    vice_client, _, _ = role_client(["VICE_PRINCIPAL"], school=school)
    response = vice_client.post(
        "/api/v1/students/merge/preview/",
        {"target_id": target.pk, "source_ids": [older.pk]},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_older_section_cannot_be_chosen_as_current_record(merge_case):
    client, _, _, target, older, duplicate, _ = merge_case
    preview = client.post(
        "/api/v1/students/merge/preview/",
        {"target_id": older.pk, "source_ids": [target.pk, duplicate.pk]},
        content_type="application/json",
    ).json()
    assert preview["can_merge"] is False
    assert preview["confirmation_token"] is None
    assert any("فصل تاريخي" in message for message in preview["blockers"])
