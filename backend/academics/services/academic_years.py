"""خدمات العام الدراسي — التفعيل الذري وقواعد التواريخ."""

from datetime import date

from django.db import transaction
from django.db.models import Q

from academics.models import AcademicYear, AcademicYearStatus, Semester, SemesterStatus
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError


def _validate_range(start_date: date, end_date: date) -> None:
    if start_date >= end_date:
        raise ApiError(
            "INVALID_ACADEMIC_YEAR_RANGE",
            "تاريخ بداية العام يجب أن يسبق تاريخ نهايته.",
        )


@transaction.atomic
def create_year(
    *,
    school,
    actor,
    name: str,
    start_date: date,
    end_date: date,
    activate: bool = False,
    request=None,
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
    if activate:
        return activate_year(year=year, actor=actor, request=request)
    return year


@transaction.atomic
def update_year(*, year: AcademicYear, actor, data: dict, request=None) -> AcademicYear:
    year = AcademicYear.objects.select_for_update().get(pk=year.pk)
    new_start_date = data.get("start_date", year.start_date)
    new_end_date = data.get("end_date", year.end_date)
    _validate_range(new_start_date, new_end_date)

    excluded_semesters = year.semesters.filter(
        Q(start_date__lt=new_start_date) | Q(end_date__gt=new_end_date)
    )
    if excluded_semesters.exists():
        raise ApiError(
            "ACADEMIC_YEAR_EXCLUDES_SEMESTERS",
            "لا يمكن تعديل حدود العام لأنها ستستبعد فصلًا دراسيًا قائمًا.",
        )

    changed = {}
    for field in ("name", "start_date", "end_date"):
        if field in data and data[field] != getattr(year, field):
            changed[field] = {"from": str(getattr(year, field)), "to": str(data[field])}
            setattr(year, field, data[field])
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
    """تفعيل عام قادم وإغلاق العام وفصله النشط السابق ذريًا.

    التزامن: select_for_update يقفل صفوف أعوام المدرسة؛ وحتى لو تسابق طلبان،
    القيد uniq_active_year_per_school هو الحكم النهائي.
    """
    locked = list(
        AcademicYear.objects.select_for_update().filter(school=year.school_id).order_by("pk")
    )
    year = next(y for y in locked if y.id == year.id)
    current = next((item for item in locked if item.status == AcademicYearStatus.ACTIVE), None)
    if current is not None and current.id == year.id:
        raise ApiError("ACADEMIC_YEAR_ALREADY_ACTIVE", "هذا العام الدراسي مفعل بالفعل.", 409)
    if year.status in (AcademicYearStatus.CLOSED, AcademicYearStatus.ARCHIVED):
        raise ApiError(
            "ACADEMIC_YEAR_NOT_ACTIVATABLE",
            "لا يمكن إعادة تفعيل عام دراسي مغلق أو مؤرشف.",
            409,
        )

    active_semesters = list(
        Semester.objects.select_for_update()
        .filter(school=year.school_id, status=SemesterStatus.ACTIVE)
        .order_by("pk")
    )
    for semester in active_semesters:
        semester.status = SemesterStatus.CLOSED
        semester.save(update_fields=["status", "updated_at"])
        record_event(
            "SEMESTER_CLOSED",
            request=request,
            actor=actor,
            school=year.school,
            target_type="Semester",
            target_id=semester.id,
            metadata={"reason": "ACADEMIC_YEAR_ACTIVATED", "replacement_year_id": year.id},
        )

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


@transaction.atomic
def close_year(*, year: AcademicYear, actor, request=None) -> AcademicYear:
    year = AcademicYear.objects.select_for_update().get(pk=year.pk)
    if year.status != AcademicYearStatus.ACTIVE:
        raise ApiError("VALIDATION_ERROR", "لا يمكن إغلاق عام غير نشط.")

    active_semesters = list(
        Semester.objects.select_for_update()
        .filter(academic_year=year, status=SemesterStatus.ACTIVE)
        .order_by("pk")
    )
    for semester in active_semesters:
        semester.status = SemesterStatus.CLOSED
        semester.save(update_fields=["status", "updated_at"])
        record_event(
            "SEMESTER_CLOSED",
            request=request,
            actor=actor,
            school=year.school,
            target_type="Semester",
            target_id=semester.id,
            metadata={"reason": "ACADEMIC_YEAR_CLOSED"},
        )

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
