"""تسجيل الإحالات في دورة الحذف النهائي (إلزام المرحلة 4.1).

الإحالة بيانات طالب بالكامل → تحذف معه. الترتيب: الأحداث ← الملاحظات ← الإحالة
(الأبناء CASCADE أصلًا لكن التسجيل الصريح يبقي العد في المعاينة دقيقًا).
`student` بـPROTECT فنسيان التسجيل يفشل صاخبًا لا صامتًا.
"""

from referrals.models import (
    StudentReferral,
    StudentReferralContribution,
    StudentReferralEvent,
)

_LABEL_EVENTS = "أحداث الإحالات"
_LABEL_CONTRIBUTIONS = "ملاحظات الإحالات"
_LABEL_REFERRALS = "إحالات الطالب"


def register_purge_steps() -> None:
    from students.services import purge as purge_service

    existing = {label for label, _ in purge_service.PURGE_STEPS}
    if _LABEL_REFERRALS in existing:
        return  # idempotent (اختبارات/إعادة تحميل)

    steps = [
        (
            _LABEL_EVENTS,
            lambda ids: StudentReferralEvent.objects.filter(
                referral__student_id__in=ids
            ),
        ),
        (
            _LABEL_CONTRIBUTIONS,
            lambda ids: StudentReferralContribution.objects.filter(
                referral__student_id__in=ids
            ),
        ),
        (_LABEL_REFERRALS, lambda ids: StudentReferral.objects.filter(student_id__in=ids)),
    ]
    for step in reversed(steps):
        purge_service.PURGE_STEPS.insert(0, step)
