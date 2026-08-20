"""تسجيل بيانات الإرشاد في دورة الحذف النهائي (البنود 93-96).

الترتيب: ردود المعلمين ← طلباتهم ← الإجراءات ← الأهداف ← الخطط ← الجلسات ←
أحداث الحالة ← الحالة — ثم إحالات م13 (‏`case.primary_referral` بـPROTECT فالحالة
تُحذف قبلها). عضوية الموظف **لا تحذف** مع الطالب (البند 95).
"""

from counseling.models import (
    CounselorCase,
    CounselorCaseEvent,
    CounselorFollowUpPlan,
    CounselorSession,
    FollowUpActivity,
    FollowUpGoal,
    TeacherFollowUpRequest,
    TeacherFollowUpResponse,
)

_LABEL_CASES = "الحالات الإرشادية"


def register_purge_steps() -> None:
    from students.services import purge as purge_service

    if _LABEL_CASES in {label for label, _ in purge_service.PURGE_STEPS}:
        return  # idempotent

    steps = [
        (
            "ردود متابعة المعلمين",
            lambda ids: TeacherFollowUpResponse.objects.filter(
                request__case__student_id__in=ids
            ),
        ),
        (
            "طلبات متابعة المعلمين",
            lambda ids: TeacherFollowUpRequest.objects.filter(case__student_id__in=ids),
        ),
        (
            "إجراءات المتابعة",
            lambda ids: FollowUpActivity.objects.filter(plan__case__student_id__in=ids),
        ),
        (
            "أهداف المتابعة",
            lambda ids: FollowUpGoal.objects.filter(plan__case__student_id__in=ids),
        ),
        (
            "خطط المتابعة",
            lambda ids: CounselorFollowUpPlan.objects.filter(case__student_id__in=ids),
        ),
        (
            "الجلسات الإرشادية",
            lambda ids: CounselorSession.objects.filter(case__student_id__in=ids),
        ),
        (
            "أحداث الحالات الإرشادية",
            lambda ids: CounselorCaseEvent.objects.filter(case__student_id__in=ids),
        ),
        (_LABEL_CASES, lambda ids: CounselorCase.objects.filter(student_id__in=ids)),
    ]
    for step in reversed(steps):
        purge_service.PURGE_STEPS.insert(0, step)
