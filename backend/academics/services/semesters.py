"""خدمات الفصول الدراسية — دائمًا داخل حدود العام، وACTIVE واحد لكل مدرسة."""

from django.db import IntegrityError, transaction

from academics.models import AcademicYear, Semester, SemesterStatus
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


def create_semester(
    *, year: AcademicYear, actor, name: str, sequence: int, start_date, end_date, request=None
) -> Semester:
    _validate_semester_dates(year, start_date, end_date)
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
        raise ApiError(
            "VALIDATION_ERROR", "يوجد فصل دراسي بنفس الترتيب في هذا العام."
        ) from exc
    record_event(
        AuditAction.SEMESTER_CREATED,
        request=request,
        actor=actor,
        school=year.school,
        target_type="Semester",
        target_id=semester.id,
        metadata={"name": name, "sequence": sequence},
    )
    return semester


def update_semester(*, semester: Semester, actor, data: dict, request=None) -> Semester:
    changed = {}
    for field in ("name", "sequence", "start_date", "end_date"):
        if field in data and data[field] != getattr(semester, field):
            changed[field] = {"from": str(getattr(semester, field)), "to": str(data[field])}
            setattr(semester, field, data[field])
    _validate_semester_dates(semester.academic_year, semester.start_date, semester.end_date)
    if changed:
        try:
            with transaction.atomic():
                semester.save()
        except IntegrityError as exc:
            raise ApiError(
                "VALIDATION_ERROR", "يوجد فصل دراسي بنفس الترتيب في هذا العام."
            ) from exc
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
    """تفعيل فصل: يغلق الفصل النشط الحالي ذريًا — قيد DB يضمن واحدًا نشطًا لكل مدرسة."""
    locked = list(Semester.objects.select_for_update().filter(school=semester.school_id))
    current = next((s for s in locked if s.status == SemesterStatus.ACTIVE), None)
    if current is not None and current.id == semester.id:
        raise ApiError("SEMESTER_ALREADY_ACTIVE", "هذا الفصل الدراسي مفعل بالفعل.", 409)

    if current is not None:
        current.status = SemesterStatus.CLOSED
        current.save(update_fields=["status", "updated_at"])

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
