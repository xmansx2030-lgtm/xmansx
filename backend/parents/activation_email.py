"""Approved, school-scoped email activation; the explicit POST proves email ownership."""

import secrets
from contextlib import contextmanager

from celery import shared_task
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from audit.services import record_event
from common.errors import ApiError
from common.tenant_rls import can_restore_tenant_context, tenant_context
from parents.access import lock_parent_school
from parents.email_recovery_provider import EmailDeliveryResult, send_activation_email
from parents.models import GuardianActivation, GuardianRegistrationRequest
from parents.security import decrypt_value, token_hash
from students.models import Student


@contextmanager
def activation_delivery_scope(school_id, activation_id):
    name = "app.parent_activation_delivery_id"
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s,true)", [name])
        previous = cursor.fetchone()[0] or ""
        cursor.execute("SELECT set_config(%s,%s,false)", [name, str(activation_id)])
    try:
        with tenant_context(school_id=school_id):
            yield
    finally:
        if can_restore_tenant_context():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config(%s,%s,false)", [name, previous])


def queue_activation_email(activation):
    if not activation.email_hash:
        raise ApiError("EMAIL_REQUIRED", "يلزم بريد تسجيل صحيح لإرسال التفعيل.")
    activation_id, school_id = activation.id, activation.school_id

    def dispatch():
        try:
            send_parent_activation_email.delay(school_id, activation_id)
        except Exception:
            with activation_delivery_scope(school_id, activation_id):
                GuardianActivation.objects.filter(
                    id=activation_id,
                    delivery_status="PENDING",
                ).update(delivery_status="FAILED", failure_code="EMAIL_QUEUE_UNAVAILABLE")

    transaction.on_commit(dispatch)


@contextmanager
def locked_activation(school_id, activation_id):
    with activation_delivery_scope(school_id, activation_id), transaction.atomic():
        lock_parent_school(school_id)
        index = (
            GuardianActivation.objects.filter(id=activation_id)
            .values(
                "student_id",
                "request_id",
            )
            .first()
        )
        if index is None:
            yield None
            return
        student = Student.objects.select_for_update().get(id=index["student_id"])
        item = GuardianRegistrationRequest.objects.select_for_update().get(id=index["request_id"])
        activation = (
            GuardianActivation.objects.select_for_update(of=("self",))
            .select_related("school")
            .get(
                id=activation_id,
            )
        )
        yield activation, item, student


def prepare_activation_email(school_id, activation_id):
    from parents.services import _validate_activation

    with locked_activation(school_id, activation_id) as locked:
        if locked is None:
            return None
        activation, item, student = locked
        if (
            activation.delivery_channel != "EMAIL"
            or activation.delivery_status != "PENDING"
            or activation.used_at
            or activation.revoked_at
        ):
            return None
        try:
            _validate_activation(activation, item, student, activation.school, for_delivery=True)
        except ApiError:
            activation.delivery_status = "FAILED"
            activation.failure_code = "PRE_SEND_STATE_CHANGED"
            activation.save(update_fields=["delivery_status", "failure_code", "updated_at"])
            return None
        token = secrets.token_urlsafe(32)
        activation.token_hash = token_hash(token)
        activation.delivery_status = "SENDING"
        activation.save(update_fields=["token_hash", "delivery_status", "updated_at"])
        return {"token": token, "token_hash": activation.token_hash}


@shared_task(name="parents.send_activation_email", ignore_result=True, max_retries=0)
def send_parent_activation_email(school_id: int, activation_id: int):
    from parents.services import _validate_activation

    # Commit the one-shot claim before provider I/O. A crashed worker cannot
    # generate a replacement bearer or blindly send this attempt a second time.
    prepared = prepare_activation_email(school_id, activation_id)
    if prepared is None:
        return "skipped"
    with locked_activation(school_id, activation_id) as locked:
        if locked is None:
            return "skipped"
        activation, item, student = locked
        if (
            activation.delivery_status != "SENDING"
            or activation.token_hash != prepared["token_hash"]
        ):
            return "skipped"
        try:
            _validate_activation(activation, item, student, activation.school)
        except ApiError:
            activation.delivery_status = "FAILED"
            activation.failure_code = "PRE_SEND_STATE_CHANGED"
            activation.save(update_fields=["delivery_status", "failure_code", "updated_at"])
            return "failed"
        # Retain the common school -> student -> request -> activation locks
        # through the bounded provider call so approval/contact cannot go stale.
        try:
            outcome = send_activation_email(
                delivery_id=str(activation.delivery_key),
                recipient=decrypt_value(item.email_encrypted),
                token=prepared["token"],
                expires_at=activation.expires_at,
                school_name=activation.school.name,
            )
        except Exception:
            outcome = EmailDeliveryResult("UNKNOWN", error_code="EMAIL_DELIVERY_UNKNOWN")
        activation.delivery_status = {
            "SUBMITTED_TO_PROVIDER": "SENT",
            "FAILED": "FAILED",
            "UNKNOWN": "UNKNOWN",
        }.get(outcome.status, "UNKNOWN")
        activation.failure_code = outcome.error_code[:60]
        activation.provider_reference = outcome.provider_reference[:100]
        activation.save(
            update_fields=[
                "delivery_status",
                "failure_code",
                "provider_reference",
                "updated_at",
            ]
        )
        record_event(
            "PARENT_ACTIVATION_DELIVERY",
            school=activation.school,
            target_type="GuardianActivation",
            target_id=activation_id,
            metadata={"status": activation.delivery_status, "channel": "EMAIL"},
        )
        return activation.delivery_status.lower()


def verify_activation_email(
    account, activation, registration, token, *, existing, current_password
):
    from parents.email_recovery_models import AccountRecoveryEmail, AccountRecoveryEmailDelivery
    from parents.email_recovery_services import email_scope, recovery_email_hash
    from parents.services import bearer_context

    try:
        with transaction.atomic(), email_scope(user_id=account.id, action="ENROLL"):
            email, _ = AccountRecoveryEmail.objects.select_for_update().get_or_create(user=account)
            # Linking another child can never replace any verified global credential.
            if email.verified_at:
                return
            if existing and not account.check_password(current_password or ""):
                raise ApiError(
                    "RECOVERY_PROOF_REQUIRED",
                    "أدخل كلمة المرور الحالية لتوثيق البريد.",
                    status_code=403,
                )
            normalized = decrypt_value(registration.email_encrypted)
            if recovery_email_hash(normalized) != activation.email_hash:
                raise ApiError("ACTIVATION_INVALID", "رابط التفعيل غير صالح.")
            email.pending_email_encrypted = registration.email_encrypted
            email.pending_email_hash = activation.email_hash
            email.pending_revision += 1
            email.save(
                update_fields=[
                    "pending_email_encrypted",
                    "pending_email_hash",
                    "pending_revision",
                    "updated_at",
                ]
            )
            AccountRecoveryEmailDelivery.objects.filter(
                user_id=account.id,
                revoked_at__isnull=True,
                consumed_at__isnull=True,
            ).update(revoked_at=timezone.now())
            with (
                bearer_context("activation", token_hash(token)),
                email_scope(
                    user_id=account.id,
                    action="ACTIVATE",
                ),
            ):
                email.current_email_encrypted = email.pending_email_encrypted
                email.current_email_hash = email.pending_email_hash
                email.pending_email_encrypted = ""
                email.pending_email_hash = ""
                email.verified_at = timezone.now()
                email.revision += 1
                email.save(
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
            record_event(
                "PARENT_RECOVERY_EMAIL_VERIFIED",
                actor=account,
                target_type="User",
                target_id=account.id,
                metadata={"revision": email.revision, "proof": "EMAIL_ACTIVATION"},
            )
    except IntegrityError as exc:
        raise ApiError("ACTIVATION_INVALID", "تعذر إتمام التفعيل. تواصل مع المدرسة.") from exc
