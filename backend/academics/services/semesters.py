"""خدمات الفصول الدراسية — دائمًا داخل حدود العام، وACTIVE واحد لكل مدرسة."""

from django.db import IntegrityError, transaction

from academics.models import AcademicYear, AcademicYearStatus, Semester, SemesterStatus
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError


def _validate_semester_dates(year: AcademicYear, start_date, end_date) -> None:
    if start_date > end_date:
        raise ApiError("INVALID_SEMESTER_RANGE", "تاريخ بداية الفصل يجب ألا يتجاوز نهايته.")
    if start_date < year.start_date or end_date > year.end_date:
        raise ApiError(
            "INVALID_SEMESTER_RANGE",
            "تواريخ الفصل الدراسي يجب أن تكون ضمن حدود العام الدراسي.",
        )


def _validate_no_overlap(
    *, year: AcademicYear, start_date, end_date, exclude_semester_id: int | None = None
) -> None:
    overlapping = Semester.objects.filter(
        academic_year=year,
        start_date__lte=end_date,
        end_date__gte=start_date,
    )
    if exclude_semester_id is not None:
        overlapping = overlapping.exclude(pk=exclude_semester_id)
    if overlapping.exists():
        raise ApiError(
            "SEMESTER_DATE_OVERLAP",
            "تتداخل تواريخ هذا الفصل مع فصل دراسي آخر في العام نفسه.",
        )


@transaction.atomic
def create_semester(
    *,
    year: AcademicYear,
    actor,
    name: str,
    sequence: int,
    start_date,
    end_date,
    activate: bool = False,
    request=None,
) -> Semester:
    # قفل العام يجعل فحص التداخل والإنشاء متسلسلين حتى بين طلبات متزامنة.
    year = AcademicYear.objects.select_for_update().get(pk=year.pk)
    _validate_semester_dates(year, start_date, end_date)
    _validate_no_overlap(year=year, start_date=start_date, end_date=end_date)
    try:
        with transaction.atomic():
            semester = Semester.objects.create(
                school=year.school,  # يحدده الخادم من العام — لا يقبل من العميل
                academic_year=year,
                name=name,
                sequence=sequence,
                start_date=start_date,
                end_date=end_date,
            )
    except IntegrityError as exc:
        raise ApiError("VALIDATION_ERROR", "يوجد فصل دراسي بنفس الترتيب في هذا العام.") from exc
    record_event(
        AuditAction.SEMESTER_CREATED,
        request=request,
        actor=actor,
        school=year.school,
        target_type="Semester",
        target_id=semester.id,
        metadata={"name": name, "sequence": sequence},
    )
    if activate:
        return activate_semester(semester=semester, actor=actor, request=request)
    return semester


@transaction.atomic
def update_semester(*, semester: Semester, actor, data: dict, request=None) -> Semester:
    year = AcademicYear.objects.select_for_update().get(pk=semester.academic_year_id)
    semester = (
        Semester.objects.select_for_update().select_related("academic_year").get(pk=semester.pk)
    )
    changed = {}
    for field in ("name", "sequence", "start_date", "end_date"):
        if field in data and data[field] != getattr(semester, field):
            changed[field] = {"from": str(getattr(semester, field)), "to": str(data[field])}
            setattr(semester, field, data[field])
    _validate_semester_dates(year, semester.start_date, semester.end_date)
    _validate_no_overlap(
        year=year,
        start_date=semester.start_date,
        end_date=semester.end_date,
        exclude_semester_id=semester.id,
    )
    if changed:
        try:
            with transaction.atomic():
                semester.save()
        except IntegrityError as exc:
            raise ApiError("VALIDATION_ERROR", "يوجد فصل دراسي بنفس الترتيب في هذا العام.") from exc
        record_event(
            "SEMESTER_UPDATED",
            request=request,
            actor=actor,
            school=semester.school,
            target_type="Semester",
            target_id=semester.id,
            metadata={"changed": changed},
        )
    return semester


@transaction.atomic
def activate_semester(*, semester: Semester, actor, request=None) -> Semester:
    """تفعيل فصل قادم داخل العام النشط وإغلاق الفصل السابق ذريًا."""
    year = AcademicYear.objects.select_for_update().get(pk=semester.academic_year_id)
    locked = list(
        Semester.objects.select_for_update().filter(school=semester.school_id).order_by("pk")
    )
    semester = next(item for item in locked if item.id == semester.id)
    if year.status != AcademicYearStatus.ACTIVE:
        raise ApiError(
            "SEMESTER_YEAR_NOT_ACTIVE",
            "لا يمكن تفعيل الفصل لأن العام الدراسي التابع له غير نشط.",
            409,
        )

    current = next((item for item in locked if item.status == SemesterStatus.ACTIVE), None)
    if current is not None and current.id == semester.id:
        raise ApiError("SEMESTER_ALREADY_ACTIVE", "هذا الفصل الدراسي مفعل بالفعل.", 409)
    if semester.status == SemesterStatus.CLOSED:
        raise ApiError(
            "SEMESTER_NOT_ACTIVATABLE",
            "لا يمكن إعادة تفعيل فصل دراسي مغلق.",
            409,
        )

    if current is not None:
        current.status = SemesterStatus.CLOSED
        current.save(update_fields=["status", "updated_at"])
        record_event(
            "SEMESTER_CLOSED",
            request=request,
            actor=actor,
            school=semester.school,
            target_type="Semester",
            target_id=current.id,
            metadata={"reason": "SEMESTER_ACTIVATED", "replacement_semester_id": semester.id},
        )

    semester.status = SemesterStatus.ACTIVE
    semester.save(update_fields=["status", "updated_at"])
    record_event(
        AuditAction.SEMESTER_ACTIVATED,
        request=request,
        actor=actor,
        school=semester.school,
        target_type="Semester",
        target_id=semester.id,
    )
    return semester
