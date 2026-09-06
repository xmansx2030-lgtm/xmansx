"""إنشاء مدرسة كاملة من لوحة المنصة — معاملة واحدة لا تترك نصف مستأجر (بند 55)."""

from datetime import timedelta

from django.db import transaction
from django.utils.text import slugify

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
from schools.models import School
from subscriptions.services import subscriptions as subscription_service
from subscriptions.services.school_accounts import generate_temporary_password


def _unique_slug(name: str) -> str:
    base = slugify(name, allow_unicode=False) or "school"
    slug = base
    index = 2
    while School.objects.filter(slug=slug).exists():
        slug = f"{base}-{index}"
        index += 1
    return slug


@transaction.atomic
def create_school(
    *,
    actor,
    school_name: str,
    manager_name: str,
    manager_mobile: str,
    plan_id: int | None = None,
    subscription_mode: str = "TRIAL",
    trial_days: int | None = None,
    months: int = 12,
    request=None,
) -> dict:
    """مدرسة + مدير + اشتراك في معاملة واحدة — أي فشل يلغي الكل."""
    if not (school_name or "").strip():
        raise ApiError("VALIDATION_ERROR", "اسم المدرسة مطلوب.")
    if not (manager_name or "").strip():
        raise ApiError("VALIDATION_ERROR", "اسم مدير المدرسة مطلوب.")

    try:
        mobile = normalize_mobile(manager_mobile)
    except Exception as exc:  # noqa: BLE001 — رسالة عربية موحدة بدل خطأ التحقق الخام
        raise ApiError("VALIDATION_ERROR", "رقم جوال المدير غير صالح.") from exc

    school = School.objects.create(
        name=school_name.strip(), slug=_unique_slug(school_name)
    )

    temporary_password = None
    user = User.objects.filter(mobile=mobile).first()
    if user is None:
        # حساب جديد: كلمة مرور مؤقتة تُعاد في الاستجابة فقط ولا تُخزن نصًا
        temporary_password = generate_temporary_password()
        user = User.objects.create_user(mobile=mobile, password=temporary_password)
        user.first_name = manager_name.strip()[:150]
        user.must_change_password = True
        user.save(update_fields=["first_name", "must_change_password"])

    membership = SchoolMembership.objects.create(
        user=user, school=school, status=MembershipStatus.ACTIVE
    )
    SchoolMembershipRole.objects.create(
        membership=membership, role=SchoolRole.SCHOOL_MANAGER
    )

    subscription = None
    if plan_id is not None:
        if subscription_mode == "TRIAL":
            subscription = subscription_service.start_trial(
                school=school, plan_id=plan_id, actor=actor,
                trial_days=trial_days, request=request,
            )
        else:
            subscription = subscription_service.activate(
                school=school, plan_id=plan_id, months=months, actor=actor, request=request
            )

        from subscriptions.entitlements import require_capacity
        from subscriptions.models import EntitlementKey
        from subscriptions.usage import count_active_staff

        require_capacity(
            school,
            EntitlementKey.MAX_STAFF,
            current=count_active_staff(school) - 1,
            adding=1,
        )

    record_event(
        AuditAction.PLATFORM_SCHOOL_CREATED,
        request=request, actor=actor, school=school,
        target_type="School", target_id=school.id,
        metadata={"slug": school.slug, "has_subscription": subscription is not None},
    )
    return {
        "school": school,
        "manager_membership": membership,
        "subscription": subscription,
        # يُعرض مرة واحدة للمنصة ولا يُخزن
        "temporary_password": temporary_password,
    }


def trial_window(days: int) -> timedelta:
    return timedelta(days=days)
