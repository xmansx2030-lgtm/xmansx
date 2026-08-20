"""تسجيل المستندات المولدة في دورة الحذف النهائي (البندان 95-96).

المستندات تحذف **أولًا**: صفوفها تشير إلى الإجراءات والإنذارات، وملفات PDF تحذف
من التخزين عبر collector بعد commit حذف الصفوف. قوالب المدرسة ليست بيانات طالب
فلا تحذف (البند 98).
"""

from documents.models import GeneratedDocument

_LABEL_DOCUMENTS = "المستندات المولدة"
_COLLECTOR_NAME = "collect_generated_document_files"


def collect_generated_document_files(student) -> list:
    return [
        document.file
        for document in GeneratedDocument.objects.filter(student=student)
        if document.file
    ]


def register_purge_steps() -> None:
    from students.services import purge as purge_service

    existing = {label for label, _ in purge_service.PURGE_STEPS}
    if _LABEL_DOCUMENTS not in existing:
        purge_service.PURGE_STEPS.insert(
            0,
            (_LABEL_DOCUMENTS, lambda ids: GeneratedDocument.objects.filter(student_id__in=ids)),
        )

    registered = {c.__name__ for c in purge_service.PURGE_STORAGE_COLLECTORS}
    if _COLLECTOR_NAME not in registered:
        purge_service.PURGE_STORAGE_COLLECTORS.append(collect_generated_document_files)
