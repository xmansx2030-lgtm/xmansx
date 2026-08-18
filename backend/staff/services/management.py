"""إدارة أدوار وحالة الموظفين — بحمايات آخر مدير وآخر دور.

السياسات الموثقة:
- إزالة آخر SCHOOL_MANAGER فعال أو إيقافه → LAST_SCHOOL_MANAGER_REQUIRED.
- إزالة آخر دور للعضوية مرفوضة — على المدير إيقاف العضوية صراحة بدلًا من
  تركها فعالة بلا دور تشغيلي (LAST_ROLE_SUSPEND_INSTEAD).
- الإيقاف لا يمس User العالمي ولا عضوياته في مدارس أخرى (بنية العزل تضمنها).
- إعادة دعوة DECLINED إجراء صريح فقط (reinvite) — لا تلقائي عبر الاستيراد.
"""

from django.db import transaction

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from memberships.models import (
    MembershipStatus,
    SchoolMembership,
    SchoolMembershipRole,
    SchoolRole,
)

MANAGEABLE_ROLES = {r.value for r in SchoolRole}


def _is_last_active_manager(membership: SchoolMembership) -> bool:
    has_manager_role = SchoolRole.SCHOOL_MANAGER in membership.role_codes()
    if not has_manager_role or membership.status != MembershipStatus.ACTIVE:
        return False
    others = (
        SchoolMembership.objects.filter(
            school=membership.school_id,
            status=MembershipStatus.ACTIVE,
            roles__role=SchoolRole.SCHOOL_MANAGER,
        )
        .exclude(id=membership.id)
        .exists()
    )
    return not others


@transaction.atomic
def add_role(*, membership: SchoolMembership, role: str, actor, request=None) -> None:
    if role not in MANAGEABLE_ROLES:
        raise ApiError("VALIDATION_ERROR", "الدور المحدد غير معروف.")
    _, created = SchoolMembershipRole.objects.get_or_create(membership=membership, role=role)
    if not created:
        raise ApiError("ROLE_ALREADY_ASSIGNED", "هذا الدور مسند للموظف بالفعل.", 409)
    record_event(
        AuditAction.STAFF_ROLE_ADDED,
        request=request, actor=actor, school=membership.school,
        target_type="SchoolMembership", target_id=membership.id,
        metadata={"role": role},
    )


@transaction.atomic
def remove_role(*, membership: SchoolMembership, role: str, actor, request=None) -> None:
    role_row = SchoolMembershipRole.objects.filter(membership=membership, role=role).first()
    if role_row is None:
        raise ApiError("ROLE_NOT_ASSIGNED", "هذا الدور غير مسند للموظف.", 409)
    if role == SchoolRole.SCHOOL_MANAGER and _is_last_active_manager(membership):
        raise ApiError(
            "LAST_SCHOOL_MANAGER_REQUIRED",
            "لا يمكن إزالة دور مدير المدرسة الوحيد — عيّن مديرًا آخر أولاً.",
            409,
        )
    if membership.roles.count() == 1:
        raise ApiError(
            "LAST_ROLE_SUSPEND_INSTEAD",
            "هذا هو الدور الوحيد للموظف — أوقف عضويته بدلًا من إزالة آخر دور.",
            409,
        )
    role_row.delete()
    record_event(
        AuditAction.STAFF_ROLE_REMOVED,
        request=request, actor=actor, school=membership.school,
        target_type="SchoolMembership", target_id=membership.id,
        metadata={"role": role},
    )


@transaction.atomic
def suspend(*, membership: SchoolMembership, actor, request=None) -> None:
    if membership.status != MembershipStatus.ACTIVE:
        raise ApiError("VALIDATION_ERROR", "العضوية ليست فعالة.")
    if _is_last_active_manager(membership):
        raise ApiError(
            "LAST_SCHOOL_MANAGER_REQUIRED",
            "لا يمكن إيقاف مدير المدرسة الوحيد — عيّن مديرًا آخر أولاً.",
            409,
        )
    membership.status = MembershipStatus.SUSPENDED
    membership.save(update_fields=["status", "updated_at"])
    record_event(
        AuditAction.STAFF_SUSPENDED,
        request=request, actor=actor, school=membership.school,
        target_type="SchoolMembership", target_id=membership.id,
    )


@transaction.atomic
def reactivate(*, membership: SchoolMembership, actor, request=None) -> None:
    if membership.status != MembershipStatus.SUSPENDED:
        raise ApiError("VALIDATION_ERROR", "العضوية ليست موقوفة.")
    membership.status = MembershipStatus.ACTIVE
    membership.save(update_fields=["status", "updated_at"])
    record_event(
        AuditAction.STAFF_REACTIVATED,
        request=request, actor=actor, school=membership.school,
        target_type="SchoolMembership", target_id=membership.id,
    )


@transaction.atomic
def reinvite(*, membership: SchoolMembership, actor, request=None) -> None:
    if membership.status != MembershipStatus.DECLINED:
        raise ApiError("VALIDATION_ERROR", "إعادة الدعوة متاحة فقط للدعوات المرفوضة.")
    membership.status = MembershipStatus.INVITED
    membership.save(update_fields=["status", "updated_at"])
    record_event(
        AuditAction.SCHOOL_MEMBERSHIP_INVITED,
        request=request, actor=actor, school=membership.school,
        target_type="SchoolMembership", target_id=membership.id,
        metadata={"reinvite": True},
    )
