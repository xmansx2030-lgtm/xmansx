"""لقطة حالة الطالب لحظة الإحالة (بنود 26-30).

مبدأان:
- **مختصرة حسب الفئة**: إحالة معلم لضعف دراسي لا تحتاج كل مؤشرات المواظبة.
- **بلا PII زائدة**: ممنوع رقم الهوية وجوال ولي الأمر (بند 29).

اللقطة ثابتة بعد الإنشاء؛ المؤشرات الحالية تُقرأ منفصلة وقت العرض (بند 30).
"""

from datetime import date, timedelta

from referrals.models import ReferralCategory
from students.services.attendance_profile import get_profile_summary
from students.services.morning_profile import get_morning_profile_summary

#: نافذة احتياطية حين لا يوجد عام دراسي نشط (أقل من حد ملف الطالب 366)
FALLBACK_WINDOW_DAYS = 364


def metrics_window(school) -> tuple[date, date]:
    """من بداية العام النشط حتى اليوم — وإلا نافذة سنة (لا نفشل الإحالة لغياب عام).

    مقصوصة بحد ملف الطالب: عام نشط لم يُغلق منذ أكثر من سنة كان يجعل النطاق
    يتجاوز `MAX_PROFILE_DAYS` فيرفع `ValueError` غير معالج ⇒ 500 على كل إحالة
    مواظبة وعلى قراءة تفاصيلها.
    """
    from django.utils import timezone as dj_timezone

    from students.services.attendance_profile import MAX_PROFILE_DAYS

    today = dj_timezone.localdate()
    earliest = today - timedelta(days=MAX_PROFILE_DAYS - 1)

    from academics.models import AcademicYear, AcademicYearStatus

    year = AcademicYear.objects.filter(
        school=school, status=AcademicYearStatus.ACTIVE
    ).first()
    if year is None:
        return today - timedelta(days=FALLBACK_WINDOW_DAYS), today
    return max(min(year.start_date, today), earliest), today


def _placement(student) -> dict:
    """الصف/الفصل الحالي — أسماء فقط لا معرفات حساسة."""
    enrollments = [e for e in student.enrollments.all() if e.status == "ACTIVE"]
    if not enrollments:
        enrollments = list(student.enrollments.all())
    enrollment = max(enrollments, key=lambda e: e.enrolled_at, default=None)
    return {
        "student_name": student.full_name,
        "grade_name": enrollment.grade.name if enrollment else None,
        "section_name": enrollment.section.name if enrollment else None,
    }


def _highest_warning_levels(*, school, student) -> dict:
    """أعلى مستوى إنذار سارٍ لكل نوع — None إذا لا إنذار."""
    from student_warnings.models import (
        LEVEL_ORDER,
        StudentWarning,
        WarningRuleType,
        WarningStatus,
    )

    issued = StudentWarning.objects.filter(
        school=school, student=student, status=WarningStatus.ISSUED
    ).values_list("warning_type", "level")
    highest: dict[str, str | None] = {
        WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE: None,
        WarningRuleType.MORNING_LATE_OCCURRENCES: None,
    }
    for warning_type, level in issued:
        current = highest.get(warning_type)
        if current is None or LEVEL_ORDER.index(level) > LEVEL_ORDER.index(current):
            highest[warning_type] = level
    return {
        "highest_absence_warning_level": highest[
            WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE
        ],
        "highest_late_warning_level": highest[WarningRuleType.MORNING_LATE_OCCURRENCES],
    }


def attendance_metrics(*, school, student) -> dict:
    """مؤشرات المواظبة الحالية — تُستخدم للقطة وللعرض «حاليًا» معًا."""
    from_date, to_date = metrics_window(school)
    summary = get_profile_summary(
        school=school, student=student, from_date=from_date, to_date=to_date
    )
    morning = get_morning_profile_summary(
        school=school, student=student, from_date=from_date, to_date=to_date
    )
    return {
        "full_absence_days": summary["full_absence_days"],
        "unexcused_full_absence_days": summary["unexcused_full_absence_days"],
        "partial_absence_days": summary["partial_absence_days"],
        "absent_periods": summary["absent_periods"],
        "period_late_occurrences": summary["period_late_occurrences"],
        "period_late_minutes": summary["period_late_minutes"],
        "morning_late_occurrences": morning.get("morning_late_occurrences", 0),
        "morning_late_minutes": morning.get("morning_late_minutes", 0),
        **_highest_warning_levels(school=school, student=student),
        "window_from": from_date.isoformat(),
        "window_to": to_date.isoformat(),
    }


def build_referral_snapshot(*, school, student, category: str) -> dict:
    """لقطة حسب الفئة: المواظبة تحمل المؤشرات، والبقية تكتفي بالتموضع (بند 28)."""
    snapshot = _placement(student)
    if category == ReferralCategory.ATTENDANCE:
        snapshot.update(attendance_metrics(school=school, student=student))
    return snapshot
