"""إنشاء المستندات وإعادة المحاولة والإلغاء (م12).

المسار الآمن (البنود 63-66):
1. صف `PENDING` + `snapshot_data` داخل transaction (المعرف والقيد الفريد يمنعان
   نسختين للنقر المزدوج قبل أن يبدأ أي توليد).
2. رسم HTML من القالب المثبت ← PDF ← تخزين خاص، **خارج** الـtransaction.
3. `READY` مع الحجم والبصمة، أو `FAILED` برمز خطأ آمن — ولا يدّعي الجاهزية أبدًا.

إعادة المحاولة (البند 67) تعيد الرسم من **اللقطة المخزنة** ولا تقرأ بيانات الطالب
الحالية، وإعادة الطباعة (البند 59) لا تولد شيئًا: تعيد الملف المخزن نفسه.
"""

import hashlib

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone as dj_timezone

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from documents.models import (
    SNAPSHOT_SCHEMA_VERSION,
    WARNING_DOCUMENT_TYPES,
    DocumentStatus,
    DocumentType,
    GeneratedDocument,
)
from documents.pdf import MIME_PDF, PdfEngineUnavailable, render_pdf
from documents.services import snapshots as snapshot_service
from documents.templates_registry import template_for, template_of
from student_warnings.models import StudentWarning, WarningStatus

DOCUMENT_NOT_FOUND = ApiError("DOCUMENT_NOT_FOUND", "المستند غير موجود.", status_code=404)


def _render(*, template, snapshot: dict) -> bytes:
    """‏HTML من قالب Django (تهريب تلقائي) ← PDF. لا مورد خارجي ولا مسار ملفات."""
    html = render_to_string(template.template_name, {"data": snapshot})
    return render_pdf(html)


def _warning_document_type(warning: StudentWarning) -> str:
    document_type = WARNING_DOCUMENT_TYPES.get(warning.level)
    if document_type is None:
        raise ApiError(
            "DOCUMENT_TEMPLATE_NOT_FOUND", "لا يوجد قالب لهذه الدرجة.", status_code=404
        )
    return document_type


def build_snapshot(
    *, school, membership, student, document_type: str, warning=None, from_date=None, to_date=None
) -> tuple[dict, object]:
    """يبني اللقطة الخادمية ويعيدها مع القالب — يستخدم للمعاينة وللإنشاء معًا."""
    template = template_for(document_type)
    if document_type in WARNING_DOCUMENT_TYPES.values():
        if warning is None:
            raise ApiError(
                "VALIDATION_ERROR", "مستند الإنذار يحتاج إنذاراً صادراً.", status_code=400
            )
        snapshot = snapshot_service.warning_snapshot(
            school=school, warning=warning, membership=membership, title=template.title
        )
    else:
        builder = snapshot_service.BUILDERS[document_type]
        if from_date is None or to_date is None:
            from_date, to_date = snapshot_service.default_range(school)
        snapshot = builder(
            school=school,
            student=student,
            membership=membership,
            from_date=from_date,
            to_date=to_date,
        )
    snapshot["template"] = {
        "key": template.key,
        "version": template.version,
        # لا ادعاء اعتماد رسمي: المصدر داخلي ما لم يوثق خلاف ذلك (البند 24)
        "source_type": template.source_type,
        "source_reference": template.source_reference,
    }
    return snapshot, template


def resolve_warning(*, school, student, warning_id) -> StudentWarning:
    warning = (
        StudentWarning.objects.filter(id=warning_id, school=school)
        .select_related("academic_year", "issued_by_membership__staff_profile",
                        "issued_by_membership__user")
        .first()
    )
    if warning is None or warning.student_id != student.id:
        raise ApiError(
            "VALIDATION_ERROR", "الإنذار غير موجود أو لا يخص هذا الطالب.", status_code=400
        )
    if warning.status != WarningStatus.ISSUED:
        raise ApiError(
            "VALIDATION_ERROR", "لا يمكن إصدار مستند لإنذار ملغى.", status_code=409
        )
    return warning


def generate_document(
    *,
    school,
    membership,
    student,
    document_type: str,
    warning_id=None,
    from_date=None,
    to_date=None,
    action=None,
    request=None,
) -> GeneratedDocument:
    if document_type not in DocumentType.values:
        raise ApiError(
            "DOCUMENT_TEMPLATE_NOT_FOUND", "نوع المستند غير معروف.", status_code=404
        )
    if student.school_id != school.id:
        raise ApiError("NOT_FOUND", "المورد المطلوب غير موجود.", status_code=404)

    warning = None
    if document_type in WARNING_DOCUMENT_TYPES.values():
        warning = resolve_warning(school=school, student=student, warning_id=warning_id)
        if _warning_document_type(warning) != document_type:
            raise ApiError(
                "VALIDATION_ERROR",
                "درجة الإنذار لا تطابق نوع المستند المطلوب.",
                status_code=400,
            )

    snapshot, template = build_snapshot(
        school=school,
        membership=membership,
        student=student,
        document_type=document_type,
        warning=warning,
        from_date=from_date,
        to_date=to_date,
    )

    try:
        with transaction.atomic():
            document = GeneratedDocument.objects.create(
                school=school,
                student=student,
                warning=warning,
                action=action,
                document_type=document_type,
                template_key=template.key,
                template_version=template.version,
                snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
                status=DocumentStatus.PENDING,
                snapshot_data=snapshot,
                generated_by_membership=membership,
            )
    except IntegrityError:
        # القيد الفريد الجزئي هو الحكم النهائي ضد النقر المزدوج (البند 77)
        raise ApiError(
            "DOCUMENT_ALREADY_EXISTS",
            "تم إنشاء هذا المستند مسبقاً.",
            status_code=409,
        ) from None

    record_event(
        AuditAction.DOCUMENT_GENERATION_REQUESTED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="GeneratedDocument",
        target_id=document.id,
        metadata={  # بلا محتوى ولا لقطة (البند 94)
            "student_id": student.id,
            "document_type": document_type,
            "warning_id": warning.id if warning else None,
        },
    )
    return _produce_file(document=document, membership=membership, request=request)


def _produce_file(*, document: GeneratedDocument, membership, request=None) -> GeneratedDocument:
    """الرسم والتخزين — خارج transaction الإنشاء (البند 63)."""
    template = template_of(document)
    try:
        pdf_bytes = _render(template=template, snapshot=document.snapshot_data)
    except PdfEngineUnavailable as exc:
        return _mark_failed(
            document=document,
            membership=membership,
            error_code="PDF_ENGINE_UNAVAILABLE",
            detail=str(exc),
            request=request,
        )
    except Exception as exc:  # قالب/بيانات — لا نسرب التفاصيل للعميل
        return _mark_failed(
            document=document,
            membership=membership,
            error_code="DOCUMENT_RENDER_FAILED",
            detail=str(exc),
            request=request,
        )

    document.file.save(f"{document.id}.pdf", ContentFile(pdf_bytes), save=False)
    document.mime_type = MIME_PDF
    document.size_bytes = len(pdf_bytes)
    document.checksum = hashlib.sha256(pdf_bytes).hexdigest()
    document.status = DocumentStatus.READY
    document.error_code = ""
    document.generated_at = dj_timezone.now()
    document.save(
        update_fields=[
            "file", "mime_type", "size_bytes", "checksum",
            "status", "error_code", "generated_at", "updated_at",
        ]
    )
    record_event(
        AuditAction.DOCUMENT_GENERATED,
        request=request,
        actor=membership.user,
        school=document.school,
        target_type="GeneratedDocument",
        target_id=document.id,
        metadata={
            "document_type": document.document_type,
            "size_bytes": document.size_bytes,
            "template": f"{document.template_key}:{document.template_version}",
        },
    )
    return document


def _mark_failed(*, document, membership, error_code: str, detail: str, request=None):
    document.status = DocumentStatus.FAILED
    document.error_code = error_code
    document.save(update_fields=["status", "error_code", "updated_at"])
    record_event(
        AuditAction.DOCUMENT_GENERATION_FAILED,
        request=request,
        actor=membership.user,
        school=document.school,
        target_type="GeneratedDocument",
        target_id=document.id,
        metadata={"document_type": document.document_type, "error_code": error_code},
    )
    # التفاصيل للسجل الداخلي فقط — لا تعاد للعميل
    from documents.pdf import logger

    logger.warning("document %s generation failed: %s — %s", document.id, error_code, detail[:200])
    return document


def retry_document(*, school, membership, document, request=None) -> GeneratedDocument:
    """إعادة توليد من اللقطة المخزنة — لا قراءة لأي بيانات حالية (البند 67)."""
    if document.school_id != school.id:
        raise DOCUMENT_NOT_FOUND
    if document.status != DocumentStatus.FAILED:
        raise ApiError(
            "DOCUMENT_NOT_READY",
            "إعادة المحاولة متاحة للمستندات التي فشل إنشاؤها فقط.",
            status_code=409,
        )
    return _produce_file(document=document, membership=membership, request=request)


def void_document(*, school, membership, document, reason: str, request=None) -> GeneratedDocument:
    if document.school_id != school.id:
        raise DOCUMENT_NOT_FOUND
    with transaction.atomic():
        locked = GeneratedDocument.objects.select_for_update().get(id=document.id)
        if locked.status == DocumentStatus.VOIDED:
            raise ApiError("DOCUMENT_NOT_FOUND", "المستند ملغى مسبقاً.", status_code=409)
        locked.status = DocumentStatus.VOIDED
        locked.voided_by_membership = membership
        locked.voided_at = dj_timezone.now()
        locked.void_reason = (reason or "")[:300]
        locked.save(
            update_fields=[
            "status", "voided_by_membership", "voided_at", "void_reason", "updated_at",
        ]
        )
    record_event(
        AuditAction.DOCUMENT_VOIDED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="GeneratedDocument",
        target_id=locked.id,
        metadata={"document_type": locked.document_type},
    )
    return locked


def open_for_download(document: GeneratedDocument):
    """يفتح الملف المخزن الأصلي — **لا توليد صامت من البيانات الحالية** (البند 60)."""
    if document.status != DocumentStatus.READY:
        raise ApiError(
            "DOCUMENT_NOT_READY", "المستند غير جاهز للتنزيل.", status_code=409
        )
    if not document.file:
        raise ApiError(
            "DOCUMENT_FILE_MISSING",
            "تعذر العثور على الملف الأصلي للمستند.",
            status_code=409,
        )
    try:
        return document.file.open("rb")
    except FileNotFoundError:
        raise ApiError(
            "DOCUMENT_FILE_MISSING",
            "تعذر العثور على الملف الأصلي للمستند.",
            status_code=409,
        ) from None
