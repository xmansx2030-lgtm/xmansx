"""Contact data is not a verified password-recovery credential."""

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from common.errors import ApiError
from common.tenant_rls import tenant_context
from memberships.models import MembershipStatus, SchoolMembership


def normalize_contact_email(value):
    if not isinstance(value, str):
        raise ApiError("INVALID_EMAIL", "أدخل بريدًا إلكترونيًا صحيحًا.")
    value = value.strip()
    try:
        if len(value) > 254:
            raise ValidationError("Too long")
        validate_email(value)
    except ValidationError as exc:
        raise ApiError("INVALID_EMAIL", "أدخل بريدًا إلكترونيًا صحيحًا.") from exc
    local, domain = value.rsplit("@", 1)
    return f"{local}@{domain.lower()}"


def initial_contact_email(user, data):
    has_school = SchoolMembership.objects.filter(user=user).exclude(
        status__in=[MembershipStatus.LEFT, MembershipStatus.DECLINED]
    ).exists()
    if "email" in data:
        return normalize_contact_email(data["email"])
    if has_school and not user.is_platform_admin and not user.email:
        raise ApiError("EMAIL_REQUIRED", "أدخل بريدك الإلكتروني لإكمال أول تسجيل دخول.")
    return user.email


def school_email_onboarding_state(user, *, enabled, has_school):
    """Owned status flags only; an old contact address is never proof of ownership."""
    if not enabled or not has_school:
        return False, False
    from parents.email_recovery_models import AccountRecoveryEmail

    # An active school is present on /me and school switching. Recovery email
    # belongs to the global account: its RLS policy deliberately hides it from
    # school-scoped reads. Read only this owner, then restore the school context.
    with tenant_context(user_id=user.pk):
        item = AccountRecoveryEmail.objects.filter(user_id=user.pk).values(
            "verified_at", "pending_email_hash",
        ).first()
    verified = bool(item and item["verified_at"])
    pending = bool(item and item["pending_email_hash"])
    return not user.must_change_password and not verified and not pending, not verified and pending
