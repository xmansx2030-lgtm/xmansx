"""Explicit family grants; imported contact is never an authorization grant."""

import uuid

from django.conf import settings
from django.db import models

from common.models import TimestampedModel


class RelationStatus(models.TextChoices):
    PENDING = "PENDING", "بانتظار الاعتماد"
    ACTIVE = "ACTIVE", "نشطة"
    SUSPENDED_CONTACT_REVIEW = "SUSPENDED_CONTACT_REVIEW", "معلقة للمراجعة"
    REJECTED = "REJECTED", "مرفوضة"
    REVOKED = "REVOKED", "مسحوبة"


class RegistrationStatus(models.TextChoices):
    PENDING = "PENDING", "قيد المراجعة"
    NEEDS_INFO = "NEEDS_INFO", "تحتاج استكمالاً"
    APPROVED = "APPROVED", "معتمدة بانتظار التفعيل"
    REJECTED = "REJECTED", "مرفوضة"
    ACTIVATED = "ACTIVATED", "تم التفعيل"
    CANCELLED = "CANCELLED", "ملغاة"


class ParentRegistrationConfig(TimestampedModel):
    school = models.OneToOneField("schools.School", on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    enabled = models.BooleanField(default=False)


class GuardianStudentRelation(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="guardian_relations"
    )
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE)
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT)
    relationship_type = models.CharField(max_length=60, default="ولي أمر")
    status = models.CharField(
        max_length=32, choices=RelationStatus.choices, default=RelationStatus.PENDING
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_revision = models.PositiveIntegerField(default=1)
    contact_bound = models.BooleanField(default=True)
    contact_revision = models.PositiveIntegerField(default=1)
    approved_contact_hash = models.CharField(max_length=64, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.CharField(max_length=300, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    verification_note = models.CharField(max_length=600, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "student"], name="uniq_guardian_student")
        ]
        indexes = [
            models.Index(fields=["user", "status"], name="parent_user_status_idx"),
            models.Index(fields=["school", "status"], name="parent_school_status_idx"),
        ]


class GuardianRegistrationRequest(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE)
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT, null=True, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    name = models.CharField(max_length=150)
    mobile_encrypted = models.TextField()
    mobile_hash = models.CharField(max_length=64)
    mobile_masked = models.CharField(max_length=20)
    email_encrypted = models.TextField(blank=True, default="", db_default="")
    email_hash = models.CharField(max_length=64, blank=True, default="", db_default="")
    email_masked = models.CharField(max_length=254, blank=True, default="", db_default="")
    identifier_encrypted = models.TextField()
    identifier_hash = models.CharField(max_length=64)
    receipt_hash = models.CharField(max_length=64, unique=True)
    relationship_type = models.CharField(max_length=60, default="ولي أمر")
    status = models.CharField(
        max_length=20, choices=RegistrationStatus.choices, default=RegistrationStatus.PENDING
    )
    contact_revision = models.PositiveIntegerField(default=1)
    contact_bound = models.BooleanField(default=True)
    approved_contact_hash = models.CharField(max_length=64, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    verification_note = models.CharField(max_length=600, blank=True)
    decision_reason = models.CharField(max_length=300, blank=True)
    applicant_note = models.CharField(max_length=600, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "mobile_hash", "identifier_hash"],
                condition=models.Q(status__in=["PENDING", "NEEDS_INFO", "APPROVED"]),
                name="uniq_open_guardian_registration",
            )
        ]
        indexes = [
            models.Index(fields=["school", "status", "created_at"], name="parent_reg_queue_idx")
        ]


class GuardianActivation(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE)
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT)
    request = models.ForeignKey(
        GuardianRegistrationRequest, on_delete=models.CASCADE, related_name="activations"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    contact_revision = models.PositiveIntegerField()
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    delivery_status = models.CharField(max_length=12, default="PENDING")
    delivery_channel = models.CharField(max_length=10, default="SMS", db_default="SMS")
    email_hash = models.CharField(max_length=64, blank=True, default="", db_default="")
    delivery_key = models.UUIDField(default=uuid.uuid4, editable=False, null=True)
    activated_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    failure_code = models.CharField(max_length=60, blank=True)
    provider_reference = models.CharField(max_length=100, blank=True)


class GuardianContactReview(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE)
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT)
    previous_revision = models.PositiveIntegerField()
    current_revision = models.PositiveIntegerField()
    source = models.CharField(max_length=40, default="DATABASE")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reason = models.CharField(max_length=300, blank=True)
    previous_mobile_hash = models.CharField(max_length=64, blank=True)
    current_mobile_hash = models.CharField(max_length=64, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    verification_note = models.CharField(max_length=600, blank=True)
    resolution_reason = models.CharField(max_length=300, blank=True, default="", db_default="")
    resolution_verification_note = models.CharField(
        max_length=600, blank=True, default="", db_default=""
    )

    class Meta:
        indexes = [models.Index(fields=["school", "resolved_at"], name="parent_contact_review_idx")]


class GlobalMobileChangeRequest(TimestampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE)
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    new_mobile_encrypted = models.TextField()
    new_mobile_hash = models.CharField(max_length=64)
    verification_note = models.CharField(max_length=600)
    reason = models.CharField(max_length=300)
    status = models.CharField(max_length=20, default="PENDING")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status="PENDING"), name="parent_global_change_intake_only"
            )
        ]


class RecipientContactBlock(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE)
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT)
    mobile_hash = models.CharField(max_length=64)
    reason = models.CharField(max_length=300)
    verification_note = models.CharField(max_length=600)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    resolution_reason = models.CharField(max_length=300, blank=True, default="", db_default="")
    resolution_verification_note = models.CharField(
        max_length=600, blank=True, default="", db_default=""
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "mobile_hash"],
                condition=models.Q(resolved_at__isnull=True),
                name="uniq_open_recipient_block",
            )
        ]


# Request models are separated by responsibility, registered in this same app.
# Imported after relation models to keep dependency contracts explicit.
from parents.email_recovery_models import (  # noqa: E402,F401
    AccountRecoveryEmail,
    AccountRecoveryEmailDelivery,
)
from parents.recovery_models import (  # noqa: E402,F401
    GlobalAccountRecoveryCase,
    RecoveryEvidenceReference,
    RecoveryReviewAuthorization,
    RecoveryReviewDecision,
)
from parents.request_models import (  # noqa: E402,F401
    AttendanceCorrectionRequest,
    FamilyPublication,
    FamilyPublicationAcknowledgement,
    ParentExcuseAttachment,
    ParentExcuseRequest,
    ParentNotification,
    WarningAcknowledgement,
)
