"""تسجيل بيانات الحضور في دورة الحذف النهائي (إلزام المرحلة 4.1).

حذف طالب يحذف علاماته وسجل تعديلاته وملخصاته اليومية (م8) —
AttendanceSession وAttendanceDayContext تبقيان لأنهما على مستوى الفصل/المدرسة
(البند 90). لا counters مخزنة منفصلة فلا شيء يفسد بعد الحذف.
"""

from attendance.models import AttendanceChange, AttendanceMark, DailyAttendanceSummary

_LABEL_MARKS = "علامات الحضور"
_LABEL_CHANGES = "تعديلات الحضور"
_LABEL_SUMMARIES = "ملخصات الحضور اليومية"


def register_purge_steps() -> None:
    from students.services import purge as purge_service

    existing = {label for label, _ in purge_service.PURGE_STEPS}
    if _LABEL_MARKS in existing and _LABEL_SUMMARIES in existing:
        return  # idempotent (اختبارات/إعادة تحميل)

    # قبل خطوة القيود الدراسية — ترتيب التبعيات
    if _LABEL_SUMMARIES not in existing:
        purge_service.PURGE_STEPS.insert(
            0,
            (
                _LABEL_SUMMARIES,
                lambda ids: DailyAttendanceSummary.objects.filter(student_id__in=ids),
            ),
        )
    if _LABEL_MARKS not in existing:
        purge_service.PURGE_STEPS.insert(
            0,
            (_LABEL_CHANGES, lambda ids: AttendanceChange.objects.filter(student_id__in=ids)),
        )
        purge_service.PURGE_STEPS.insert(
            0, (_LABEL_MARKS, lambda ids: AttendanceMark.objects.filter(student_id__in=ids))
        )
