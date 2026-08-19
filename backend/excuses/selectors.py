"""التصنيف الإداري الفعال للغياب + Selectors جاهزية المرحلة 11 (بلا أي إنذارات).

اليوم «كامل بعذر» = FULL و unexcused_absent_periods = 0
اليوم «كامل بدون عذر» = FULL و excused_absent_periods = 0
اليوم المختلط (excused>0 و unexcused>0) لا يحسب في أي منهما — قرار احتسابه
للإنذارات حسم في المرحلة 11: لا يحتسب (docs/WARNING_RULES.md).
"""

from datetime import date as date_cls

from django.db.models import Q, Sum

from attendance.models import (
    AttendanceMark,
    AttendanceMarkStatus,
    AttendanceSessionStatus,
    DailyAbsenceStatus,
    DailyAttendanceSummary,
)
from excuses.models import AbsenceExcuseCoverage, ExcuseCoverageStatus

EXCUSED = "EXCUSED"
UNEXCUSED = "UNEXCUSED"

# التعريف المرجعي الوحيد لليوم «كامل بدون عذر» — تستهلكه م11 كما هو (لا إعادة بناء)
UNEXCUSED_FULL_DAY_FILTER = Q(
    absence_status=DailyAbsenceStatus.FULL,
    excused_absent_periods=0,
    unexcused_absent_periods__gt=0,
)

CLASSIFICATION_LABELS = {EXCUSED: "غياب بعذر", UNEXCUSED: "غياب بدون عذر"}


def get_effective_absence_classification(*, student, attendance_session) -> str | None:
    """‏EXCUSED / UNEXCUSED إذا كانت الحالة الأصلية ABSENT — وإلا None.

    الحقيقة الخام (ABSENT) لا تتغير؛ التصنيف مشتق من التغطية النشطة فقط.
    """
    if attendance_session.status != AttendanceSessionStatus.SUBMITTED:
        return None
    is_absent = AttendanceMark.objects.filter(
        session=attendance_session,
        student=student,
        status=AttendanceMarkStatus.ABSENT,
    ).exists()
    if not is_absent:
        return None
    covered = AbsenceExcuseCoverage.objects.filter(
        attendance_session=attendance_session,
        student=student,
        status=ExcuseCoverageStatus.ACTIVE,
    ).exists()
    return EXCUSED if covered else UNEXCUSED


def excused_session_ids(*, school, student, attendance_date: date_cls) -> set[int]:
    """معرفات الجلسات المغطاة بعذر نشط لطالب في يوم — للاستخدام في تفاصيل اليوم."""
    return set(
        AbsenceExcuseCoverage.objects.filter(
            school=school,
            student=student,
            attendance_date=attendance_date,
            status=ExcuseCoverageStatus.ACTIVE,
        ).values_list("attendance_session_id", flat=True)
    )


def _summaries(*, school, student, from_date=None, to_date=None, academic_year=None):
    """‏academic_year اختياري (أضيف في م11): مرساة أدق من نطاق التواريخ عند الحاجة."""
    rows = DailyAttendanceSummary.objects.filter(school=school, student=student)
    if from_date is not None:
        rows = rows.filter(attendance_date__gte=from_date)
    if to_date is not None:
        rows = rows.filter(attendance_date__lte=to_date)
    if academic_year is not None:
        rows = rows.filter(academic_year=academic_year)
    return rows


def count_unexcused_full_absence_days(
    *, school, student, from_date=None, to_date=None, academic_year=None
) -> int:
    """أيام غياب كامل بدون أي عذر — مادة الإنذارات في المرحلة 11.

    شرط `unexcused > 0` يضمن أن اليوم مصنف فعلًا؛ صف بعدادات صفرية (بيانات
    غير محسوبة) لا يحسب هنا ولا في نظيره «بعذر».
    """
    return (
        _summaries(
            school=school, student=student, from_date=from_date, to_date=to_date,
            academic_year=academic_year,
        )
        .filter(UNEXCUSED_FULL_DAY_FILTER)
        .count()
    )


def count_excused_full_absence_days(
    *, school, student, from_date=None, to_date=None, academic_year=None
) -> int:
    return (
        _summaries(
            school=school, student=student, from_date=from_date, to_date=to_date,
            academic_year=academic_year,
        )
        .filter(
            absence_status=DailyAbsenceStatus.FULL,
            unexcused_absent_periods=0,
            excused_absent_periods__gt=0,
        )
        .count()
    )


def count_unexcused_absent_periods(
    *, school, student, from_date=None, to_date=None, academic_year=None
) -> int:
    total = _summaries(
        school=school, student=student, from_date=from_date, to_date=to_date,
        academic_year=academic_year,
    ).aggregate(total=Sum("unexcused_absent_periods"))["total"]
    return total or 0


def count_mixed_full_absence_days(
    *, school, student, from_date=None, to_date=None, academic_year=None
) -> int:
    return (
        _summaries(
            school=school, student=student, from_date=from_date, to_date=to_date,
            academic_year=academic_year,
        )
        .filter(
            Q(absence_status=DailyAbsenceStatus.FULL)
            & Q(excused_absent_periods__gt=0)
            & Q(unexcused_absent_periods__gt=0)
        )
        .count()
    )
