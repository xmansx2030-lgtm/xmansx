"""Purpose-bound email verification and password recovery; never mobile recovery."""

import hashlib
import hmac
import secrets
import uuid
from contextlib import contextmanager
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from accounts.models import User
from audit.services import record_event
from common.errors import ApiError
from common.security.identifiers import national_id_lookup_hash
from common.tenant_rls import can_restore_tenant_context, tenant_context
from memberships.models import SchoolMembership, SchoolMembershipRole, SchoolRole
from parents.credential_protection import has_guardian_credentials
from parents.email_recovery_models import (
    AccountRecoveryEmail,
    AccountRecoveryEmailDelivery,
)
from parents.email_recovery_models import (
    RecoveryEmailDeliveryStatus as DeliveryStatus,
)
from parents.email_recovery_models import (
    RecoveryEmailPurpose as Purpose,
)
from parents.security import decrypt_value, encrypt_value, token_hash
from platform_team.models import PlatformStaffMembership

GENERIC_RESET_MESSAGE = (
    "إذا كان الحساب مسجلاً وله بريد إلكتروني موثق، فسيتم إرسال رابط استعادة كلمة المرور إليه."
)
LINK_UNAVAILABLE_MESSAGE = "رابط الاسترداد غير صالح أو انتهت صلاحيته. اطلب رابطاً جديداً."
ACTIVE_DELIVERY_STATUSES = [
    DeliveryStatus.PENDING,
    DeliveryStatus.SENDING,
    DeliveryStatus.SUBMITTED_TO_PROVIDER,
    DeliveryStatus.UNKNOWN,
]


def normalize_recovery_email(value):
    """Trim, NFC normalize, case-fold both parts; preserve dots and plus suffixes."""
    import unicodedata

    if not isinstance(value, str) or not value.strip():
        raise ValidationError("البريد الإلكتروني مطلوب.")
    value = unicodedata.normalize("NFC", value.strip()).casefold()
    if len(value) > 254 or "\r" in value or "\n" in value:
        raise ValidationError("صيغة البريد الإلكتروني غير صحيحة.")
    try:
        validate_email(value)
    except ValidationError as exc:
        raise ValidationError("صيغة البريد الإلكتروني غير صحيحة.") from exc
    return value


def recovery_email_hash(value):
    return national_id_lookup_hash(f"parent-recovery-email:{value}")


normalize_email = normalize_recovery_email


def mask_recovery_email(value):
    if not value:
        return ""
    local, domain = value.rsplit("@", 1)
    return f"{local[:1]}***@{domain[:1]}***"


def credential_fingerprint(user):
    return hashlib.sha256(user.password.encode()).hexdigest()


def mobile_fingerprint(user):
    return hashlib.sha256(user.mobile.encode()).hexdigest()


@contextmanager
def email_scope(*, user_id=None, delivery_id=None, token_digest=None, action=""):
    """Exact own-account, worker UUID or bearer hash; no school/platform bypass."""
    names = ("app.parent_email_delivery", "app.parent_email_token", "app.parent_email_action")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting(%s,true),current_setting(%s,true),current_setting(%s,true)",
            names,
        )
        previous = cursor.fetchone()
        for name, value in zip(
            names, (str(delivery_id or ""), token_digest or "", action), strict=True
        ):
            cursor.execute("SELECT set_config(%s,%s,false)", [name, value])
    try:
        with tenant_context(user_id=user_id):
            yield
    finally:
        if can_restore_tenant_context():
            with connection.cursor() as cursor:
                for name, value in zip(names, previous, strict=True):
                    cursor.execute("SELECT set_config(%s,%s,false)", [name, value or ""])


def owns_parent_account(user):
    return has_guardian_credentials(user.id)


def eligible_for_password_recovery(user):
    """Teacher+parent is allowed; every privileged school/platform role fails closed."""
    if (
        not user.is_active
        or user.must_change_password
        or not user.has_usable_password()
        or user.is_superuser
        or user.is_staff
    ):
        return False
    if PlatformStaffMembership.objects.filter(user_id=user.id).exists():
        return False
    if (
        SchoolMembershipRole.objects.filter(membership__user_id=user.id)
        .exclude(role=SchoolRole.TEACHER)
        .exists()
    ):
        return False
    return owns_parent_account(user)


def require_verified_recovery_email(user):
    # A fresh owned SELECT needs only tenant identity, never worker/action GUCs.
    with tenant_context(user_id=user.id):
        verified = AccountRecoveryEmail.objects.filter(
            user_id=user.id,
            verified_at__isnull=False,
            current_email_hash__isnull=False,
        ).exists()
    if not verified:
        raise ApiError(
            "EMAIL_VERIFICATION_REQUIRED", "أكمل توثيق بريد الاسترداد أولاً.", status_code=403
        )


def email_status(user):
    with email_scope(user_id=user.id):
        item = AccountRecoveryEmail.objects.filter(user_id=user.id).first()
        latest = (
            AccountRecoveryEmailDelivery.objects.filter(
                user_id=user.id,
                purpose=Purpose.RECOVERY_EMAIL_VERIFICATION,
            )
            .order_by("-created_at")
            .first()
        )
        return {
            "verified": bool(item and item.verified_at),
            "verification_required": not bool(item and item.verified_at),
            "email_masked": mask_recovery_email(
                decrypt_value(item.current_email_encrypted) if item and item.verified_at else ""
            ),
            "pending_email_masked": mask_recovery_email(
                decrypt_value(item.pending_email_encrypted)
                if item and item.pending_email_encrypted
                else ""
            ),
            "delivery_status": latest.status if latest else None,
            "enabled": settings.PARENT_RECOVERY_EMAIL_ENABLED,
        }


def _queue_delivery(user, item, purpose):
    now = timezone.now()
    recent = AccountRecoveryEmailDelivery.objects.filter(
        user_id=user.id,
        purpose=purpose,
        created_at__gt=now - timedelta(seconds=60),
        revoked_at__isnull=True,
        consumed_at__isnull=True,
    ).exists()
    if recent:
        return None
    AccountRecoveryEmailDelivery.objects.filter(
        user_id=user.id,
        purpose=purpose,
        revoked_at__isnull=True,
        consumed_at__isnull=True,
    ).update(revoked_at=now)
    delivery = AccountRecoveryEmailDelivery.objects.create(
        user=user,
        recovery_email=item,
        purpose=purpose,
        email_hash=(
            item.pending_email_hash
            if purpose == Purpose.RECOVERY_EMAIL_VERIFICATION
            else item.current_email_hash
        ),
        email_revision=(
            item.pending_revision
            if purpose == Purpose.RECOVERY_EMAIL_VERIFICATION
            else item.revision
        ),
        password_fingerprint=credential_fingerprint(user),
        mobile_fingerprint=mobile_fingerprint(user),
    )
    if settings.PARENT_RECOVERY_EMAIL_ENABLED:
        transaction.on_commit(lambda delivery_id=str(delivery.id): _dispatch(delivery_id))
    return delivery


def _dispatch(delivery_id):
    from parents.email_recovery_tasks import send_parent_recovery_email

    try:
        send_parent_recovery_email.delay(delivery_id)
    except Exception:
        # Broker failure is known-before-provider and safe to diagnose without secrets.
        finalize_email_delivery(
            delivery_id, DeliveryStatus.FAILED, error_code="EMAIL_QUEUE_UNAVAILABLE"
        )


def _enroll_locked(user, email, *, initial_only=False):
    item, _ = AccountRecoveryEmail.objects.select_for_update().get_or_create(user=user)
    if initial_only and (item.verified_at or item.pending_email_hash):
        return item
    lookup = recovery_email_hash(email)
    if item.current_email_hash == lookup and item.verified_at:
        return item
    if item.pending_email_hash != lookup:
        item.pending_email_encrypted = encrypt_value(email)
        item.pending_email_hash = lookup
        item.pending_revision += 1
        item.save(
            update_fields=[
                "pending_email_encrypted",
                "pending_email_hash",
                "pending_revision",
                "updated_at",
            ]
        )
        AccountRecoveryEmailDelivery.objects.filter(
            user_id=user.id, revoked_at__isnull=True, consumed_at__isnull=True
        ).update(revoked_at=timezone.now())
    _queue_delivery(user, item, Purpose.RECOVERY_EMAIL_VERIFICATION)
    return item


def enroll_recovery_email(user, email, current_password):
    email = normalize_recovery_email(email)
    with email_scope(user_id=user.id, action="ENROLL"), transaction.atomic():
        fresh = User.objects.select_for_update().get(id=user.id)
        if (
            not fresh.is_active
            or fresh.must_change_password
            or not hmac.compare_digest(fresh.password, user.password)
            or not fresh.check_password(current_password)
            or not owns_parent_account(fresh)
        ):
            raise ApiError(
                "RECOVERY_PROOF_REQUIRED", "تحقق من كلمة المرور الحالية للحساب.", status_code=403
            )
        _enroll_locked(fresh, email)
        record_event(
            "PARENT_RECOVERY_EMAIL_REQUESTED", actor=fresh, target_type="User", target_id=fresh.id
        )
    return email_status(fresh)


def enroll_registration_email(user, email, *, new_account=False):
    """Activation already locked/proved User. Never replace existing recovery credentials."""
    if not email or not new_account:
        return
    email = normalize_recovery_email(email)
    with email_scope(user_id=user.id, action="ENROLL"), transaction.atomic():
        fresh = User.objects.select_for_update().get(id=user.id)
        if not owns_parent_account(fresh):
            raise ApiError("RECOVERY_PROOF_REQUIRED", "أكمل تفعيل الحساب أولاً.", status_code=403)
        _enroll_locked(fresh, email, initial_only=True)


def resend_verification(user):
    with email_scope(user_id=user.id, action="ENROLL"), transaction.atomic():
        fresh = User.objects.select_for_update().get(id=user.id)
        if (
            not fresh.is_active
            or fresh.must_change_password
            or not hmac.compare_digest(fresh.password, user.password)
        ):
            raise ApiError(
                "RECOVERY_PROOF_REQUIRED", "سجل الدخول إلى الحساب مجدداً.", status_code=403
            )
        item = AccountRecoveryEmail.objects.select_for_update().filter(user_id=user.id).first()
        if item and item.pending_email_hash:
            _queue_delivery(fresh, item, Purpose.RECOVERY_EMAIL_VERIFICATION)
    return email_status(fresh)


def request_password_recovery(mobile):
    user = User.objects.filter(mobile=mobile).first()
    if user is None:
        return
    with email_scope(user_id=user.id, action="REQUEST"), transaction.atomic():
        user = User.objects.select_for_update().get(id=user.id)
        if not eligible_for_password_recovery(user):
            return
        item = (
            AccountRecoveryEmail.objects.select_for_update()
            .filter(
                user_id=user.id,
                verified_at__isnull=False,
            )
            .first()
        )
        if item:
            _queue_delivery(user, item, Purpose.PASSWORD_RESET)


def _delivery_current(delivery, item, user):
    if (
        delivery.revoked_at
        or delivery.consumed_at
        or not user.is_active
        or user.must_change_password
        or not hmac.compare_digest(delivery.password_fingerprint, credential_fingerprint(user))
        or not hmac.compare_digest(delivery.mobile_fingerprint, mobile_fingerprint(user))
    ):
        return False
    if delivery.purpose == Purpose.RECOVERY_EMAIL_VERIFICATION:
        return (
            bool(item.pending_email_hash)
            and delivery.email_hash == item.pending_email_hash
            and delivery.email_revision == item.pending_revision
        )
    return (
        bool(item.verified_at)
        and delivery.email_hash == item.current_email_hash
        and delivery.email_revision == item.revision
        and eligible_for_password_recovery(user)
    )


def prepare_email_delivery(delivery_id):
    try:
        delivery_id = uuid.UUID(str(delivery_id))
    except (ValueError, TypeError):
        return None
    with email_scope(delivery_id=delivery_id, action="DELIVER"), transaction.atomic():
        index = (
            AccountRecoveryEmailDelivery.objects.filter(id=delivery_id).values("user_id").first()
        )
        if index is None:
            return None
        # The worker's exact UUID permits only this global account, not other accounts.
        with email_scope(user_id=index["user_id"], delivery_id=delivery_id, action="DELIVER"):
            user = User.objects.select_for_update().get(id=index["user_id"])
            item = AccountRecoveryEmail.objects.select_for_update().get(user_id=user.id)
            delivery = AccountRecoveryEmailDelivery.objects.select_for_update().get(id=delivery_id)
            if delivery.status == DeliveryStatus.SENDING:
                if delivery.attempt_started_at < timezone.now() - timedelta(minutes=10):
                    delivery.status = DeliveryStatus.UNKNOWN
                    delivery.error_code = "DELIVERY_STATE_UNKNOWN"
                    delivery.save(update_fields=["status", "error_code", "updated_at"])
                return None
            if delivery.status != DeliveryStatus.PENDING:
                return None
            if not settings.PARENT_RECOVERY_EMAIL_ENABLED or not _delivery_current(
                delivery, item, user
            ):
                delivery.status = DeliveryStatus.CANCELLED
                delivery.revoked_at = timezone.now()
                delivery.save(update_fields=["status", "revoked_at", "updated_at"])
                return None
            raw_token = secrets.token_urlsafe(32)
            delivery.token_hash = token_hash(raw_token)
            delivery.attempt_started_at = timezone.now()
            ttl = (
                settings.PARENT_RECOVERY_VERIFY_TTL_SECONDS
                if delivery.purpose == Purpose.RECOVERY_EMAIL_VERIFICATION
                else settings.PARENT_RECOVERY_RESET_TTL_SECONDS
            )
            delivery.expires_at = delivery.attempt_started_at + timedelta(seconds=ttl)
            delivery.status = DeliveryStatus.SENDING
            delivery.save(
                update_fields=[
                    "token_hash",
                    "attempt_started_at",
                    "expires_at",
                    "status",
                    "updated_at",
                ]
            )
            address = (
                item.pending_email_encrypted
                if delivery.purpose == Purpose.RECOVERY_EMAIL_VERIFICATION
                else item.current_email_encrypted
            )
            return {
                "delivery_id": str(delivery.id),
                "user_id": user.id,
                "recipient": decrypt_value(address),
                "purpose": delivery.purpose,
                "token": raw_token,
                "expires_at": delivery.expires_at,
            }


@contextmanager
def email_delivery_send_scope(delivery_id):
    with email_scope(delivery_id=delivery_id, action="DELIVER"), transaction.atomic():
        index = (
            AccountRecoveryEmailDelivery.objects.filter(id=delivery_id).values("user_id").first()
        )
        if index is None:
            yield False
            return
        with email_scope(user_id=index["user_id"], delivery_id=delivery_id, action="DELIVER"):
            user = User.objects.select_for_update().get(id=index["user_id"])
            item = AccountRecoveryEmail.objects.select_for_update().get(user_id=user.id)
            delivery = AccountRecoveryEmailDelivery.objects.select_for_update().get(id=delivery_id)
            permitted = (
                settings.PARENT_RECOVERY_EMAIL_ENABLED
                and delivery.status == DeliveryStatus.SENDING
                and delivery.expires_at > timezone.now()
                and _delivery_current(delivery, item, user)
            )
            if not permitted:
                delivery.status = DeliveryStatus.CANCELLED
                delivery.revoked_at = timezone.now()
                delivery.save(update_fields=["status", "revoked_at", "updated_at"])
            yield permitted


def finalize_email_delivery(delivery_id, status, provider_reference="", error_code=""):
    if status not in {
        DeliveryStatus.SUBMITTED_TO_PROVIDER,
        DeliveryStatus.FAILED,
        DeliveryStatus.UNKNOWN,
    }:
        raise ValueError("Invalid recovery delivery result")
    with email_scope(delivery_id=delivery_id, action="DELIVER"), transaction.atomic():
        index = (
            AccountRecoveryEmailDelivery.objects.filter(id=delivery_id).values("user_id").first()
        )
        if not index:
            return
        with email_scope(user_id=index["user_id"], delivery_id=delivery_id, action="DELIVER"):
            User.objects.select_for_update().get(id=index["user_id"])
            delivery = AccountRecoveryEmailDelivery.objects.select_for_update().get(id=delivery_id)
            if delivery.status not in {DeliveryStatus.PENDING, DeliveryStatus.SENDING}:
                return
            delivery.status = status
            delivery.provider_reference = provider_reference[:100]
            delivery.error_code = error_code[:60]
            if status == DeliveryStatus.FAILED:
                delivery.revoked_at = timezone.now()
            delivery.save(
                update_fields=[
                    "status",
                    "provider_reference",
                    "error_code",
                    "revoked_at",
                    "updated_at",
                ]
            )


def _token_delivery(token, purpose, *, actor=None, action="CHECK"):
    digest = token_hash(token)
    with email_scope(token_digest=digest, action=action):
        index = (
            AccountRecoveryEmailDelivery.objects.filter(token_hash=digest, purpose=purpose)
            .values("id", "user_id")
            .first()
        )
    if not index or (actor is not None and index["user_id"] != actor.id):
        raise ApiError("RECOVERY_TOKEN_INVALID", LINK_UNAVAILABLE_MESSAGE)
    return index, digest


@contextmanager
def _locked_token(token, purpose, *, actor=None, action="CHECK"):
    index, digest = _token_delivery(token, purpose, actor=actor, action=action)
    with (
        email_scope(user_id=index["user_id"], token_digest=digest, action=action),
        transaction.atomic(),
    ):
        user = User.objects.select_for_update().get(id=index["user_id"])
        if purpose == Purpose.PASSWORD_RESET:
            # A role may be added to an existing employee without updating User.
            # Lock both FK parents and existing roles before the fresh privilege read.
            membership_ids = list(
                SchoolMembership.objects.select_for_update(of=("self",))
                .filter(user_id=user.id)
                .order_by("id")
                .values_list("id", flat=True)
            )
            list(
                SchoolMembershipRole.objects.select_for_update(of=("self",))
                .filter(membership_id__in=membership_ids)
                .order_by("id")
                .values_list("id", flat=True)
            )
        item = AccountRecoveryEmail.objects.select_for_update().get(user_id=user.id)
        delivery = AccountRecoveryEmailDelivery.objects.select_for_update().get(id=index["id"])
        if delivery.consumed_at:
            raise ApiError("RECOVERY_TOKEN_USED", LINK_UNAVAILABLE_MESSAGE)
        if delivery.expires_at is None or delivery.expires_at <= timezone.now():
            raise ApiError("RECOVERY_TOKEN_EXPIRED", LINK_UNAVAILABLE_MESSAGE)
        if delivery.status not in {
            DeliveryStatus.SENDING,
            DeliveryStatus.SUBMITTED_TO_PROVIDER,
            DeliveryStatus.UNKNOWN,
        } or not _delivery_current(delivery, item, user):
            raise ApiError("RECOVERY_TOKEN_INVALID", LINK_UNAVAILABLE_MESSAGE)
        if actor is not None and not hmac.compare_digest(user.password, actor.password):
            raise ApiError("RECOVERY_TOKEN_INVALID", LINK_UNAVAILABLE_MESSAGE)
        yield user, item, delivery


def check_token(token, purpose, *, actor=None):
    with _locked_token(token, purpose, actor=actor):
        return {"status": "VALID"}


def verify_recovery_email(user, token):
    try:
        with _locked_token(
            token, Purpose.RECOVERY_EMAIL_VERIFICATION, actor=user, action="VERIFY"
        ) as (fresh, item, delivery):
            item.current_email_encrypted = item.pending_email_encrypted
            item.current_email_hash = item.pending_email_hash
            item.pending_email_encrypted = ""
            item.pending_email_hash = ""
            item.verified_at = timezone.now()
            item.revision += 1
            item.save(
                update_fields=[
                    "current_email_encrypted",
                    "current_email_hash",
                    "pending_email_encrypted",
                    "pending_email_hash",
                    "verified_at",
                    "revision",
                    "updated_at",
                ]
            )
            delivery.consumed_at = timezone.now()
            delivery.save(update_fields=["consumed_at", "updated_at"])
            AccountRecoveryEmailDelivery.objects.filter(
                user_id=fresh.id, revoked_at__isnull=True, consumed_at__isnull=True
            ).update(revoked_at=timezone.now())
            record_event(
                "PARENT_RECOVERY_EMAIL_VERIFIED",
                actor=fresh,
                target_type="User",
                target_id=fresh.id,
                metadata={"revision": item.revision},
            )
    except IntegrityError as exc:
        # Unique verified email conflict is never evidence about another account.
        raise ApiError("RECOVERY_TOKEN_INVALID", LINK_UNAVAILABLE_MESSAGE) from exc
    return email_status(fresh)


def complete_password_recovery(token, new_password, confirm_password):
    with _locked_token(token, Purpose.PASSWORD_RESET, action="RESET") as (user, item, delivery):
        if new_password != confirm_password:
            raise ApiError("VALIDATION_ERROR", "كلمتا المرور غير متطابقتين.")
        try:
            validate_password(new_password, user)
        except ValidationError as exc:
            raise ApiError("VALIDATION_ERROR", " ".join(exc.messages)) from exc
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        delivery.consumed_at = timezone.now()
        delivery.save(update_fields=["consumed_at", "updated_at"])
        AccountRecoveryEmailDelivery.objects.filter(
            user_id=user.id, consumed_at__isnull=True, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())
        # Django validates the session auth hash against this password on every request.
        # No session or alternate access token is issued by this bearer capability.
        record_event(
            "PARENT_PASSWORD_RECOVERED",
            actor=user,
            target_type="User",
            target_id=user.id,
            metadata={"email_revision": item.revision, "session_auth_hash_rotated": True},
        )
    return {"message": "تم تغيير كلمة المرور. سجل الدخول بكلمة المرور الجديدة."}
