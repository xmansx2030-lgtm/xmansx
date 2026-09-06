"""إدارة حسابات مديري المدارس من لوحة المنصة دون كشف أسرار دائمة."""

import secrets

from django.db import transaction
from django.utils import timezone

from accounts.mobile import normalize_mobile
from accounts.models import User
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from memberships.models import (
    MembershipStatus,
    SchoolMembership,
    SchoolMembershipRole,
    SchoolRole,
)
from subscriptions.entitlements import lock_school_capacity, require_capacity
from subscriptions.models import EntitlementKey
from subscriptions.usage import count_active_staff


def generate_temporary_password() -> str:
    """اعتماد قوي يعاد للعميل مرة واحدة ولا يخزن إلا كـ hash."""
    return f"Xm{secrets.token_urlsafe(12)}"


def manager_memberships(school):
    return (
        SchoolMembership.objects.filter(
            school=school,
            roles__role=SchoolRole.SCHOOL_MANAGER,
        )
        .select_related("user")
        .prefetch_related("roles")
        .distinct()
        .order_by("id")
    )


def manager_payload(membership: SchoolMembership) -> dict:
    user = membership.user
    return {
        "membership_id": membership.id,
        "user_id": user.id,
        "name": user.display_name,
        "mobile": user.mobile,
        "membership_status": membership.status,
        "account_active": user.is_active,
        "must_change_password": user.must_change_password,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "joined_at": membership.joined_at.isoformat(),
        "shared_with_other_schools": user.memberships.exclude(
            id=membership.id
        ).exists(),
    }


def get_manager(school, membership_id: int) -> SchoolMembership:
    try:
        return manager_memberships(school).get(id=membership_id)
    except SchoolMembership.DoesNotExist as exc:
        raise ApiError("NOT_FOUND", "حساب مدير المدرسة غير موجود.", 404) from exc


@transaction.atomic
def add_manager(*, school, name: str, mobile: str, actor, request=None) -> dict:
    normalized = normalize_mobile(mobile)
    clean_name = name.strip()
    if len(clean_name) < 2:
        raise ApiError("VALIDATION_ERROR", "أدخل اسم المدير كاملًا.")

    lock_school_capacity(school)
    user = User.objects.select_for_update().filter(mobile=normalized).first()
    membership = (
        SchoolMembership.objects.select_for_update()
        .filter(user=user, school=school)
        .first()
        if user
        else None
    )
    if membership and membership.roles.filter(role=SchoolRole.SCHOOL_MANAGER).exists():
        raise ApiError("MANAGER_ALREADY_EXISTS", "هذا الحساب مدير في المدرسة بالفعل.", 409)

    if membership is None or membership.status != MembershipStatus.ACTIVE:
        require_capacity(
            school,
            EntitlementKey.MAX_STAFF,
            current=count_active_staff(school),
            adding=1,
        )

    temporary_password = None
    if user is None:
        temporary_password = generate_temporary_password()
        user = User.objects.create_user(
            mobile=normalized,
            password=temporary_password,
            first_name=clean_name[:150],
            must_change_password=True,
        )

    if membership is None:
        membership = SchoolMembership.objects.create(
            user=user,
            school=school,
            status=MembershipStatus.ACTIVE,
        )
    elif membership.status != MembershipStatus.ACTIVE:
        membership.status = MembershipStatus.ACTIVE
        membership.save(update_fields=["status", "updated_at"])

    SchoolMembershipRole.objects.get_or_create(
        membership=membership,
        role=SchoolRole.SCHOOL_MANAGER,
    )
    record_event(
        AuditAction.PLATFORM_MANAGER_ADDED,
        request=request,
        actor=actor,
        school=school,
        target_type="SchoolMembership",
        target_id=membership.id,
        metadata={"new_account": temporary_password is not None},
    )
    return {
        "manager": manager_payload(get_manager(school, membership.id)),
        "temporary_password": temporary_password,
    }


@transaction.atomic
def update_manager(
    *, membership: SchoolMembership, name: str | None, mobile: str | None, actor, request=None
) -> SchoolMembership:
    user = User.objects.select_for_update().get(id=membership.user_id)
    changed = []
    if name is not None:
        clean_name = name.strip()
        if len(clean_name) < 2:
            raise ApiError("VALIDATION_ERROR", "أدخل اسم المدير كاملًا.")
        if user.display_name != clean_name:
            user.first_name = clean_name[:150]
            user.last_name = ""
            changed.append("name")

    if mobile is not None:
        normalized = normalize_mobile(mobile)
        if user.mobile != normalized:
            if User.objects.exclude(id=user.id).filter(mobile=normalized).exists():
                raise ApiError("MOBILE_ALREADY_EXISTS", "رقم الجوال مرتبط بحساب آخر.", 409)
            user.mobile = normalized
            changed.append("mobile")

    if changed:
        user.save(update_fields=["first_name", "last_name", "mobile", "updated_at"])
        record_event(
            AuditAction.PLATFORM_MANAGER_UPDATED,
            request=request,
            actor=actor,
            school=membership.school,
            target_type="SchoolMembership",
            target_id=membership.id,
            metadata={"changed_fields": changed},
        )
    return get_manager(membership.school, membership.id)


@transaction.atomic
def reset_manager_password(*, membership: SchoolMembership, actor, request=None) -> dict:
    user = User.objects.select_for_update().get(id=membership.user_id)
    temporary_password = generate_temporary_password()
    user.set_password(temporary_password)
    user.must_change_password = True
    user.save(update_fields=["password", "must_change_password", "updated_at"])
    record_event(
        AuditAction.PLATFORM_MANAGER_PASSWORD_RESET,
        request=request,
        actor=actor,
        school=membership.school,
        target_type="SchoolMembership",
        target_id=membership.id,
        metadata={"reset_at": timezone.now().isoformat()},
    )
    return {
        "manager": manager_payload(get_manager(membership.school, membership.id)),
        "temporary_password": temporary_password,
    }
