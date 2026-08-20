"""تسجيل الإجراءات الطلابية في دورة الحذف النهائي (إلزام م4.1 + البند 95).

الترتيب مهم: الإجراءات تحذف **قبل** الإنذارات (‏action.warning بـPROTECT)،
والمستندات قبل الإجراءات (‏document.action) — تسجيل م12 يضعها في المقدمة.
"""

from student_actions.models import StudentAction

_LABEL_ACTIONS = "الإجراءات الطلابية"


def register_purge_steps() -> None:
    from students.services import purge as purge_service

    existing = {label for label, _ in purge_service.PURGE_STEPS}
    if _LABEL_ACTIONS not in existing:
        purge_service.PURGE_STEPS.insert(
            0, (_LABEL_ACTIONS, lambda ids: StudentAction.objects.filter(student_id__in=ids))
        )
