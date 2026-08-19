"""تسجيل بيانات الأعذار في دورة الحذف النهائي (إلزام المرحلة 4.1).

حذف طالب يحذف: تغطيات الأعذار ← أهداف الأعذار ← مرفقات الأعذار (صفوف + ملفات
التخزين عبر collector) ← الأعذار نفسها. student FK هو PROTECT فنسيان التسجيل
يفشل الحذف بصوت عالٍ.
"""

from excuses.models import (
    AbsenceExcuse,
    AbsenceExcuseAttachment,
    AbsenceExcuseCoverage,
    AbsenceExcuseTarget,
)

_LABEL_COVERAGES = "تغطيات الأعذار"
_LABEL_TARGETS = "أهداف الأعذار"
_LABEL_ATTACHMENTS = "مرفقات الأعذار"
_LABEL_EXCUSES = "أعذار الغياب"

_COLLECTOR_NAME = "collect_excuse_attachment_files"


def collect_excuse_attachment_files(student) -> list:
    """ملفات مرفقات أعذار الطالب — تحذف من التخزين بعد commit حذف الصفوف."""
    return [
        attachment.file
        for attachment in AbsenceExcuseAttachment.objects.filter(
            excuse__student=student
        )
        if attachment.file
    ]


def register_purge_steps() -> None:
    from students.services import purge as purge_service

    existing = {label for label, _ in purge_service.PURGE_STEPS}
    if _LABEL_EXCUSES not in existing:
        steps = [
            (
                _LABEL_COVERAGES,
                lambda ids: AbsenceExcuseCoverage.objects.filter(student_id__in=ids),
            ),
            (
                _LABEL_TARGETS,
                lambda ids: AbsenceExcuseTarget.objects.filter(
                    excuse__student_id__in=ids
                ),
            ),
            (
                _LABEL_ATTACHMENTS,
                lambda ids: AbsenceExcuseAttachment.objects.filter(
                    excuse__student_id__in=ids
                ),
            ),
            (
                _LABEL_EXCUSES,
                lambda ids: AbsenceExcuse.objects.filter(student_id__in=ids),
            ),
        ]
        for step in reversed(steps):
            purge_service.PURGE_STEPS.insert(0, step)

    registered = {c.__name__ for c in purge_service.PURGE_STORAGE_COLLECTORS}
    if _COLLECTOR_NAME not in registered:
        purge_service.PURGE_STORAGE_COLLECTORS.append(collect_excuse_attachment_files)
