"""Controlled reconciliation of confirmed duplicate students from a Noor import."""

from collections import defaultdict

from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from attendance.models import AttendanceMark, DailyAttendanceSummary
from audit.models import AuditAction
from audit.services import record_event
from parents.access import lock_parent_school
from students.management.commands.audit_student_reconciliation import audit_group
from students.models import (
    EnrollmentStatus,
    Student,
    StudentEnrollment,
    StudentImportJob,
    StudentStatus,
)

_MOVABLE_RELATIONS = {
    "students.StudentEnrollment",
    "attendance.DailyAttendanceSummary",
    "attendance.AttendanceMark",
}
# Contact reviews grant no access. Keep them on archived source records as evidence.
_RETAINED_SOURCE_RELATIONS = {"parents.GuardianContactReview"}


def _validated_summaries(student_ids):
    grouped = defaultdict(list)
    for row in DailyAttendanceSummary.objects.select_for_update().filter(
        student_id__in=student_ids
    ):
        grouped[row.attendance_date].append(row)
    for day, rows in grouped.items():
        if len(rows) < 2:
            continue
        comparable = {
            (
                row.section_id,
                row.academic_year_id,
                row.expected_periods,
                row.absence_status,
                row.absent_periods,
                row.excused_absent_periods,
                row.unexcused_absent_periods,
            )
            for row in rows
        }
        if len(comparable) != 1 or any(
            row.present_periods != row.submitted_periods - row.absent_periods for row in rows
        ):
            raise CommandError(f"Conflicting attendance facts on {day}; manual review required.")
    return grouped


@transaction.atomic
def reconcile_group(ids, *, school_id, expected_import_job_id):
    """Move verified history to the file's student, retaining old identifiers as aliases."""
    lock_parent_school(school_id)
    students = list(Student.objects.select_for_update().filter(pk__in=ids))
    if len(students) != len(ids):
        raise CommandError("A student record disappeared during reconciliation.")
    by_id = {student.pk: student for student in students}
    target = by_id[ids[0]]
    sources = [by_id[item] for item in ids[1:]]
    report = audit_group(ids, school_id=school_id)
    if report["latest_import_job_id"] != expected_import_job_id:
        raise CommandError("The latest completed import changed; run the audit again.")
    if not all(report["identity_checks"].values()):
        raise CommandError("Identity or latest-import checks failed; no records changed.")
    if any(
        student.status != StudentStatus.ACTIVE or student.merged_into_id for student in students
    ):
        raise CommandError("All records must be active and unmerged before reconciliation.")
    if StudentImportJob.objects.filter(
        school_id=school_id, status__in=["PROCESSING", "IMPORTING"]
    ).exists():
        raise CommandError("An import is currently running for this school.")

    for relation in report["relations"]:
        source_count = sum(relation["counts"].get(item.pk, 0) for item in sources)
        if source_count and relation["model"] not in (
            _MOVABLE_RELATIONS | _RETAINED_SOURCE_RELATIONS
        ):
            raise CommandError(f"Unsupported linked history: {relation['model']}.")
        if relation["model"] == "attendance.AttendanceMark" and relation["collisions"]:
            raise CommandError("Attendance marks overlap in one session; manual review required.")

    summary_groups = _validated_summaries(ids)
    source_ids = [item.pk for item in sources]
    enrollments = list(StudentEnrollment.objects.select_for_update().filter(student_id__in=ids))
    target_active = [
        row
        for row in enrollments
        if row.student_id == target.pk and row.status == EnrollmentStatus.ACTIVE
    ]
    if len(target_active) != 1:
        raise CommandError("Expected exactly one active target enrollment.")
    for source in sources:
        active = [
            row
            for row in enrollments
            if row.student_id == source.pk and row.status == EnrollmentStatus.ACTIVE
        ]
        if len(active) != 1:
            raise CommandError(f"Source {source.pk} has an unexpected active enrollment.")
        if active[0].enrolled_at < target_active[0].enrolled_at:
            raise CommandError("Source has an earlier active enrollment; manual review required.")

    moved_marks = AttendanceMark.objects.filter(student_id__in=source_ids).update(student=target)
    moved_summaries = 0
    discarded_summaries = []
    for day, rows in summary_groups.items():
        chosen = max(rows, key=lambda row: (row.submitted_periods, row.calculated_at, row.pk))
        for row in rows:
            if row.pk == chosen.pk:
                continue
            discarded_summaries.append(
                {
                    "id": row.pk,
                    "day": day.isoformat(),
                    "submitted": row.submitted_periods,
                    "absence_status": row.absence_status,
                }
            )
            row.delete()
        if chosen.student_id != target.pk:
            DailyAttendanceSummary.objects.filter(pk=chosen.pk).update(student=target)
            moved_summaries += 1

    moved_enrollments = []
    discarded_enrollments = []
    for row in enrollments:
        if row.student_id not in source_ids:
            continue
        if (
            row.status != EnrollmentStatus.ACTIVE
            and row.ended_at is not None
            and row.enrolled_at < row.ended_at
            and row.ended_at <= target_active[0].enrolled_at
        ):
            StudentEnrollment.objects.filter(pk=row.pk).update(student=target)
            moved_enrollments.append(row.pk)
        else:
            if row.status != EnrollmentStatus.ACTIVE and (
                row.ended_at is None or row.enrolled_at < row.ended_at
            ):
                raise CommandError("An enrollment cannot be safely consolidated.")
            discarded_enrollments.append(row.pk)
            row.delete()

    today = timezone.localdate()
    for source in sources:
        source.status = StudentStatus.ARCHIVED
        source.merged_into = target
        source.status_changed_at = timezone.now()
        source.exit_date = today
        source.exit_reason = f"دُمج هذا السجل بسجل الطالب رقم {target.pk}"
        source.save(
            update_fields=[
                "status",
                "merged_into",
                "status_changed_at",
                "exit_date",
                "exit_reason",
                "updated_at",
            ]
        )

    record_event(
        AuditAction.STUDENT_UPDATED,
        school=target.school,
        target_type="Student",
        target_id=target.pk,
        metadata={
            "operation": "confirmed_duplicate_reconciliation",
            "source_ids": source_ids,
            "import_job_id": expected_import_job_id,
            "moved_attendance_marks": moved_marks,
            "moved_daily_summaries": moved_summaries,
            "discarded_daily_summaries": discarded_summaries,
            "moved_historical_enrollments": moved_enrollments,
            "discarded_duplicate_enrollments": discarded_enrollments,
        },
    )
    return {
        "target_id": target.pk,
        "archived_source_ids": source_ids,
        "moved_attendance_marks": moved_marks,
        "moved_daily_summaries": moved_summaries,
        "discarded_daily_summaries": discarded_summaries,
        "moved_historical_enrollments": moved_enrollments,
    }
