"""إعادة حساب ملخص اليوم للطالب (م8) — idempotent، متزامن مع الاعتماد/التعديل.

قواعد الحساب:
- expected من AttendanceDayContext (حصص تحضير فقط) — تعديل الجدول لاحقًا لا يغير
  أيامًا مضت.
- submitted = حصص SUBMITTED فقط — مسودات IN_PROGRESS ليست حقيقة رسمية.
- present + absent = submitted؛ اليوم الناقص UNDETERMINED أبدًا لا FULL.
- عضوية الطالب بالفصل من تاريخ القيد (enrollments_on_date) — لا القيد الحالي.
"""

from datetime import date as date_cls

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone as dj_timezone

from attendance.models import (
    AttendanceMark,
    AttendanceMarkStatus,
    AttendanceSession,
    AttendanceSessionStatus,
    DailyAbsenceStatus,
    DailyAttendanceSummary,
    DailyCompleteness,
)
from attendance.services.day_context import get_or_create_attendance_day_context
from students.services.enrollments import enrollments_on_date


def _classify(*, expected: int, submitted: int, absent: int) -> tuple[str, str]:
    complete = expected > 0 and submitted >= expected
    if not complete:
        return DailyCompleteness.INCOMPLETE, DailyAbsenceStatus.UNDETERMINED
    if absent == 0:
        return DailyCompleteness.COMPLETE, DailyAbsenceStatus.NONE
    if absent >= expected:
        return DailyCompleteness.COMPLETE, DailyAbsenceStatus.FULL
    return DailyCompleteness.COMPLETE, DailyAbsenceStatus.PARTIAL


def recalculate_daily_attendance_for_section(*, school, section, attendance_date: date_cls) -> int:
    """يعيد حساب صفوف ملخص اليوم لطلاب فصل — idempotent (تشغيله 10 مرات = نفس الناتج)."""
    context = get_or_create_attendance_day_context(
        school=school, attendance_date=attendance_date
    )
    expected = len(context.attendance_periods)

    sessions = list(
        AttendanceSession.objects.filter(
            school=school,
            section=section,
            attendance_date=attendance_date,
            status=AttendanceSessionStatus.SUBMITTED,
        ).only("id", "period_sequence", "academic_year_id")
    )
    submitted = len({s.period_sequence for s in sessions})
    session_ids = [s.id for s in sessions]
    academic_year_id = sessions[0].academic_year_id if sessions else (
        context.academic_year_id
    )
    if academic_year_id is None:
        return 0  # لا عام مرجعي — لا صفوف (يوم بلا أي نشاط حضور)

    # عدادات العلامات لكل طالب — استعلام تجميعي واحد (لا N+1)
    marks = (
        AttendanceMark.objects.filter(session_id__in=session_ids)
        .values("student_id")
        .annotate(
            absent=Count("id", filter=Q(status=AttendanceMarkStatus.ABSENT)),
        )
    )
    marks_by_student = {m["student_id"]: m for m in marks}

    # م10 — الغياب المغطى بعذر نشط، مطابَقًا على مستوى (الطالب، الجلسة) لا بالعدد:
    # تغطية بقيت لجلسة لم يعد الطالب غائبًا فيها يجب ألا تُنسب لغياب آخر.
    from excuses.models import AbsenceExcuseCoverage, ExcuseCoverageStatus

    absent_pairs = set(
        AttendanceMark.objects.filter(
            session_id__in=session_ids, status=AttendanceMarkStatus.ABSENT
        ).values_list("student_id", "session_id")
    )
    excused_by_student: dict[int, int] = {}
    for student_id, session_id in AbsenceExcuseCoverage.objects.filter(
        attendance_session_id__in=session_ids,
        status=ExcuseCoverageStatus.ACTIVE,
    ).values_list("student_id", "attendance_session_id"):
        if (student_id, session_id) in absent_pairs:
            excused_by_student[student_id] = excused_by_student.get(student_id, 0) + 1

    # طلاب الفصل بتاريخ اليوم (تاريخيًا) + من له علامات بلا قيد ساري في فصل آخر
    enrolled_ids = set(
        enrollments_on_date(school=school, on_date=attendance_date, section=section)
        .values_list("student_id", flat=True)
    )
    marked_only = set(marks_by_student) - enrolled_ids
    if marked_only:
        elsewhere = set(
            enrollments_on_date(school=school, on_date=attendance_date)
            .filter(student_id__in=marked_only)
            .exclude(section=section)
            .values_list("student_id", flat=True)
        )
        marked_only -= elsewhere  # فصلهم الحالي بتاريخه يملك صفهم — لا ازدواج

    now = dj_timezone.now()
    students = enrolled_ids | marked_only

    def build_fields(student_id: int) -> dict:
        counters = marks_by_student.get(student_id, {})
        absent = counters.get("absent", 0)
        completeness, absence = _classify(
            expected=expected, submitted=submitted, absent=absent
        )
        # م10 — التصنيف الإداري مشتق من التغطية: excused + unexcused = absent
        excused = min(excused_by_student.get(student_id, 0), absent)
        return {
            "academic_year_id": academic_year_id,
            "section": section,
            "expected_periods": expected,
            "submitted_periods": submitted,
            "absent_periods": absent,
            "present_periods": max(submitted - absent, 0),
            "excused_absent_periods": excused,
            "unexcused_absent_periods": absent - excused,
            "completeness_status": completeness,
            "absence_status": absence,
            "calculated_at": now,
        }

    updated_fields = [
        "academic_year", "section", "expected_periods", "submitted_periods",
        "absent_periods", "present_periods",
        "excused_absent_periods", "unexcused_absent_periods",
        "completeness_status", "absence_status", "calculated_at", "updated_at",
    ]

    # ‏bulk بدل صف-بصف: استعلامات ثابتة العدد — الاعتماد المتزامن لا يدفع ثمن N طلاب
    with transaction.atomic():
        existing = {
            row.student_id: row
            for row in DailyAttendanceSummary.objects.select_for_update().filter(
                school=school, attendance_date=attendance_date, student_id__in=students
            )
        }
        to_update, to_create = [], []
        for student_id in students:
            fields = build_fields(student_id)
            row = existing.get(student_id)
            if row is None:
                to_create.append(
                    DailyAttendanceSummary(
                        school=school,
                        student_id=student_id,
                        attendance_date=attendance_date,
                        **{k: v for k, v in fields.items() if k != "updated_at"},
                    )
                )
            else:
                for key, value in fields.items():
                    setattr(row, key, value)
                row.updated_at = now
                to_update.append(row)
        if to_update:
            DailyAttendanceSummary.objects.bulk_update(to_update, updated_fields)
        if to_create:
            # سباق إنشاء متزامن نادر: تجاهل التعارض ثم تحديث الصفوف الفائزة
            DailyAttendanceSummary.objects.bulk_create(to_create, ignore_conflicts=True)
            missing_ids = [r.student_id for r in to_create]
            raced = list(
                DailyAttendanceSummary.objects.select_for_update().filter(
                    school=school,
                    attendance_date=attendance_date,
                    student_id__in=missing_ids,
                    calculated_at__lt=now,
                )
            )
            for row in raced:
                for key, value in build_fields(row.student_id).items():
                    setattr(row, key, value)
                row.updated_at = now
            if raced:
                DailyAttendanceSummary.objects.bulk_update(raced, updated_fields)
    return len(students)
