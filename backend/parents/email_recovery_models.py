"""Global, private recovery credentials, independent of school contact/email."""

import uuid

from django.conf import settings
from django.db import models

from common.models import TimestampedModel


class RecoveryEmailPurpose(models.TextChoices):
    RECOVERY_EMAIL_VERIFICATION = "RECOVERY_EMAIL_VERIFICATION", "توثيق بريد الاسترداد"
    PASSWORD_RESET = "PASSWORD_RESET", "استعادة كلمة المرور"


class RecoveryEmailDeliveryStatus(models.TextChoices):
    PENDING = "PENDING", "قيد الانتظار"
    SENDING = "SENDING", "قيد الإرسال"
    SUBMITTED_TO_PROVIDER = "SUBMITTED_TO_PROVIDER", "قبله مزود البريد"
    FAILED = "FAILED", "فشل الإرسال"
    UNKNOWN = "UNKNOWN", "نتيجة غير مؤكدة"
    CANCELLED = "CANCELLED", "ملغاة"


class AccountRecoveryEmail(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    current_email_encrypted = models.TextField(blank=True, default="")
    current_email_hash = models.CharField(max_length=64, null=True, blank=True, unique=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)
    pending_email_encrypted = models.TextField(blank=True, default="")
    pending_email_hash = models.CharField(max_length=64, blank=True, default="")
    pending_revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        verified_at__isnull=True,
                        current_email_hash__isnull=True,
                        current_email_encrypted="",
                    )
                    | (
                        models.Q(verified_at__isnull=False, current_email_hash__isnull=False)
                        & ~models.Q(current_email_encrypted="")
                    )
                ),
                name="recovery_email_verified_binding",
            ),
        ]


class AccountRecoveryEmailDelivery(TimestampedModel):
    """Hash-only bearer credential and purpose-specific, single-attempt outbox."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recovery_email = models.ForeignKey(AccountRecoveryEmail, on_delete=models.PROTECT)
    purpose = models.CharField(max_length=32, choices=RecoveryEmailPurpose.choices)
    status = models.CharField(
        max_length=32,
        choices=RecoveryEmailDeliveryStatus.choices,
        default=RecoveryEmailDeliveryStatus.PENDING,
    )
    email_hash = models.CharField(max_length=64)
    email_revision = models.PositiveIntegerField()
    password_fingerprint = models.CharField(max_length=64)
    mobile_fingerprint = models.CharField(max_length=64)
    token_hash = models.CharField(max_length=64, null=True, blank=True, unique=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    attempt_started_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    provider_reference = models.CharField(max_length=100, blank=True, default="")
    error_code = models.CharField(max_length=60, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(
                fields=["user", "purpose", "-created_at"], name="recovery_email_outbox_idx"
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(purpose__in=RecoveryEmailPurpose.values),
                name="recovery_email_purpose_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=RecoveryEmailDeliveryStatus.values),
                name="recovery_email_delivery_valid",
            ),
        ]
