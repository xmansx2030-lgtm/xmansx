from django.db import transaction
from django.utils import timezone

from accounts.mobile import normalize_mobile
from accounts.models import User
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from platform_team.access import get_platform_access
from platform_team.models import (
    PlatformStaffMembership,
    PlatformStaffRole,
    PlatformStaffStatus,
)
from subscriptions.services.school_accounts import generate_temporary_password


def _validate_name(name: str) -> str:
    clean = name.strip()
    if len(clean) < 2:
        raise ApiError("VALIDATION_ERROR", "أدخل اسم الموظف كاملًا.")
    return clean


def _normalize_mobile(mobile: str) -> str:
    try:
        return normalize_mobile(mobile)
    except Exception as exc:
        raise ApiError("VALIDATION_ERROR", "رقم الجوال غير صحيح.") from exc


def member_payload(membership: PlatformStaffMembership) -> dict:
    user = membership.user
    access = get_platform_access(user)
    return {
        "user_id": user.id,
        "name": user.display_name,
        "mobile": user.mobile,
        "role": membership.role,
        "role_label": membership.get_role_display(),
        "job_title": membership.job_title,
        "status": membership.status,
        "status_label": membership.get_status_display(),
        "capabilities": access["capabilities"]
        if membership.status == PlatformStaffStatus.ACTIVE
        else [],
        "must_change_password": user.must_change_password,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "created_at": membership.created_at.isoformat(),
        "school_memberships_count": user.memberships.count(),
        "is_owner": False,
    }


def owner_payload(user) -> dict:
    access = get_platform_access(user)
    return {
        "user_id": user.id,
        "name": user.display_name,
        "mobile": user.mobile,
        "role": "OWNER",
        "role_label": "مالك المنصة",
        "job_title": "المالك وصاحب الصلاحية العليا",
        "status": "ACTIVE" if user.is_active else "SUSPENDED",
        "status_label": "نشط" if user.is_active else "موقوف",
        "capabilities": access["capabilities"],
        "must_change_password": user.must_change_password,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "created_at": user.date_joined.isoformat(),
        "school_memberships_count": user.memberships.count(),
        "is_owner": True,
    }


def list_team() -> list[dict]:
    owners = [owner_payload(user) for user in User.objects.filter(is_superuser=True).order_by("id")]
    staff = [
        member_payload(row)
        for row in PlatformStaffMembership.objects.select_related("user").order_by(
            "role", "user__first_name", "user_id"
        )
    ]
    return owners + staff


@transaction.atomic
def create_member(
    *, name: str, mobile: str, role: str, job_title: str, actor, request=None
) -> dict:
    if role not in PlatformStaffRole.values:
        raise ApiError("VALIDATION_ERROR", "اختر دورًا وظيفيًا صالحًا.")
    clean_name = _validate_name(name)
    normalized = _normalize_mobile(mobile)
    user = User.objects.select_for_update().filter(mobile=normalized).first()
    if user and user.is_superuser:
        raise ApiError(
            "PLATFORM_OWNER_PROTECTED", "حساب مالك المنصة محمي ولا يمكن تحويله إلى موظف.", 409
        )
    if user and user.memberships.exists():
        raise ApiError(
            "SCHOOL_ACCOUNT_NOT_ALLOWED",
            "لحماية الفصل بين المنصة والمدارس، استخدم حسابًا مستقلًا لا يرتبط بأي مدرسة.",
            409,
        )
    if user and PlatformStaffMembership.objects.filter(user=user).exists():
        raise ApiError(
            "PLATFORM_STAFF_ALREADY_EXISTS", "هذا الحساب مضاف بالفعل إلى فريق المنصة.", 409
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
    else:
        user.first_name = clean_name[:150]
        user.last_name = ""
        user.save(update_fields=["first_name", "last_name", "updated_at"])

    membership = PlatformStaffMembership.objects.create(
        user=user,
        role=role,
        job_title=job_title.strip()[:120],
        created_by=actor,
    )
    record_event(
        AuditAction.PLATFORM_STAFF_CREATED,
        request=request,
        actor=actor,
        target_type="PlatformStaffMembership",
        target_id=membership.id,
        metadata={"role": role, "new_account": temporary_password is not None},
    )
    return {"member": member_payload(membership), "temporary_password": temporary_password}


def get_member(user_id: int, *, lock: bool = False) -> PlatformStaffMembership:
    query = PlatformStaffMembership.objects.select_related("user")
    if lock:
        query = query.select_for_update()
    try:
        return query.get(user_id=user_id)
    except PlatformStaffMembership.DoesNotExist as exc:
        if User.objects.filter(id=user_id, is_superuser=True).exists():
            raise ApiError(
                "PLATFORM_OWNER_PROTECTED",
                "حساب مالك المنصة محمي ولا يمكن تعديله من إدارة الفريق.",
                409,
            ) from exc
        raise ApiError("NOT_FOUND", "موظف المنصة غير موجود.", 404) from exc


@transaction.atomic
def update_member(*, user_id: int, data: dict, actor, request=None) -> dict:
    membership = get_member(user_id, lock=True)
    user = User.objects.select_for_update().get(id=user_id)
    identity_change_requested = "name" in data or "mobile" in data
    if identity_change_requested and user.memberships.exists():
        raise ApiError(
            "SCHOOL_ACCOUNT_NOT_ALLOWED",
            "هذا الحساب مرتبط بمدرسة؛ لا يمكن تعديل هويته من فريق المنصة.",
            409,
        )
    changed: list[str] = []
    if "name" in data:
        clean = _validate_name(str(data["name"]))
        if user.display_name != clean:
            user.first_name, user.last_name = clean[:150], ""
            changed.append("name")
    if "mobile" in data:
        normalized = _normalize_mobile(str(data["mobile"]))
        if normalized != user.mobile:
            if User.objects.exclude(id=user.id).filter(mobile=normalized).exists():
                raise ApiError("MOBILE_ALREADY_EXISTS", "رقم الجوال مرتبط بحساب آخر.", 409)
            user.mobile = normalized
            changed.append("mobile")
    if "role" in data:
        role = str(data["role"])
        if role not in PlatformStaffRole.values:
            raise ApiError("VALIDATION_ERROR", "اختر دورًا وظيفيًا صالحًا.")
        if role != membership.role:
            membership.role = role
            changed.append("role")
    if "job_title" in data:
        title = str(data["job_title"]).strip()[:120]
        if title != membership.job_title:
            membership.job_title = title
            changed.append("job_title")
    if changed:
        user.save(update_fields=["first_name", "last_name", "mobile", "updated_at"])
        membership.save(update_fields=["role", "job_title", "updated_at"])
        record_event(
            AuditAction.PLATFORM_STAFF_UPDATED,
            request=request,
            actor=actor,
            target_type="PlatformStaffMembership",
            target_id=membership.id,
            metadata={"changed_fields": changed, "role": membership.role},
        )
    return member_payload(membership)


@transaction.atomic
def run_member_action(*, user_id: int, action: str, actor, request=None) -> dict:
    membership = get_member(user_id, lock=True)
    if user_id == actor.id and action == "suspend":
        raise ApiError("SELF_SUSPEND_NOT_ALLOWED", "لا يمكنك إيقاف حسابك أثناء استخدامه.", 409)
    if user_id == actor.id and action == "reset-password":
        raise ApiError(
            "SELF_PASSWORD_RESET_NOT_ALLOWED",
            "استخدم قسم حسابي لتغيير كلمة مرور حسابك بأمان.",
            409,
        )
    if action == "suspend":
        membership.status = PlatformStaffStatus.SUSPENDED
        membership.save(update_fields=["status", "updated_at"])
        event = AuditAction.PLATFORM_STAFF_SUSPENDED
        result = {"member": member_payload(membership), "temporary_password": None}
    elif action == "reactivate":
        membership.status = PlatformStaffStatus.ACTIVE
        membership.save(update_fields=["status", "updated_at"])
        event = AuditAction.PLATFORM_STAFF_REACTIVATED
        result = {"member": member_payload(membership), "temporary_password": None}
    elif action == "reset-password":
        if membership.user.memberships.exists():
            raise ApiError(
                "SCHOOL_ACCOUNT_NOT_ALLOWED",
                "هذا الحساب مرتبط بمدرسة؛ لا يمكن إعادة كلمة مروره من فريق المنصة.",
                409,
            )
        temporary_password = generate_temporary_password()
        membership.user.set_password(temporary_password)
        membership.user.must_change_password = True
        membership.user.save(update_fields=["password", "must_change_password", "updated_at"])
        event = AuditAction.PLATFORM_STAFF_PASSWORD_RESET
        result = {"member": member_payload(membership), "temporary_password": temporary_password}
    else:
        raise ApiError("INVALID_ACTION", "الإجراء المطلوب غير مدعوم.")
    record_event(
        event,
        request=request,
        actor=actor,
        target_type="PlatformStaffMembership",
        target_id=membership.id,
        metadata={"action_at": timezone.now().isoformat()},
    )
    return result
