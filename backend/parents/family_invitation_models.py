"""One reviewed SMS invitation, with independent exact-child approval proofs."""

import uuid

from django.conf import settings
from django.db import models, transaction

from common.models import TimestampedModel


class FamilyInvitationQuerySet(models.QuerySet):
    def delete(self):
        # Student purge's queryset count stays read-only. Deletion alone takes
        # the same locks as issue/consume before Django starts child cascades.
        from parents.family_invitation_services import lock_family, lock_parent_school
        from parents.models import GuardianActivation, GuardianRegistrationRequest
        from students.models import Student

        with transaction.atomic():
            rows = list(
                self.values("id", "school_id", "mobile_hash").order_by("school_id", "mobile_hash")
            )
            for school_id in sorted({row["school_id"] for row in rows}):
                lock_parent_school(school_id)
            for row in rows:
                lock_family(row["school_id"], row["mobile_hash"])
            ids = [row["id"] for row in rows]
            children = list(
                GuardianFamilyInvitationChild.objects.filter(invitation_id__in=ids).values(
                    "student_id", "activation_id"
                )
            )
            list(
                Student.objects.filter(id__in=[child["student_id"] for child in children])
                .order_by("id")
                .select_for_update()
            )
            acts = GuardianActivation.objects.filter(
                id__in=[child["activation_id"] for child in children]
            )
            list(
                GuardianRegistrationRequest.objects.filter(id__in=acts.values("request_id"))
                .order_by("id")
                .select_for_update()
            )
            list(acts.order_by("id").select_for_update())
            return models.QuerySet.delete(self.filter(pk__in=ids))


class GuardianFamilyInvitation(TimestampedModel):
    objects = FamilyInvitationQuerySet.as_manager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    mobile_encrypted = models.TextField()
    mobile_hash = models.CharField(max_length=64)
    mobile_masked = models.CharField(max_length=20)
    token_hash = models.CharField(max_length=64, unique=True)
    verification_note = models.CharField(max_length=600)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    activated_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    delivery_status = models.CharField(max_length=12, default="PENDING")
    provider_reference = models.CharField(max_length=100, blank=True)
    failure_code = models.CharField(max_length=60, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "mobile_hash"],
                condition=models.Q(revoked_at__isnull=True, consumed_at__isnull=True),
                name="uniq_open_family_invitation",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    delivery_status__in=["PENDING", "SENDING", "SENT", "FAILED", "UNKNOWN"]
                ),
                name="family_invitation_delivery_state",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school", "mobile_hash", "-created_at"], name="family_invitation_queue_idx"
            )
        ]


class GuardianFamilyInvitationChild(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE)
    invitation = models.ForeignKey(
        GuardianFamilyInvitation, on_delete=models.CASCADE, related_name="children"
    )
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT)
    activation = models.OneToOneField(
        "parents.GuardianActivation", on_delete=models.CASCADE, related_name="family_child"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["invitation", "student"], name="uniq_family_invitation_child"
            )
        ]
