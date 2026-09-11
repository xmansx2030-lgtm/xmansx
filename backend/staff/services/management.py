"""إدارة أدوار وحالة الموظفين — مع عزل حساب مدير المدرسة عن إدارة الموظفين.

السياسات الموثقة:
- تعيين/إزالة دور SCHOOL_MANAGER لا يتم من إدارة موظفي المدرسة.
- حساب مدير المدرسة لا يوقف أو يعاد تفعيله أو يحذف إلا من إدارة المنصة.
- إزالة آخر SCHOOL_MANAGER فعال أو إيقافه من المنصة → LAST_SCHOOL_MANAGER_REQUIRED.
- إزالة آخر دور للعضوية مرفوضة — على المدير إيقاف العضوية صراحة بدلًا من
  تركها فعالة بلا دور تشغيلي (LAST_ROLE_SUSPEND_INSTEAD).
- الإيقاف لا يمس User العالمي ولا عضوياته في مدارس أخرى (بنية العزل تضمنها).
- الحذف النهائي يزيل ملف الموظف وأدواره من المدرسة، مع إبقاء العضوية التاريخية
  بحالة LEFT حتى لا تنكسر سجلات الحضور والتدقيق المرتبطة بها.
- إعادة دعوة DECLINED إجراء صريح فقط (reinvite) — لا تلقائي عبر الاستيراد.
"""

from django.db import transaction

from accounts.models import User
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from memberships.models import (
    MembershipStatus,
    SchoolCapability,
    SchoolMembership,
    SchoolMembershipCapability,
    SchoolMembershipRole,
    SchoolRole,
)
from staff.services.credentials import initial_password_from_mobile

MANAGEABLE_ROLES = {r.value for r in SchoolRole}
SCHOOL_ASSIGNABLE_ROLES = MANAGEABLE_ROLES - {SchoolRole.SCHOOL_MANAGER}


def _manager_account_requires_platform(
    membership: SchoolMembership, actor, *, action: str
) -> None:
    """امنع لوحة المدرسة من إدارة حساب المدير حتى مع استدعاء الخدمة مباشرة."""
    if (
        SchoolRole.SCHOOL_MANAGER in membership.role_codes()
        and not actor.is_platform_admin
    ):
        raise ApiError(
            "SCHOOL_MANAGER_ACCOUNT_PLATFORM_ONLY",
            f"لا يمكن {action} حساب مدير المدرسة من إدارة الموظفين. "
            "تتم إدارته من إدارة المنصة فقط.",
            403,
        )


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
    if role == SchoolRole.SCHOOL_MANAGER:
        raise ApiError(
            "SCHOOL_MANAGER_ASSIGNMENT_PLATFORM_ONLY",
            "لا يمكن تعيين مدير آخر من إدارة موظفي المدرسة. "
            "للمدرسة مدير واحد تتم إدارة حسابه من إدارة المنصة.",
            403,
        )
    _manager_account_requires_platform(membership, actor, action="تعديل أدوار")
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
    _manager_account_requires_platform(membership, actor, action="تعديل أدوار")
    if membership.roles.count() == 1:
        raise ApiError(
            "LAST_ROLE_SUSPEND_INSTEAD",
            "هذا هو الدور الوحيد للموظف — أوقف عضويته بدلًا من إزالة آخر دور.",
            409,
        )
    role_row.delete()
    if role == SchoolRole.COUNSELOR:
        from staff.services.counselor_sections import clear_counselor_sections

        clear_counselor_sections(membership=membership)
    record_event(
        AuditAction.STAFF_ROLE_REMOVED,
        request=request, actor=actor, school=membership.school,
        target_type="SchoolMembership", target_id=membership.id,
        metadata={"role": role},
    )


@transaction.atomic
def grant_morning_attendance(*, membership: SchoolMembership, actor, request=None) -> None:
    """يمنح موظفًا نشطًا تكليف الصباح دون تعديل أدواره الأخرى."""
    if membership.status != MembershipStatus.ACTIVE:
        raise ApiError(
            "ACTIVE_STAFF_REQUIRED",
            "أعد تفعيل الموظف أولًا قبل منحه تكليف التأخر الصباحي.",
            409,
        )
    _, created = SchoolMembershipCapability.objects.get_or_create(
        membership=membership,
        capability=SchoolCapability.MORNING_ATTENDANCE,
        defaults={"granted_by": actor},
    )
    if not created:
        raise ApiError(
            "CAPABILITY_ALREADY_GRANTED",
            "هذا الموظف مكلّف بمتابعة التأخر الصباحي بالفعل.",
            409,
        )
    record_event(
        AuditAction.STAFF_CAPABILITY_GRANTED,
        request=request,
        actor=actor,
        school=membership.school,
        target_type="SchoolMembership",
        target_id=membership.id,
        metadata={"capability": SchoolCapability.MORNING_ATTENDANCE},
    )


@transaction.atomic
def revoke_morning_attendance(*, membership: SchoolMembership, actor, request=None) -> None:
    """يسحب التكليف وحده ويبقي أدوار الموظف وبقية مهامه كما هي."""
    deleted, _ = SchoolMembershipCapability.objects.filter(
        membership=membership,
        capability=SchoolCapability.MORNING_ATTENDANCE,
    ).delete()
    if not deleted:
        raise ApiError(
            "CAPABILITY_NOT_GRANTED",
            "هذا الموظف غير مكلّف بمتابعة التأخر الصباحي.",
            409,
        )
    record_event(
        AuditAction.STAFF_CAPABILITY_REVOKED,
        request=request,
        actor=actor,
        school=membership.school,
        target_type="SchoolMembership",
        target_id=membership.id,
        metadata={"capability": SchoolCapability.MORNING_ATTENDANCE},
    )


@transaction.atomic
def suspend(*, membership: SchoolMembership, actor, request=None) -> None:
    if membership.status != MembershipStatus.ACTIVE:
        raise ApiError("VALIDATION_ERROR", "العضوية ليست فعالة.")
    _manager_account_requires_platform(membership, actor, action="إيقاف")
    if _is_last_active_manager(membership):
        raise ApiError(
            "LAST_SCHOOL_MANAGER_REQUIRED",
            "لا يمكن إيقاف مدير المدرسة الوحيد. أعد تفعيل حسابه أو حدّث بياناته من إدارة المنصة.",
            409,
        )
    membership.status = MembershipStatus.SUSPENDED
    membership.save(update_fields=["status", "updated_at"])
    from staff.services.counselor_sections import clear_counselor_sections

    clear_counselor_sections(membership=membership)
    record_event(
        AuditAction.STAFF_SUSPENDED,
        request=request, actor=actor, school=membership.school,
        target_type="SchoolMembership", target_id=membership.id,
    )


@transaction.atomic
def reactivate(*, membership: SchoolMembership, actor, request=None) -> None:
    if membership.status != MembershipStatus.SUSPENDED:
        raise ApiError("VALIDATION_ERROR", "العضوية ليست موقوفة.")
    _manager_account_requires_platform(membership, actor, action="إعادة تفعيل")
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
    _manager_account_requires_platform(membership, actor, action="إعادة دعوة")
    membership.status = MembershipStatus.INVITED
    membership.save(update_fields=["status", "updated_at"])
    record_event(
        AuditAction.SCHOOL_MEMBERSHIP_INVITED,
        request=request, actor=actor, school=membership.school,
        target_type="SchoolMembership", target_id=membership.id,
        metadata={"reinvite": True},
    )


@transaction.atomic
def reset_teacher_password(*, membership: SchoolMembership, actor, request=None) -> str:
    """يعيد كلمة المعلم أو حارس البوابة ويفرض استبدالها عند الدخول التالي."""
    _manager_account_requires_platform(membership, actor, action="إعادة ضبط كلمة مرور")
    roles = membership.role_codes()
    if not {SchoolRole.TEACHER, SchoolRole.GATE_GUARD}.intersection(roles):
        raise ApiError(
            "TEACHER_ROLE_REQUIRED",
            "إعادة ضبط كلمة المرور متاحة للمعلمين وحراس البوابة فقط.",
            409,
        )
    if membership.status != MembershipStatus.ACTIVE:
        raise ApiError(
            "ACTIVE_TEACHER_REQUIRED",
            "أعد تفعيل الموظف أولًا قبل إعادة ضبط كلمة مروره.",
            409,
        )
    if membership.user_id == actor.id:
        raise ApiError(
            "SELF_PASSWORD_RESET_NOT_ALLOWED",
            "لا يمكنك إعادة ضبط كلمة مرور حسابك من إدارة الموظفين.",
            409,
        )
    user = User.objects.select_for_update().get(id=membership.user_id)
    has_other_school = (
        SchoolMembership.objects.filter(user_id=membership.user_id)
        .exclude(school_id=membership.school_id)
        .exclude(status__in=[MembershipStatus.LEFT, MembershipStatus.DECLINED])
        .exists()
    )
    if has_other_school:
        raise ApiError(
            "SHARED_ACCOUNT_PASSWORD_RESET_NOT_ALLOWED",
            "هذا الحساب مرتبط بمدرسة أخرى؛ يجب أن يغيّر المستخدم كلمة مروره بنفسه.",
            409,
        )

    temporary_password = initial_password_from_mobile(user.mobile)
    user.set_password(temporary_password)
    user.must_change_password = True
    user.save(update_fields=["password", "must_change_password", "updated_at"])
    record_event(
        AuditAction.STAFF_PASSWORD_RESET,
        request=request,
        actor=actor,
        school=membership.school,
        target_type="SchoolMembership",
        target_id=membership.id,
    )
    return temporary_password


@transaction.atomic
def delete_staff(*, profile, actor, request=None) -> None:
    """يحذف وجود الموظف من المدرسة دون المساس بحسابه العالمي أو التاريخ."""
    membership = profile.membership
    if membership.user_id == actor.id:
        raise ApiError(
            "SELF_STAFF_DELETE_NOT_ALLOWED",
            "لا يمكنك حذف حسابك الحالي. اطلب من مدير آخر تنفيذ الإجراء.",
            409,
        )
    _manager_account_requires_platform(membership, actor, action="حذف")
    if _is_last_active_manager(membership):
        raise ApiError(
            "LAST_SCHOOL_MANAGER_REQUIRED",
            "لا يمكن حذف مدير المدرسة الوحيد. حدّث بيانات حسابه من إدارة المنصة.",
            409,
        )

    membership_id = membership.id
    from staff.services.counselor_sections import clear_counselor_sections

    clear_counselor_sections(membership=membership)
    profile.delete()
    membership.roles.all().delete()
    membership.status = MembershipStatus.LEFT
    membership.save(update_fields=["status", "updated_at"])
    record_event(
        AuditAction.STAFF_DELETED,
        request=request,
        actor=actor,
        school=membership.school,
        target_type="SchoolMembership",
        target_id=membership_id,
    )
