"""تسجيل بيانات الحضور في دورة الحذف النهائي (إلزام المرحلة 4.1).

حذف طالب يحذف علاماته وسجل تعديلاته فقط — AttendanceSession تبقى لأنها تخص
الفصل والمعلم والحصة (البند 48). لا counters مخزنة في الجلسة فلا شيء يفسد.
"""

from attendance.models import AttendanceChange, AttendanceMark

_LABEL_MARKS = "علامات الحضور"
_LABEL_CHANGES = "تعديلات الحضور"


def register_purge_steps() -> None:
    from students.services import purge as purge_service

    existing = {label for label, _ in purge_service.PURGE_STEPS}
    if _LABEL_MARKS in existing:
        return  # idempotent (اختبارات/إعادة تحميل)

    # قبل خطوة القيود الدراسية — ترتيب التبعيات
    purge_service.PURGE_STEPS.insert(
        0, (_LABEL_CHANGES, lambda ids: AttendanceChange.objects.filter(student_id__in=ids))
    )
    purge_service.PURGE_STEPS.insert(
        0, (_LABEL_MARKS, lambda ids: AttendanceMark.objects.filter(student_id__in=ids))
    )
