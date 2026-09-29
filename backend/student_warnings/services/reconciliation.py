"""Reconcile issued warnings after an authoritative attendance metric changes.

Issuance remains a human decision. A warning whose current metric fell below
its threshold at issue is voided, while its original snapshot stays intact.
"""

from collections import defaultdict

from django.db import transaction

from academics.models import AcademicYear
from audit.models import AuditAction
from audit.services import record_event
from documents.models import DocumentStatus, GeneratedDocument
from student_warnings.models import StudentWarning, WarningRuleType, WarningStatus
from student_warnings.selectors.eligibility import metric_for_students


def void_locked_warning(*, warning, reason, membership=None, request=None, current_value=None):
    """Void a locked warning and its linked documents in the same transaction."""
    from django.utils import timezone

    now = timezone.now()
    warning.status = WarningStatus.VOIDED
    warning.voided_by_membership = membership
    warning.voided_at = now
    warning.void_reason = reason[:300]
    warning.save(
        update_fields=[
            "status",
            "voided_by_membership",
            "voided_at",
            "void_reason",
            "updated_at",
        ]
    )

    documents = list(
        GeneratedDocument.objects.select_for_update()
        .filter(school=warning.school, warning=warning)
        .exclude(status=DocumentStatus.VOIDED)
    )
    for document in documents:
        document.status = DocumentStatus.VOIDED
        document.voided_by_membership = membership
        document.voided_at = now
        document.void_reason = reason[:300]
        document.save(
            update_fields=[
                "status",
                "voided_by_membership",
                "voided_at",
                "void_reason",
                "updated_at",
            ]
        )
        record_event(
            AuditAction.DOCUMENT_VOIDED,
            request=request,
            actor=membership.user if membership else None,
            school=warning.school,
            target_type="GeneratedDocument",
            target_id=document.id,
            metadata={
                "document_type": document.document_type,
                "warning_id": warning.id,
                "automatic": current_value is not None,
            },
        )

    record_event(
        AuditAction.STUDENT_WARNING_VOIDED,
        request=request,
        actor=membership.user if membership else None,
        school=warning.school,
        target_type="StudentWarning",
        target_id=warning.id,
        metadata={
            "student_id": warning.student_id,
            "warning_type": warning.warning_type,
            "level": warning.level,
            "automatic": current_value is not None,
            **(
                {"current_value": current_value, "threshold_at_issue": warning.threshold_at_issue}
                if current_value is not None
                else {}
            ),
        },
    )
    return warning


def reconcile_issued_warnings(
    *,
    school,
    student_ids,
    warning_type: str,
    membership=None,
    request=None,
) -> list[int]:
    """Void only warnings no longer supported by the current metric.

    Each warning uses its own academic year and original threshold, so editing
    school rules or a different year's attendance cannot revoke it.
    """
    if warning_type not in WarningRuleType.values:
        return []
    ids = set(student_ids)
    if not ids:
        return []
    with transaction.atomic():
        warnings = list(
            StudentWarning.objects.select_for_update()
            .filter(
                school=school,
                student_id__in=ids,
                warning_type=warning_type,
                status=WarningStatus.ISSUED,
            )
            .order_by("id")
        )
        if not warnings:
            return []
        years = AcademicYear.objects.in_bulk({w.academic_year_id for w in warnings})
        students_by_year: dict[int, set[int]] = defaultdict(set)
        for warning in warnings:
            students_by_year[warning.academic_year_id].add(warning.student_id)
        values = {
            year_id: metric_for_students(
                school=school,
                year=years[year_id],
                rule_type=warning_type,
                student_ids=student_ids_for_year,
            )
            for year_id, student_ids_for_year in students_by_year.items()
        }
        voided_ids = []
        for warning in warnings:
            current = values[warning.academic_year_id].get(warning.student_id, 0)
            if current >= warning.threshold_at_issue:
                continue
            label = (
                "الغياب بدون عذر"
                if warning_type == WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE
                else "التأخر الصباحي"
            )
            reason = (
                f"إلغاء تلقائي بعد تحديث {label}: القيمة الحالية {current} "
                f"أقل من حد الإنذار وقت الإصدار {warning.threshold_at_issue}."
            )
            void_locked_warning(
                warning=warning,
                reason=reason,
                membership=membership,
                request=request,
                current_value=current,
            )
            voided_ids.append(warning.id)
        return voided_ids
