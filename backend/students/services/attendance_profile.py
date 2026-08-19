"""Read-only student attendance profile queries built on Phase 8 attendance data."""

from datetime import date

from django.db.models import Count, Q, Sum

from attendance.models import (
    AttendanceChange,
    AttendanceMark,
    AttendanceMarkStatus,
    AttendanceSession,
    AttendanceSessionStatus,
    DailyAbsenceStatus,
    DailyAttendanceSummary,
)
from students.models import Student

MAX_PROFILE_DAYS = 366

STATUS_LABELS = {
    "ACTIVE": "نشط",
    "GRADUATED": "متخرج",
    "TRANSFERRED": "منقول",
    "WITHDRAWN": "منسحب",
    "INACTIVE": "غير نشط",
    "ARCHIVED": "مؤرشف",
}
ABSENCE_LABELS = {
    DailyAbsenceStatus.FULL: "غياب يوم كامل",
    DailyAbsenceStatus.PARTIAL: "غياب جزئي",
    DailyAbsenceStatus.NONE: "لا يوجد غياب",
    DailyAbsenceStatus.UNDETERMINED: "بيانات غير مكتملة",
}
MARK_LABELS = {
    AttendanceMarkStatus.ABSENT: "غائب",
    AttendanceMarkStatus.LATE: "متأخر",
    "PRESENT": "حاضر",
    "NOT_RECORDED": "لم يتم تسجيل الحضور",
}


def validate_profile_range(from_date: date, to_date: date) -> None:
    if from_date > to_date:
        raise ValueError("INVALID_ATTENDANCE_DATE_RANGE")
    if (to_date - from_date).days + 1 > MAX_PROFILE_DAYS:
        raise ValueError("ATTENDANCE_PROFILE_RANGE_TOO_LARGE")


def student_in_school(*, school, student_id: int) -> Student | None:
    return Student.objects.filter(school=school, id=student_id).first()


def profile_student_queryset(*, school, student_id: int):
    return Student.objects.filter(school=school, id=student_id).prefetch_related(
        "enrollments__grade", "enrollments__section"
    )


def _current_enrollment(student: Student, *, on_date: date | None = None):
    enrollments = list(student.enrollments.all())
    if on_date is not None:
        dated = [
            enrollment
            for enrollment in enrollments
            if enrollment.enrolled_at <= on_date
            and (enrollment.ended_at is None or enrollment.ended_at > on_date)
        ]
        return max(dated, key=lambda enrollment: enrollment.enrolled_at, default=None)
    return max(
        [enrollment for enrollment in enrollments if enrollment.status == "ACTIVE"],
        key=lambda enrollment: enrollment.enrolled_at,
        default=max(enrollments, key=lambda enrollment: enrollment.enrolled_at, default=None),
    )


def serialize_student_header(student: Student) -> dict:
    enrollment = _current_enrollment(student)
    return {
        "id": student.id,
        "full_name": student.full_name,
        "status": student.status,
        "status_label": STATUS_LABELS.get(student.status, student.status),
        "national_id_masked": student.national_id_masked,
        "student_number": student.student_number,
        "grade": {"id": enrollment.grade_id, "name": enrollment.grade.name}
        if enrollment
        else None,
        "section": {"id": enrollment.section_id, "name": enrollment.section.name}
        if enrollment
        else None,
    }


def get_profile_summary(*, school, student: Student, from_date: date, to_date: date) -> dict:
    validate_profile_range(from_date, to_date)
    rows = DailyAttendanceSummary.objects.filter(
        school=school,
        student=student,
        attendance_date__range=(from_date, to_date),
    )
    totals = rows.aggregate(
        full_absence_days=Count("id", filter=Q(absence_status=DailyAbsenceStatus.FULL)),
        partial_absence_days=Count("id", filter=Q(absence_status=DailyAbsenceStatus.PARTIAL)),
        undetermined_days=Count("id", filter=Q(absence_status=DailyAbsenceStatus.UNDETERMINED)),
        absent_periods=Sum("absent_periods"),
        late_occurrences=Sum("late_periods"),
        late_minutes=Sum("total_late_minutes"),
    )
    return {
        "full_absence_days": totals["full_absence_days"] or 0,
        "partial_absence_days": totals["partial_absence_days"] or 0,
        "undetermined_days": totals["undetermined_days"] or 0,
        "absent_periods": totals["absent_periods"] or 0,
        "period_late_occurrences": totals["late_occurrences"] or 0,
        "period_late_minutes": totals["late_minutes"] or 0,
    }


def get_daily_history(*, school, student: Student, from_date: date, to_date: date):
    validate_profile_range(from_date, to_date)
    return DailyAttendanceSummary.objects.filter(
        school=school,
        student=student,
        attendance_date__range=(from_date, to_date),
    ).select_related("section__grade").order_by("-attendance_date")


def _mark_payload(mark: AttendanceMark | None, *, submitted: bool) -> dict:
    if mark is None and not submitted:
        status = "NOT_RECORDED"
    elif mark is None:
        status = "PRESENT"
    else:
        status = mark.status
    return {
        "status": status,
        "status_label": MARK_LABELS[status],
        "arrival_time": mark.arrival_time.strftime("%H:%M") if mark and mark.arrival_time else None,
        "late_minutes": mark.late_minutes if mark else None,
    }


def get_day_detail(*, school, student: Student, attendance_date: date) -> dict:
    from attendance.models import AttendanceDayContext

    summary = DailyAttendanceSummary.objects.filter(
        school=school, student=student, attendance_date=attendance_date
    ).select_related("section__grade").first()
    context = AttendanceDayContext.objects.filter(
        school=school, attendance_date=attendance_date
    ).first()
    expected = context.schedule_snapshot.get("periods", []) if context else []
    expected = [period for period in expected if period.get("is_attendance_period", True)]
    section_id = summary.section_id if summary else None
    sessions = {
        session.period_sequence: session
        for session in AttendanceSession.objects.filter(
            school=school,
            section_id=section_id,
            attendance_date=attendance_date,
            status=AttendanceSessionStatus.SUBMITTED,
        ).prefetch_related("marks")
    } if section_id else {}
    periods = []
    for period in expected:
        session = sessions.get(period["sequence"])
        mark = (
            next((m for m in session.marks.all() if m.student_id == student.id), None)
            if session
            else None
        )
        periods.append({
            "sequence": period["sequence"],
            "name": period["name"],
            "start_time": period.get("start_time"),
            "end_time": period.get("end_time"),
            **_mark_payload(mark, submitted=session is not None),
        })
    return {
        "date": attendance_date.isoformat(),
        "absence_status": summary.absence_status if summary else DailyAbsenceStatus.UNDETERMINED,
        "absence_status_label": ABSENCE_LABELS[summary.absence_status]
        if summary else ABSENCE_LABELS[DailyAbsenceStatus.UNDETERMINED],
        "section": {
            "id": summary.section_id,
            "name": summary.section.name,
            "grade_name": summary.section.grade.name,
        }
        if summary else None,
        "periods": periods,
    }


def get_period_marks(*, school, student: Student, from_date: date, to_date: date, status: str):
    validate_profile_range(from_date, to_date)
    return AttendanceMark.objects.filter(
        school=school,
        student=student,
        status=status,
        session__status=AttendanceSessionStatus.SUBMITTED,
        session__attendance_date__range=(from_date, to_date),
    ).select_related("session__section__grade").order_by(
        "-session__attendance_date", "session__period_sequence"
    )


def get_attendance_changes(*, school, student: Student, from_date: date, to_date: date):
    validate_profile_range(from_date, to_date)
    return AttendanceChange.objects.filter(
        school=school,
        student=student,
        session__attendance_date__range=(from_date, to_date),
    ).select_related(
        "session__section__grade", "actor_membership__staff_profile", "actor_membership__user"
    ).order_by("-changed_at")
