"""تسجيل إنذارات الطلاب في الحذف النهائي (إلزام م4.1).

إنذارات الطالب بيانات مملوكة له → تحذف مع الحذف النهائي.
‏WarningRule بيانات مدرسة (عتبات) → تبقى (البند 85).
"""

from student_warnings.models import StudentWarning

_LABEL = "إنذارات الطالب"


def register_purge_steps() -> None:
    from students.services import purge as purge_service

    if _LABEL in {label for label, _ in purge_service.PURGE_STEPS}:
        return  # idempotent
    purge_service.PURGE_STEPS.insert(
        0, (_LABEL, lambda ids: StudentWarning.objects.filter(student_id__in=ids))
    )
