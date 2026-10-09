"""Family requests and explicitly published family content.

These records never grant staff membership or change attendance by themselves.
"""

from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import models

from common.models import TimestampedModel
from documents.storage import PrivateDocumentStorage
from excuses.models import ExcuseReasonType


class ParentRequestStatus(models.TextChoices):
    PENDING = "PENDING", "بانتظار المراجعة"
    NEEDS_INFO = "NEEDS_INFO", "يحتاج استكمالاً"
    APPROVED = "APPROVED", "معتمد"
    REJECTED = "REJECTED", "مرفوض"
    CANCELLED = "CANCELLED", "ملغى"


class ParentExcuseRequest(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    student = models.ForeignKey(
        "students.Student", on_delete=models.PROTECT, related_name="parent_excuse_requests"
    )
    relation = models.ForeignKey(
        "parents.GuardianStudentRelation", on_delete=models.PROTECT, related_name="excuse_requests"
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="parent_excuse_requests"
    )
    status = models.CharField(
        max_length=12, choices=ParentRequestStatus.choices, default=ParentRequestStatus.PENDING
    )
    reason_type = models.CharField(max_length=20, choices=ExcuseReasonType.choices)
    notes = models.CharField(max_length=500, blank=True, default="")
    targets = models.JSONField(default=list)
    target_fingerprint = models.CharField(max_length=64)
    administrative_excuse = models.ForeignKey(
        "excuses.AbsenceExcuse",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="parent_requests",
    )
    reviewed_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["relation", "target_fingerprint"],
                condition=models.Q(status__in=["PENDING", "NEEDS_INFO"]),
                name="uniq_open_parent_excuse",
            )
        ]
        indexes = [
            models.Index(fields=["school", "status", "created_at"], name="parent_excuse_queue_idx")
        ]


def parent_attachment_path(instance, filename):
    return (
        f"parent_requests/school_{instance.school_id}/{uuid4().hex}{Path(filename).suffix.lower()}"
    )


class ParentExcuseAttachment(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    parent_request = models.ForeignKey(
        ParentExcuseRequest, on_delete=models.CASCADE, related_name="attachments"
    )
    file = models.FileField(upload_to=parent_attachment_path, storage=PrivateDocumentStorage)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=50)
    size_bytes = models.PositiveIntegerField()
    checksum = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )


class AttendanceCorrectionRequest(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    student = models.ForeignKey(
        "students.Student", on_delete=models.PROTECT, related_name="parent_correction_requests"
    )
    relation = models.ForeignKey(
        "parents.GuardianStudentRelation",
        on_delete=models.PROTECT,
        related_name="correction_requests",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="parent_correction_requests",
    )
    session = models.ForeignKey(
        "attendance.AttendanceSession",
        on_delete=models.PROTECT,
        related_name="parent_correction_requests",
    )
    reason = models.CharField(max_length=500)
    status = models.CharField(
        max_length=12, choices=ParentRequestStatus.choices, default=ParentRequestStatus.PENDING
    )
    reviewed_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "session"],
                condition=models.Q(status__in=["PENDING", "NEEDS_INFO"]),
                name="uniq_open_parent_correction",
            )
        ]
        indexes = [
            models.Index(fields=["school", "status", "created_at"], name="parent_correct_queue_idx")
        ]


class FamilyPublication(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    student = models.ForeignKey(
        "students.Student", on_delete=models.PROTECT, related_name="family_publications"
    )
    case = models.ForeignKey(
        "counseling.CounselorCase",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="family_publications",
    )
    document = models.ForeignKey(
        "documents.GeneratedDocument",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="family_publications",
    )
    title = models.CharField(max_length=180)
    body = models.TextField(max_length=4000, blank=True, default="")
    required_action = models.CharField(max_length=500, blank=True, default="")
    due_at = models.DateTimeField(null=True, blank=True)
    published_by_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )
    published_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    revocation_reason = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(
                fields=["school", "student", "published_at"], name="family_publication_idx"
            )
        ]


class WarningAcknowledgement(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    relation = models.ForeignKey(
        "parents.GuardianStudentRelation",
        on_delete=models.PROTECT,
        related_name="warning_acknowledgements",
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    warning = models.ForeignKey(
        "student_warnings.StudentWarning",
        on_delete=models.CASCADE,
        related_name="parent_acknowledgements",
    )
    acknowledged_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["relation", "warning"], name="uniq_parent_warning_ack")
        ]


class FamilyPublicationAcknowledgement(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    relation = models.ForeignKey(
        "parents.GuardianStudentRelation",
        on_delete=models.PROTECT,
        related_name="publication_acknowledgements",
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    publication = models.ForeignKey(
        FamilyPublication, on_delete=models.CASCADE, related_name="acknowledgements"
    )
    acknowledged_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["relation", "publication"], name="uniq_parent_publication_ack"
            )
        ]


class ParentNotification(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    relation = models.ForeignKey(
        "parents.GuardianStudentRelation", on_delete=models.PROTECT, related_name="notifications"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="parent_notifications"
    )
    kind = models.CharField(max_length=32)
    dedup_key = models.CharField(max_length=120)
    title = models.CharField(max_length=180)
    body = models.CharField(max_length=500, blank=True, default="")
    requires_action = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    action_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["relation", "dedup_key"], name="uniq_parent_notification"
            )
        ]
        indexes = [models.Index(fields=["user", "-created_at"], name="parent_notification_idx")]
