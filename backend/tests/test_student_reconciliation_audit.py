"""The duplicate audit must expose conflicts before any student merge."""

import json
from datetime import date
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from attendance.models import AttendanceMark, AttendanceSession, DailyAttendanceSummary
from audit.models import AuditLog
from common.errors import ApiError
from students.management.commands.audit_student_reconciliation import (
    _parse_group,
    audit_group,
)
from students.models import (
    EnrollmentStatus,
    ImportJobStatus,
    Student,
    StudentEnrollment,
    StudentImportJob,
)
from students.services.lifecycle import set_student_status
from tests.attendance_helpers import setup_attendance_env


@pytest.mark.django_db
def test_reconciliation_audit_reports_attendance_and_enrollment_collisions(
    make_school, make_user, make_membership, role_client
):
    school = make_school()
    env = setup_attendance_env(school, students_count=3)
    target, old_one, old_two = env["students"]
    Student.objects.filter(pk__in=[target.pk, old_one.pk, old_two.pk]).update(
        full_name="الطالب نفسه", guardian_name="ولي الأمر"
    )
    StudentEnrollment.objects.filter(student_id__in=[target.pk, old_one.pk, old_two.pk]).update(
        enrolled_at=date(2026, 9, 29)
    )
    for student, start in [(old_one, date(2026, 9, 13)), (old_two, date(2026, 9, 29))]:
        StudentEnrollment.objects.create(
            school=school,
            student=student,
            academic_year=env["year"],
            grade=env["grade"],
            section=env["section"],
            status=EnrollmentStatus.TRANSFERRED,
            enrolled_at=start,
            ended_at=date(2026, 9, 29),
        )
    import_job = StudentImportJob.objects.create(
        school=school,
        uploaded_by=make_user("0550008001"),
        academic_year=env["year"],
        original_filename="students.xlsx",
        status=ImportJobStatus.COMPLETED,
        summary={"missing_ids": [old_one.pk, old_two.pk]},
    )

    for student, day in [(old_one, 28), (old_one, 29), (old_two, 29)]:
        DailyAttendanceSummary.objects.create(
            school=school,
            student=student,
            academic_year=env["year"],
            section=env["section"],
            attendance_date=date(2026, 9, day),
            expected_periods=7,
            submitted_periods=1,
            absent_periods=1 if day == 28 else 0,
            present_periods=0 if day == 28 else 1,
            completeness_status="PARTIAL",
            absence_status="FULL" if day == 28 else "NONE",
            calculated_at=timezone.now(),
        )
    actor = make_user("0550008002")
    membership = make_membership(actor, school)
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
    AttendanceMark.objects.create(school=school, session=session, student=old_one, status="ABSENT")

    report = audit_group([target.pk, old_one.pk, old_two.pk], school_id=school.pk)
    assert all(report["identity_checks"].values())
    summaries = next(
        row for row in report["relations"] if row["model"] == "attendance.DailyAttendanceSummary"
    )
    assert summaries["counts"] == {target.pk: 0, old_one.pk: 2, old_two.pk: 1}
    assert len(summaries["collisions"]) == 1
    assert summaries["collisions"][0]["key"]["attendance_date"] == date(2026, 9, 29)
    enrollments = next(
        row for row in report["relations"] if row["model"] == "students.StudentEnrollment"
    )
    assert len(enrollments["collisions"]) == 1

    output = StringIO()
    call_command(
        "audit_student_reconciliation",
        "--school-id",
        str(school.pk),
        "--group",
        f"{target.pk}:{old_one.pk}:{old_two.pk}",
        stdout=output,
    )
    command_report = json.loads(output.getvalue())
    assert command_report[0]["identity_checks"] == report["identity_checks"]
    assert Student.objects.filter(school=school).count() == 3

    conflict = DailyAttendanceSummary.objects.get(student=old_two)
    conflict.absence_status = "FULL"
    conflict.absent_periods = 1
    conflict.present_periods = 0
    conflict.unexcused_absent_periods = 1
    conflict.save()
    with pytest.raises(CommandError, match="Conflicting attendance facts"):
        call_command(
            "audit_student_reconciliation",
            "--school-id", str(school.pk),
            "--group", f"{target.pk}:{old_one.pk}:{old_two.pk}",
            "--apply", "--expected-import-job", str(import_job.pk),
            stdout=StringIO(),
        )
    assert Student.objects.filter(pk__in=[old_one.pk, old_two.pk], status="ACTIVE").count() == 2
    assert AttendanceMark.objects.filter(student=old_one, session=session).exists()
    conflict.absence_status = "NONE"
    conflict.absent_periods = 0
    conflict.present_periods = 1
    conflict.unexcused_absent_periods = 0
    conflict.save()

    applied_output = StringIO()
    call_command(
        "audit_student_reconciliation",
        "--school-id",
        str(school.pk),
        "--group",
        f"{target.pk}:{old_one.pk}:{old_two.pk}",
        "--apply",
        "--expected-import-job",
        str(import_job.pk),
        stdout=applied_output,
    )
    applied = json.loads(applied_output.getvalue())[0]
    assert applied["archived_source_ids"] == [old_one.pk, old_two.pk]
    assert len(applied["discarded_daily_summaries"]) == 1
    assert DailyAttendanceSummary.objects.filter(student=target).count() == 2
    assert (
        DailyAttendanceSummary.objects.filter(student_id__in=[old_one.pk, old_two.pk]).count() == 0
    )
    assert AttendanceMark.objects.filter(student=target, session=session).exists()
    assert StudentEnrollment.objects.filter(student=target).count() == 2
    assert StudentEnrollment.objects.filter(student_id__in=[old_one.pk, old_two.pk]).count() == 0
    assert (
        Student.objects.filter(
            pk__in=[old_one.pk, old_two.pk], merged_into=target, status="ARCHIVED"
        ).count()
        == 2
    )
    assert AuditLog.objects.filter(
        target_id=str(target.pk), metadata__operation="confirmed_duplicate_reconciliation"
    ).exists()
    old_one.refresh_from_db()
    with pytest.raises(ApiError, match="سجل قديم مدمج"):
        set_student_status(student=old_one, new_status="ACTIVE", actor=actor)
    client, _, _ = role_client(["SCHOOL_MANAGER"], school=school)
    assert client.get("/api/v1/students/inactive/?missing_last_import=1").json()["count"] == 0
    assert client.get("/api/v1/students/inactive/").json()["count"] == 0


def test_reconciliation_group_requires_distinct_positive_ids():
    assert _parse_group("3:1:2") == [3, 1, 2]
    for value in ["3", "3:3", "3:0", "3:not-an-id"]:
        with pytest.raises(CommandError):
            _parse_group(value)
