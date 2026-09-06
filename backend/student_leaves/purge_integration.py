"""تسجيل الاستئذانات في دورة الحذف النهائي للطالب."""

from student_leaves.models import StudentLeavePermission

_LABEL = "استئذانات الطلاب"


def register_purge_steps() -> None:
    from students.services import purge as purge_service

    existing = {label for label, _ in purge_service.PURGE_STEPS}
    if _LABEL not in existing:
        purge_service.PURGE_STEPS.insert(
            0,
            (
                _LABEL,
                lambda ids: StudentLeavePermission.objects.filter(student_id__in=ids),
            ),
        )
