"""دورة حياة العذر: تسجيل، تعديل (PENDING)، رفض، مرفقات.

الاعتماد والإلغاء وReconcile في services/coverage.py — هنا ما لا يمس التغطية.
"""

import hashlib
from datetime import date as date_cls

from django.db import transaction
from django.utils import timezone as dj_timezone

from attendance.services.day_context import get_or_create_attendance_day_context
from attendance.services.periods import school_now
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from excuses.models import (
    AbsenceExcuse,
    AbsenceExcuseAttachment,
    AbsenceExcuseStatus,
    AbsenceExcuseTarget,
)
from excuses.services.coverage import _raise_not_pending
from excuses.validators import validate_excuse_attachment
from subscriptions.entitlements import lock_school_capacity, require_storage_capacity

MAX_TARGETS_PER_EXCUSE = 60
MAX_ATTACHMENTS_PER_EXCUSE = 5


def _validate_targets(school, targets: list[dict]) -> list[dict]:
    """يتحقق من الأهداف: لا مستقبل، لا تكرار، لا تعارض يوم كامل/حصص، حصص موجودة."""
    if not targets:
        raise ApiError("EXCUSE_INVALID_TARGET", "يجب تحديد يوم أو حصة واحدة على الأقل.")
    if len(targets) > MAX_TARGETS_PER_EXCUSE:
        raise ApiError(
            "EXCUSE_INVALID_TARGET",
            f"عدد الأهداف يتجاوز الحد المسموح ({MAX_TARGETS_PER_EXCUSE}).",
        )

    today = school_now(school).date()
    seen: set[tuple[date_cls, int | None]] = set()
    full_days: set[date_cls] = set()
    period_days: set[date_cls] = set()
    for target in targets:
        day = target["attendance_date"]
        sequence = target.get("period_sequence")
        if day > today:
            raise ApiError(
                "EXCUSE_FUTURE_DATE_NOT_ALLOWED",
                "لا يمكن تسجيل عذر لتاريخ مستقبلي.",
            )
        key = (day, sequence)
        if key in seen:
            raise ApiError("EXCUSE_INVALID_TARGET", "توجد أهداف مكررة في العذر.")
        seen.add(key)
        if sequence is None:
            full_days.add(day)
        else:
            period_days.add(day)
            context = get_or_create_attendance_day_context(
                school=school, attendance_date=day
            )
            valid_sequences = {p["sequence"] for p in context.attendance_periods}
            if sequence not in valid_sequences:
                raise ApiError(
                    "EXCUSE_INVALID_TARGET",
                    "الحصة المحددة غير موجودة في جدول ذلك اليوم.",
                    details={"attendance_date": day.isoformat(), "period_sequence": sequence},
                )
    conflicting = full_days & period_days
    if conflicting:
        raise ApiError(
            "EXCUSE_INVALID_TARGET",
            "لا يمكن الجمع بين هدف يوم كامل وأهداف حصص لنفس التاريخ.",
            details={"dates": sorted(d.isoformat() for d in conflicting)},
        )
    return targets


def create_excuse(
    *, school, membership, student, reason_type: str, notes: str,
    targets: list[dict], request=None,
) -> AbsenceExcuse:
    validated = _validate_targets(school, targets)
    with transaction.atomic():
        excuse = AbsenceExcuse.objects.create(
            school=school,
            student=student,
            reason_type=reason_type,
            notes=notes[:500],
            recorded_by_membership=membership,
            recorded_at=dj_timezone.now(),
        )
        AbsenceExcuseTarget.objects.bulk_create(
            AbsenceExcuseTarget(
                school=school,
                excuse=excuse,
                attendance_date=t["attendance_date"],
                period_sequence=t.get("period_sequence"),
            )
            for t in validated
        )
        record_event(
            AuditAction.EXCUSE_CREATED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="AbsenceExcuse",
            target_id=excuse.id,
            metadata={"student_id": student.id, "targets": len(validated)},
        )
    return excuse


def update_excuse(
    *, excuse_id: int, school, membership, reason_type: str | None = None,
    notes: str | None = None, targets: list[dict] | None = None, request=None,
) -> AbsenceExcuse:
    """تعديل عذر PENDING فقط — المعتمد يلغى ويعاد تسجيله، لا يعدل بصمت."""
    with transaction.atomic():
        excuse = AbsenceExcuse.objects.select_for_update().get(id=excuse_id, school=school)
        if excuse.status != AbsenceExcuseStatus.PENDING:
            _raise_not_pending(excuse)
        update_fields = ["updated_at"]
        if reason_type is not None:
            excuse.reason_type = reason_type
            update_fields.append("reason_type")
        if notes is not None:
            excuse.notes = notes[:500]
            update_fields.append("notes")
        if targets is not None:
            validated = _validate_targets(school, targets)
            excuse.targets.all().delete()
            AbsenceExcuseTarget.objects.bulk_create(
                AbsenceExcuseTarget(
                    school=school,
                    excuse=excuse,
                    attendance_date=t["attendance_date"],
                    period_sequence=t.get("period_sequence"),
                )
                for t in validated
            )
        excuse.save(update_fields=update_fields)
        record_event(
            AuditAction.EXCUSE_UPDATED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="AbsenceExcuse",
            target_id=excuse.id,
            metadata={"targets_replaced": targets is not None},
        )
    return excuse


def reject_excuse(
    *, excuse_id: int, school, membership, reason: str, request=None
) -> AbsenceExcuse:
    with transaction.atomic():
        excuse = AbsenceExcuse.objects.select_for_update().get(id=excuse_id, school=school)
        if excuse.status != AbsenceExcuseStatus.PENDING:
            _raise_not_pending(excuse)
        excuse.status = AbsenceExcuseStatus.REJECTED
        excuse.rejected_by_membership = membership
        excuse.rejected_at = dj_timezone.now()
        excuse.rejection_reason = reason[:300]
        excuse.save(
            update_fields=[
                "status",
                "rejected_by_membership",
                "rejected_at",
                "rejection_reason",
                "updated_at",
            ]
        )
        record_event(
            AuditAction.EXCUSE_REJECTED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="AbsenceExcuse",
            target_id=excuse.id,
        )
    return excuse


def add_attachment(
    *, excuse: AbsenceExcuse, school, membership, uploaded_file, request=None
) -> AbsenceExcuseAttachment:
    if excuse.status not in (AbsenceExcuseStatus.PENDING, AbsenceExcuseStatus.APPROVED):
        raise ApiError(
            "VALIDATION_ERROR", "لا يمكن إضافة مرفق لعذر مرفوض أو ملغى.", status_code=409
        )
    mime_type = validate_excuse_attachment(uploaded_file)
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)

    with transaction.atomic():
        lock_school_capacity(school)
        require_storage_capacity(school, adding_bytes=uploaded_file.size)
        # قفل العذر: رفعان متزامنان كانا يقرآن العدد نفسه فيتجاوزان الحد معًا
        locked = AbsenceExcuse.objects.select_for_update().get(id=excuse.id)
        if locked.attachments.count() >= MAX_ATTACHMENTS_PER_EXCUSE:
            raise ApiError(
                "EXCUSE_ATTACHMENT_INVALID",
                f"عدد المرفقات يتجاوز الحد المسموح ({MAX_ATTACHMENTS_PER_EXCUSE}).",
            )
        attachment = AbsenceExcuseAttachment.objects.create(
            school=school,
            excuse=excuse,
            file=uploaded_file,
            original_filename=uploaded_file.name[:255],
            mime_type=mime_type,
            size_bytes=uploaded_file.size,
            checksum=digest.hexdigest(),
            uploaded_by_membership=membership,
        )
    record_event(
        AuditAction.EXCUSE_ATTACHMENT_UPLOADED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="AbsenceExcuseAttachment",
        target_id=attachment.id,
        metadata={"excuse_id": excuse.id, "size_bytes": attachment.size_bytes},
    )
    return attachment


def remove_attachment(
    *, attachment: AbsenceExcuseAttachment, school, membership, request=None
) -> None:
    if attachment.excuse.status != AbsenceExcuseStatus.PENDING:
        raise ApiError(
            "VALIDATION_ERROR",
            "لا يمكن حذف مرفق بعد البت في العذر.",
            status_code=409,
        )
    excuse_id = attachment.excuse_id
    stored_file = attachment.file
    # الصف أولًا ثم الملف بعد الـcommit (نفس قاعدة الحذف النهائي): العكس كان يترك
    # صفًا يشير إلى ملف مفقود فينكسر التنزيل بـ500 إذا فشل حذف الصف
    with transaction.atomic():
        attachment.delete()
        transaction.on_commit(lambda: stored_file.delete(save=False))
    record_event(
        AuditAction.EXCUSE_ATTACHMENT_REMOVED,
        request=request,
        actor=membership.user,
        school=school,
        target_type="AbsenceExcuseAttachment",
        metadata={"excuse_id": excuse_id},
    )
