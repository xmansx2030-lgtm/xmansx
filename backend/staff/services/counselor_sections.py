"""إدارة توزيع الفصول على المرشدين الطلابيين."""

from django.db import transaction

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from memberships.models import SchoolRole
from staff.models import CounselorSectionAssignment
from students.models import Section


def _membership_name(membership) -> str:
    profile = getattr(membership, "staff_profile", None)
    return profile.display_name if profile else membership.user.display_name


def serialize_assignment(assignment: CounselorSectionAssignment) -> dict:
    section = assignment.section
    return {
        "id": section.id,
        "name": section.name,
        "code": section.code,
        "grade": {"id": section.grade_id, "name": section.grade.name},
    }


def counselor_sections(membership) -> list[dict]:
    assignments = sorted(
        membership.counselor_section_assignments.all(),
        key=lambda item: (item.section.grade.sequence, item.section.code),
    )
    return [serialize_assignment(assignment) for assignment in assignments]


@transaction.atomic
def set_counselor_sections(
    *,
    school,
    membership,
    section_ids: list[int] | None,
    actor,
    confirm_reassignment: bool = False,
    request=None,
) -> list[CounselorSectionAssignment]:
    """يستبدل نطاق المرشد كاملًا؛ القائمة الفارغة تعني جميع الفصول النشطة."""

    if membership.school_id != school.id or not membership.roles.filter(
        role=SchoolRole.COUNSELOR
    ).exists():
        raise ApiError(
            "INVALID_COUNSELOR_ASSIGNMENT",
            "الموظف المحدد ليس مرشدًا طلابيًا في المدرسة الحالية.",
        )

    requested_ids = list(dict.fromkeys(section_ids or []))
    sections_query = Section.objects.select_for_update().filter(
        school=school, is_active=True
    ).select_related("grade")
    if requested_ids:
        sections_query = sections_query.filter(id__in=requested_ids)
    sections = list(sections_query.order_by("grade__sequence", "code"))
    if requested_ids and len(sections) != len(requested_ids):
        raise ApiError(
            "INVALID_COUNSELOR_SECTIONS",
            "تتضمن الفصول المحددة فصلًا غير نشط أو لا يتبع المدرسة الحالية.",
            details={"field": "counselor_section_ids"},
        )

    target_ids = {section.id for section in sections}
    conflicts = list(
        # Lock the assignment rows only. ``staff_profile`` below is an optional
        # one-to-one relation, so PostgreSQL rejects an unqualified FOR UPDATE
        # because it would also try to lock the nullable side of that outer
        # join.
        CounselorSectionAssignment.objects.select_for_update(of=("self",))
        .filter(school=school, section_id__in=target_ids)
        .exclude(counselor_membership=membership)
        .select_related(
            "section__grade",
            "counselor_membership__user",
            "counselor_membership__staff_profile",
        )
        .order_by("section__grade__sequence", "section__code")
    )
    if conflicts and not confirm_reassignment:
        raise ApiError(
            "COUNSELOR_SECTION_REASSIGNMENT_REQUIRED",
            "بعض الفصول مرتبطة بمرشد آخر. أكّد نقل مسؤوليتها للمتابعة.",
            status_code=409,
            details={
                "conflicts": [
                    {
                        "section_id": assignment.section_id,
                        "section_name": (
                            f"{assignment.section.grade.name} / {assignment.section.name}"
                        ),
                        "current_counselor_name": _membership_name(
                            assignment.counselor_membership
                        ),
                    }
                    for assignment in conflicts
                ]
            },
        )

    removed_count, _ = CounselorSectionAssignment.objects.filter(
        school=school, counselor_membership=membership
    ).exclude(section_id__in=target_ids).delete()

    transferred = 0
    for section in sections:
        assignment, created = CounselorSectionAssignment.objects.update_or_create(
            section=section,
            defaults={
                "school": school,
                "counselor_membership": membership,
                "assigned_by": actor,
            },
        )
        if not created and any(item.section_id == section.id for item in conflicts):
            transferred += 1

    record_event(
        AuditAction.STAFF_PROFILE_UPDATED,
        request=request,
        actor=actor,
        school=school,
        target_type="SchoolMembership",
        target_id=membership.id,
        metadata={
            "changed_fields": ["counselor_sections"],
            "section_count": len(target_ids),
            "transferred_count": transferred,
            "removed_count": removed_count,
        },
    )
    return list(
        CounselorSectionAssignment.objects.filter(
            school=school, counselor_membership=membership
        ).select_related("section__grade")
    )


def clear_counselor_sections(*, membership) -> None:
    CounselorSectionAssignment.objects.filter(counselor_membership=membership).delete()
