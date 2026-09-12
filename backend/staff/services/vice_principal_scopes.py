"""توزيع مسؤولية الطلاب على الوكلاء حسب الصف أو الفصل."""

from django.db import models, transaction

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from memberships.models import MembershipStatus, SchoolRole
from staff.models import VicePrincipalScopeAssignment
from students.models import EnrollmentStatus, Grade, Section


def _membership_name(membership) -> str:
    profile = getattr(membership, "staff_profile", None)
    return profile.display_name if profile else membership.user.display_name


def vice_principal_scopes(membership) -> list[dict]:
    assignments = list(membership.vice_principal_scope_assignments.all())
    assignments.sort(
        key=lambda item: (
            item.grade.sequence if item.grade_id else item.section.grade.sequence,
            0 if item.grade_id else 1,
            "" if item.grade_id else item.section.code,
        )
    )
    return [
        (
            {
                "kind": "GRADE",
                "id": assignment.grade_id,
                "name": assignment.grade.name,
            }
            if assignment.grade_id
            else {
                "kind": "SECTION",
                "id": assignment.section_id,
                "name": assignment.section.name,
                "grade": {
                    "id": assignment.section.grade_id,
                    "name": assignment.section.grade.name,
                },
            }
        )
        for assignment in assignments
    ]


@transaction.atomic
def set_vice_principal_scopes(
    *,
    school,
    membership,
    grade_ids: list[int] | None,
    section_ids: list[int] | None,
    actor,
    confirm_reassignment: bool = False,
    request=None,
) -> list[VicePrincipalScopeAssignment]:
    """يستبدل نطاق الوكيل كاملًا مع قفل أهداف التوزيع لمنع السباقات."""

    if membership.school_id != school.id or not membership.roles.filter(
        role=SchoolRole.VICE_PRINCIPAL
    ).exists():
        raise ApiError(
            "INVALID_VICE_PRINCIPAL_ASSIGNMENT",
            "الموظف المحدد ليس وكيلًا في المدرسة الحالية.",
        )

    requested_grade_ids = list(dict.fromkeys(grade_ids or []))
    requested_section_ids = list(dict.fromkeys(section_ids or []))

    grades = list(
        Grade.objects.select_for_update()
        .filter(school=school, is_active=True, id__in=requested_grade_ids)
        .order_by("sequence", "id")
    )
    if len(grades) != len(requested_grade_ids):
        raise ApiError(
            "INVALID_VICE_PRINCIPAL_SCOPES",
            "تتضمن الصفوف المحددة صفًا غير نشط أو لا يتبع المدرسة الحالية.",
            details={"field": "vice_principal_grade_ids"},
        )

    sections = list(
        Section.objects.select_for_update()
        .filter(
            school=school,
            is_active=True,
            grade__is_active=True,
            id__in=requested_section_ids,
        )
        .select_related("grade")
        .order_by("grade__sequence", "code", "id")
    )
    if len(sections) != len(requested_section_ids):
        raise ApiError(
            "INVALID_VICE_PRINCIPAL_SCOPES",
            "تتضمن الفصول المحددة فصلًا غير نشط أو لا يتبع المدرسة الحالية.",
            details={"field": "vice_principal_section_ids"},
        )

    # اختيار الصف يغطي فصوله؛ لا نخزن إسنادًا زائدًا للوكيل نفسه.
    grade_id_set = {grade.id for grade in grades}
    sections = [section for section in sections if section.grade_id not in grade_id_set]
    section_id_set = {section.id for section in sections}

    conflicts = list(
        VicePrincipalScopeAssignment.objects.select_for_update(of=("self",))
        .filter(school=school)
        .filter(
            models.Q(grade_id__in=grade_id_set)
            | models.Q(section_id__in=section_id_set)
        )
        .exclude(vice_principal_membership=membership)
        .select_related(
            "grade",
            "section__grade",
            "vice_principal_membership__user",
            "vice_principal_membership__staff_profile",
        )
    )
    if conflicts and not confirm_reassignment:
        raise ApiError(
            "VICE_PRINCIPAL_SCOPE_REASSIGNMENT_REQUIRED",
            "بعض الصفوف أو الفصول مرتبطة بوكيل آخر. أكّد نقل مسؤوليتها.",
            status_code=409,
            details={
                "conflicts": [
                    {
                        "kind": "GRADE" if item.grade_id else "SECTION",
                        "target_id": item.grade_id or item.section_id,
                        "target_name": (
                            item.grade.name
                            if item.grade_id
                            else f"{item.section.grade.name} / {item.section.name}"
                        ),
                        "current_vice_principal_name": _membership_name(
                            item.vice_principal_membership
                        ),
                    }
                    for item in conflicts
                ]
            },
        )

    current = VicePrincipalScopeAssignment.objects.filter(
        school=school, vice_principal_membership=membership
    )
    kept = current.filter(
        models.Q(grade_id__in=grade_id_set) | models.Q(section_id__in=section_id_set)
    )
    kept_ids = list(kept.values_list("id", flat=True))
    removed_count, _ = current.exclude(id__in=kept_ids).delete()

    # الحذف أولًا يحرر القيود الفريدة عند النقل، داخل المعاملة نفسها.
    conflict_ids = [item.id for item in conflicts]
    if conflict_ids:
        VicePrincipalScopeAssignment.objects.filter(id__in=conflict_ids).delete()

    created_count = 0
    for grade in grades:
        _, created = VicePrincipalScopeAssignment.objects.update_or_create(
            school=school,
            grade=grade,
            defaults={
                "section": None,
                "vice_principal_membership": membership,
                "assigned_by": actor,
            },
        )
        created_count += int(created)
    for section in sections:
        _, created = VicePrincipalScopeAssignment.objects.update_or_create(
            school=school,
            section=section,
            defaults={
                "grade": None,
                "vice_principal_membership": membership,
                "assigned_by": actor,
            },
        )
        created_count += int(created)

    record_event(
        AuditAction.STAFF_PROFILE_UPDATED,
        request=request,
        actor=actor,
        school=school,
        target_type="SchoolMembership",
        target_id=membership.id,
        metadata={
            "changed_fields": ["vice_principal_scopes"],
            "grade_count": len(grade_id_set),
            "section_count": len(section_id_set),
            "transferred_count": len(conflicts),
            "removed_count": removed_count,
            "created_count": created_count,
        },
    )
    return list(
        VicePrincipalScopeAssignment.objects.filter(
            school=school, vice_principal_membership=membership
        ).select_related("grade", "section__grade")
    )


def responsible_vice_for_student(*, school, student):
    """يعيد الوكيل المسؤول وبيانات مسار التوجيه؛ الفصل يتقدم على الصف."""

    enrollment = (
        student.enrollments.filter(
            school=school,
            status=EnrollmentStatus.ACTIVE,
            academic_year__status="ACTIVE",
        )
        .select_related("grade", "section")
        .order_by("-enrolled_at", "-id")
        .first()
    )
    if enrollment is None:
        return None, None

    # نفس ترتيب أقفال خدمة التوزيع (صف ثم فصل): إما ترى الإحالة التوزيع القديم
    # كاملًا أو الجديد كاملًا، ولا يمكن أن تسقط بين نقلين متزامنين.
    Grade.objects.select_for_update().get(id=enrollment.grade_id, school=school)
    Section.objects.select_for_update().get(id=enrollment.section_id, school=school)

    active_owner = {
        "vice_principal_membership__status": MembershipStatus.ACTIVE,
        "vice_principal_membership__roles__role": SchoolRole.VICE_PRINCIPAL,
    }
    assignment = (
        VicePrincipalScopeAssignment.objects.filter(
            school=school, section=enrollment.section, **active_owner
        )
        .select_related("vice_principal_membership")
        .first()
    )
    route_kind = "SECTION"
    if assignment is None:
        assignment = (
            VicePrincipalScopeAssignment.objects.filter(
                school=school, grade=enrollment.grade, **active_owner
            )
            .select_related("vice_principal_membership")
            .first()
        )
        route_kind = "GRADE"
    if assignment is None:
        return None, {
            "grade_id": enrollment.grade_id,
            "section_id": enrollment.section_id,
            "scope_kind": None,
        }
    return assignment.vice_principal_membership, {
        "grade_id": enrollment.grade_id,
        "section_id": enrollment.section_id,
        "scope_kind": route_kind,
    }


def clear_vice_principal_scopes(*, membership) -> None:
    VicePrincipalScopeAssignment.objects.filter(
        vice_principal_membership=membership
    ).delete()
