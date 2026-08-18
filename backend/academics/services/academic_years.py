"""خدمات العام الدراسي — التفعيل الذري وقواعد التواريخ."""

from datetime import date

from django.db import transaction

from academics.models import AcademicYear, AcademicYearStatus
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError


def _validate_range(start_date: date, end_date: date) -> None:
    if start_date >= end_date:
        raise ApiError(
            "INVALID_ACADEMIC_YEAR_RANGE",
            "تاريخ بداية العام يجب أن يسبق تاريخ نهايته.",
        )


def create_year(
    *, school, actor, name: str, start_date: date, end_date: date, request=None
) -> AcademicYear:
    _validate_range(start_date, end_date)
    year = AcademicYear.objects.create(
        school=school, name=name, start_date=start_date, end_date=end_date
    )
    record_event(
        AuditAction.ACADEMIC_YEAR_CREATED,
        request=request,
        actor=actor,
        school=school,
        target_type="AcademicYear",
        target_id=year.id,
        metadata={"name": name},
    )
    return year


def update_year(*, year: AcademicYear, actor, data: dict, request=None) -> AcademicYear:
    changed = {}
    for field in ("name", "start_date", "end_date"):
        if field in data and data[field] != getattr(year, field):
            changed[field] = {"from": str(getattr(year, field)), "to": str(data[field])}
            setattr(year, field, data[field])
    _validate_range(year.start_date, year.end_date)
    if changed:
        year.save()
        record_event(
            "ACADEMIC_YEAR_UPDATED",
            request=request,
            actor=actor,
            school=year.school,
            target_type="AcademicYear",
            target_id=year.id,
            metadata={"changed": changed},
        )
    return year


@transaction.atomic
def activate_year(*, year: AcademicYear, actor, request=None) -> AcademicYear:
    """تفعيل عام: يغلق العام النشط الحالي (إن وجد) ذريًا — قيد DB يضمن واحدًا نشطًا.

    التزامن: select_for_update يقفل صفوف أعوام المدرسة؛ وحتى لو تسابق طلبان،
    القيد uniq_active_year_per_school هو الحكم النهائي.
    """
    locked = list(
        AcademicYear.objects.select_for_update().filter(school=year.school_id)
    )
    current = next((y for y in locked if y.status == AcademicYearStatus.ACTIVE), None)
    if current is not None and current.id == year.id:
        raise ApiError("ACADEMIC_YEAR_ALREADY_ACTIVE", "هذا العام الدراسي مفعل بالفعل.", 409)
    if year.status == AcademicYearStatus.ARCHIVED:
        raise ApiError("VALIDATION_ERROR", "لا يمكن تفعيل عام مؤرشف.")

    if current is not None:
        current.status = AcademicYearStatus.CLOSED
        current.save(update_fields=["status", "updated_at"])
        record_event(
            AuditAction.ACADEMIC_YEAR_CLOSED,
            request=request,
            actor=actor,
            school=year.school,
            target_type="AcademicYear",
            target_id=current.id,
        )

    year.status = AcademicYearStatus.ACTIVE
    year.save(update_fields=["status", "updated_at"])
    record_event(
        AuditAction.ACADEMIC_YEAR_ACTIVATED,
        request=request,
        actor=actor,
        school=year.school,
        target_type="AcademicYear",
        target_id=year.id,
    )
    return year


def close_year(*, year: AcademicYear, actor, request=None) -> AcademicYear:
    if year.status != AcademicYearStatus.ACTIVE:
        raise ApiError("VALIDATION_ERROR", "لا يمكن إغلاق عام غير نشط.")
    year.status = AcademicYearStatus.CLOSED
    year.save(update_fields=["status", "updated_at"])
    record_event(
        AuditAction.ACADEMIC_YEAR_CLOSED,
        request=request,
        actor=actor,
        school=year.school,
        target_type="AcademicYear",
        target_id=year.id,
    )
    return year


def archive_year(*, year: AcademicYear, actor, request=None) -> AcademicYear:
    """أرشفة بدل الحذف المدمر (Soft Archive — ADR-010)."""
    if year.status == AcademicYearStatus.ACTIVE:
        raise ApiError("VALIDATION_ERROR", "لا يمكن أرشفة العام النشط — أغلقه أولاً.")
    year.status = AcademicYearStatus.ARCHIVED
    year.save(update_fields=["status", "updated_at"])
    record_event(
        "ACADEMIC_YEAR_ARCHIVED",
        request=request,
        actor=actor,
        school=year.school,
        target_type="AcademicYear",
        target_id=year.id,
    )
    return year
