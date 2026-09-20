"""The current school-day attendance population and its uncovered reasons."""

from django.db.models import Q

from attendance.models import (
    AttendanceSession,
    AttendanceSessionStatus,
    DailyAbsenceStatus,
    DailyAttendanceSummary,
)
from attendance.selectors.monitoring import expected_sections_queryset
from attendance.services.sessions import _active_year
from students.models import EnrollmentStatus, Student, StudentEnrollment, StudentStatus
from students.services.enrollments import enrollments_on_date


def current_day_scope(*, school, attendance_date):
    """Keep the roster, attendance population, and missing-summary reasons distinct."""
    year = _active_year(school)
    section_ids = set(
        expected_sections_queryset(school=school, year=year)
        .filter(grade__is_active=True)
        .values_list("id", flat=True)
    )
    enrollment_rows = list(
        enrollments_on_date(school=school, on_date=attendance_date)
        .filter(
            academic_year=year,
            section_id__in=section_ids,
            status=EnrollmentStatus.ACTIVE,
            student__status=StudentStatus.ACTIVE,
        )
        .values_list("student_id", "section_id")
        .distinct()
    )
    section_by_student = dict(enrollment_rows)
    eligible_ids = set(section_by_student)
    roster_ids = set(
        Student.objects.filter(school=school, status=StudentStatus.ACTIVE)
        .values_list("id", flat=True)
    )
    excluded_ids = roster_ids - eligible_ids
    inactive_assignment_ids = set(
        StudentEnrollment.objects.filter(
            school=school,
            academic_year=year,
            status=EnrollmentStatus.ACTIVE,
            student_id__in=excluded_ids,
        )
        .filter(Q(section__is_active=False) | Q(grade__is_active=False))
        .values_list("student_id", flat=True)
    )
    summary_rows = list(
        DailyAttendanceSummary.objects.filter(
            school=school,
            attendance_date=attendance_date,
            student_id__in=eligible_ids,
            submitted_periods__gt=0,
        ).values_list("student_id", "absence_status")
    )
    present_ids = {
        student_id for student_id, status in summary_rows
        if status in (DailyAbsenceStatus.NONE, DailyAbsenceStatus.PARTIAL)
    }
    absent_ids = {
        student_id for student_id, status in summary_rows
        if status == DailyAbsenceStatus.FULL
    }
    partial_ids = {
        student_id for student_id, status in summary_rows
        if status == DailyAbsenceStatus.PARTIAL
    }
    unrecorded_ids = eligible_ids - present_ids - absent_ids
    submitted_sections = set(
        AttendanceSession.objects.filter(
            school=school,
            attendance_date=attendance_date,
            section_id__in=section_ids,
            status=AttendanceSessionStatus.SUBMITTED,
        ).values_list("section_id", flat=True)
    )
    awaiting_preparation_ids = {
        student_id for student_id in unrecorded_ids
        if section_by_student[student_id] not in submitted_sections
    }
    missing_summary_ids = unrecorded_ids - awaiting_preparation_ids
    return {
        "roster_students": len(roster_ids),
        "total_students": len(eligible_ids),
        "present_students": len(present_ids),
        "absent_students": len(absent_ids),
        "partial_absence_students": len(partial_ids),
        "unrecorded_students": len(unrecorded_ids),
        "awaiting_preparation_students": len(awaiting_preparation_ids),
        "missing_summary_students": len(missing_summary_ids),
        "excluded_students": len(excluded_ids),
        "inactive_assignment_students": len(inactive_assignment_ids),
        "eligible_ids": eligible_ids,
        "excluded_ids": excluded_ids,
        "inactive_assignment_ids": inactive_assignment_ids,
        "awaiting_preparation_ids": awaiting_preparation_ids,
        "missing_summary_ids": missing_summary_ids,
    }
