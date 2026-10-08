"""Review-only recovery foundation. No state authorizes a credential change."""

import uuid

from django.conf import settings
from django.db import models

from common.models import TimestampedModel


class RecoveryOperation(models.TextChoices):
    MOBILE_CHANGE = "MOBILE_CHANGE", "تغيير رقم الدخول"
    PASSWORD_RECOVERY = "PASSWORD_RECOVERY", "استعادة كلمة المرور"
    MOBILE_AND_PASSWORD = "MOBILE_AND_PASSWORD", "استعادة الرقم وكلمة المرور"


class RecoveryStatus(models.TextChoices):
    PENDING = "PENDING", "بانتظار المراجعة"
    IDENTITY_REVIEW = "IDENTITY_REVIEW", "مراجعة هوية الحساب الأصلي"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE", "تحتاج أدلة مستقلة"
    AWAITING_SECOND_REVIEW = "AWAITING_SECOND_REVIEW", "بانتظار مراجع مستقل ثان"
    POLICY_BLOCKED = "POLICY_BLOCKED", "الإتمام محجوب لغياب سياسة معتمدة"
    REJECTED = "REJECTED", "مرفوضة"
    EXPIRED = "EXPIRED", "منتهية"
    CANCELLED = "CANCELLED", "ملغاة"


class RecoveryReviewStage(models.TextChoices):
    FIRST = "FIRST", "مراجعة أولى"
    SECOND = "SECOND", "مراجعة مستقلة ثانية"


class RecoveryReviewAuthorization(TimestampedModel):
    """Explicit, expiring central review permission; no credential authority."""

    reviewer = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    authorization_reference = models.UUIDField()
    stage = models.CharField(max_length=6, choices=RecoveryReviewStage.choices)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(reviewer=models.F("granted_by")),
                name="recovery_no_self_authorization",
            ),
            models.CheckConstraint(
                condition=models.Q(stage__in=RecoveryReviewStage.values),
                name="recovery_authority_stage_valid",
            ),
        ]


class GlobalAccountRecoveryCase(TimestampedModel):
    """A school intake is not evidence of global-account ownership."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_request = models.OneToOneField(
        "parents.GlobalMobileChangeRequest", on_delete=models.PROTECT, related_name="recovery_case"
    )
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE)
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    operation = models.CharField(max_length=24, choices=RecoveryOperation.choices)
    status = models.CharField(max_length=24, choices=RecoveryStatus.choices, default="PENDING")
    source_mobile_hash = models.CharField(max_length=64)
    account_password_fingerprint = models.CharField(max_length=64)
    account_mobile_fingerprint = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1, db_default=1, editable=False)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=RecoveryStatus.values),
                name="recovery_review_only_state",
            ),
            models.CheckConstraint(
                condition=models.Q(operation__in=RecoveryOperation.values),
                name="recovery_operation_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school", "status", "created_at"], name="recovery_school_queue_idx"
            ),
            models.Index(fields=["status", "expires_at"], name="recovery_expiry_idx"),
        ]


class RecoveryEvidenceKind(models.TextChoices):
    ORIGINAL_ACCOUNT_BINDING = "ORIGINAL_ACCOUNT_BINDING", "مرجع مستقل لصاحب الحساب الأصلي"
    NEW_NUMBER_OWNERSHIP = "NEW_NUMBER_OWNERSHIP", "مرجع ملكية الرقم المطلوب"


class RecoveryEvidenceReference(TimestampedModel):
    """Opaque external references only, unverified until an approved policy exists."""

    case = models.ForeignKey(GlobalAccountRecoveryCase, on_delete=models.PROTECT)
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE)
    kind = models.CharField(max_length=30, choices=RecoveryEvidenceKind.choices)
    reference_id = models.UUIDField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["case", "kind", "reference_id"], name="recovery_ref_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=RecoveryEvidenceKind.values),
                name="recovery_ref_kind_valid",
            ),
        ]


class RecoveryRecommendation(models.TextChoices):
    CONTINUE_REVIEW = "CONTINUE_REVIEW", "استكمال مراجعة لا يجيز الاستعادة"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE", "طلب أدلة مستقلة"
    REJECT = "REJECT", "رفض"


class RecoveryReviewDecision(TimestampedModel):
    case = models.ForeignKey(GlobalAccountRecoveryCase, on_delete=models.PROTECT)
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    stage = models.CharField(max_length=6, choices=RecoveryReviewStage.choices)
    recommendation = models.CharField(max_length=20, choices=RecoveryRecommendation.choices)
    case_version = models.PositiveIntegerField()
    evidence_fingerprint = models.CharField(max_length=64)
    note_encrypted = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["case", "case_version", "stage"], name="recovery_stage_once"
            ),
            models.UniqueConstraint(
                fields=["case", "case_version", "reviewer"], name="recovery_reviewer_once"
            ),
            models.CheckConstraint(
                condition=models.Q(stage__in=RecoveryReviewStage.values),
                name="recovery_stage_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(recommendation__in=RecoveryRecommendation.values),
                name="recovery_recommendation_valid",
            ),
        ]
