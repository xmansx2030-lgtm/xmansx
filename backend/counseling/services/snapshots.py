"""لقطة الحالة لحظة فتحها (البنود 16-18).

تبنى من مؤشرات م13 نفسها (لا إعادة بناء) مع إضافة ما يخص الملف: سبب الإحالة،
وعدد الإنذارات وأعلاها، وعدد الإجراءات الإدارية. **بلا PII زائدة** (البند 17):
لا رقم هوية ولا بيانات ولي أمر ولا أي وصف صحي.

اللقطة ثابتة بعد الفتح؛ «الحالي» يقرأ منفصلًا وقت العرض.
"""

from referrals.models import ReferralCategory, ReferralReason
from referrals.services.snapshots import (  # مصدر واحد للمؤشرات — لا نسخة ثانية
    attendance_metrics,
    metrics_window,
)

SNAPSHOT_SCHEMA_VERSION = 1


def _placement(student) -> dict:
    enrollment = (
        student.enrollments.select_related("grade", "section")
        .order_by("-enrolled_at")
        .first()
    )
    return {
        "student_name": student.full_name,
        "grade_name": enrollment.grade.name if enrollment else None,
        "section_name": enrollment.section.name if enrollment else None,
    }


def _case_context(*, school, student) -> dict:
    from student_actions.models import StudentAction, StudentActionStatus
    from student_warnings.models import LEVEL_ORDER, StudentWarning, WarningStatus

    levels = list(
        StudentWarning.objects.filter(
            school=school, student=student, status=WarningStatus.ISSUED
        ).values_list("level", flat=True)
    )
    highest = None
    for level in levels:
        if highest is None or LEVEL_ORDER.index(level) > LEVEL_ORDER.index(highest):
            highest = level
    return {
        "warnings_count": len(levels),
        "highest_warning_level": highest,
        "actions_count": StudentAction.objects.filter(
            school=school, student=student, status=StudentActionStatus.COMPLETED
        ).count(),
    }


def build_case_snapshot(*, school, student, referral) -> dict:
    """كل ما يحتاجه المرشد لفهم الوضع لحظة البدء — ولا شيء زائد."""
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        **_placement(student),
        "referral_category": referral.category,
        "referral_category_label": ReferralCategory(referral.category).label,
        "referral_reason": referral.reason_code,
        "referral_reason_label": ReferralReason(referral.reason_code).label,
        "referral_created_at": referral.created_at.date().isoformat(),
        **_case_context(school=school, student=student),
    }
    # مؤشرات المواظبة تُدرج دائمًا في ملف المتابعة (حتى لإحالة دراسية): المرشد
    # يحتاج صورة الحضور ليقرر، بخلاف لقطة الإحالة المختصرة حسب الفئة.
    snapshot.update(attendance_metrics(school=school, student=student))
    return snapshot


def current_case_metrics(*, school, student) -> dict:
    """المؤشر الحالي — يقرأ لحظة العرض ولا يكتب في اللقطة أبدًا."""
    return {
        **attendance_metrics(school=school, student=student),
        **_case_context(school=school, student=student),
    }


__all__ = [
    "SNAPSHOT_SCHEMA_VERSION",
    "build_case_snapshot",
    "current_case_metrics",
    "metrics_window",
]
