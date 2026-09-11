"""إدارة الصفوف والفصول مع حماية التاريخ وسجل تدقيق واضح."""

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from students.models import Grade, Section


def _duplicate_grade_code(*, school, grade_id: int, code: str) -> bool:
    return Grade.objects.filter(school=school, code__iexact=code).exclude(id=grade_id).exists()


def _duplicate_section_code(*, school, section_id: int, grade: Grade, code: str) -> bool:
    return (
        Section.objects.filter(school=school, grade=grade, code__iexact=code)
        .exclude(id=section_id)
        .exists()
    )


@transaction.atomic
def update_grade(*, grade: Grade, data: dict, actor, request=None) -> Grade:
    grade = Grade.objects.select_for_update().get(id=grade.id, school=grade.school)
    changed_fields: list[str] = []
    requested_code = data.get("code", grade.code)
    if _duplicate_grade_code(school=grade.school, grade_id=grade.id, code=requested_code):
        raise ApiError("GRADE_CODE_ALREADY_EXISTS", "رمز الصف مستخدم مسبقًا.", 409)

    old_active = grade.is_active
    for field in ("name", "code", "sequence", "is_active"):
        if field in data and getattr(grade, field) != data[field]:
            setattr(grade, field, data[field])
            changed_fields.append(field)

    if not changed_fields:
        return grade

    cascaded_sections = 0
    if old_active and not grade.is_active:
        cascaded_sections = grade.sections.filter(is_active=True).update(is_active=False)

    try:
        grade.save()
    except IntegrityError as exc:
        raise ApiError("GRADE_CODE_ALREADY_EXISTS", "رمز الصف مستخدم مسبقًا.", 409) from exc

    status_changed = old_active != grade.is_active
    record_event(
        AuditAction.GRADE_STATUS_CHANGED if status_changed else AuditAction.GRADE_UPDATED,
        request=request,
        actor=actor,
        school=grade.school,
        target_type="Grade",
        target_id=grade.id,
        metadata={
            "changed_fields": changed_fields,
            "is_active": grade.is_active,
            "deactivated_sections": cascaded_sections,
        },
    )
    return grade


@transaction.atomic
def update_section(*, section: Section, data: dict, actor, request=None) -> Section:
    section = (
        Section.objects.select_for_update()
        .select_related("grade")
        .get(id=section.id, school=section.school)
    )
    grade = data.get("grade", section.grade)
    requested_code = data.get("code", section.code)
    resulting_active = data.get("is_active", section.is_active)
    if resulting_active and not grade.is_active:
        raise ApiError(
            "SECTION_GRADE_INACTIVE",
            "فعّل الصف أولًا قبل إعادة تفعيل الفصل.",
            409,
        )
    if _duplicate_section_code(
        school=section.school,
        section_id=section.id,
        grade=grade,
        code=requested_code,
    ):
        raise ApiError(
            "SECTION_CODE_ALREADY_EXISTS",
            "رمز الفصل مستخدم مسبقًا داخل الصف.",
            409,
        )

    old_active = section.is_active
    changed_fields: list[str] = []
    for field in ("name", "code", "is_active"):
        if field in data and getattr(section, field) != data[field]:
            setattr(section, field, data[field])
            changed_fields.append(field)
    if grade.id != section.grade_id:
        section.grade = grade
        changed_fields.append("grade")

    if not changed_fields:
        return section

    try:
        section.save()
    except IntegrityError as exc:
        raise ApiError(
            "SECTION_CODE_ALREADY_EXISTS",
            "رمز الفصل مستخدم مسبقًا داخل الصف.",
            409,
        ) from exc

    status_changed = old_active != section.is_active
    record_event(
        AuditAction.SECTION_STATUS_CHANGED if status_changed else AuditAction.SECTION_UPDATED,
        request=request,
        actor=actor,
        school=section.school,
        target_type="Section",
        target_id=section.id,
        metadata={
            "changed_fields": changed_fields,
            "is_active": section.is_active,
            "grade_id": section.grade_id,
        },
    )
    return section


@transaction.atomic
def delete_grade(*, grade: Grade, actor, request=None) -> None:
    grade = Grade.objects.select_for_update().get(id=grade.id, school=grade.school)
    if grade.sections.exists():
        raise ApiError(
            "GRADE_HAS_SECTIONS",
            "لا يمكن حذف الصف قبل حذف فصوله. يمكنك إيقاف الصف بدلًا من ذلك.",
            409,
        )
    grade_id = grade.id
    school = grade.school
    record_event(
        AuditAction.GRADE_DELETED,
        request=request,
        actor=actor,
        school=school,
        target_type="Grade",
        target_id=grade_id,
    )
    try:
        grade.delete()
    except ProtectedError as exc:
        raise ApiError(
            "GRADE_IN_USE",
            "لا يمكن حذف الصف لوجود سجلات مرتبطة به. أوقفه للحفاظ على التاريخ.",
            409,
        ) from exc


@transaction.atomic
def delete_section(*, section: Section, actor, request=None) -> None:
    section = Section.objects.select_for_update().get(id=section.id, school=section.school)
    section_id = section.id
    school = section.school
    record_event(
        AuditAction.SECTION_DELETED,
        request=request,
        actor=actor,
        school=school,
        target_type="Section",
        target_id=section_id,
        metadata={"grade_id": section.grade_id},
    )
    try:
        section.delete()
    except ProtectedError as exc:
        raise ApiError(
            "SECTION_IN_USE",
            "لا يمكن حذف الفصل لوجود طلاب أو سجلات حضور مرتبطة به. أوقفه للحفاظ على التاريخ.",
            409,
        ) from exc
