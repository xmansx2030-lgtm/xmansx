from django.conf import settings
from django.db import models

from common.models import TimestampedModel


class PlatformStaffRole(models.TextChoices):
    OPERATIONS_MANAGER = "OPERATIONS_MANAGER", "مدير العمليات"
    SUPPORT = "SUPPORT", "خدمة المدارس"
    BILLING = "BILLING", "الاشتراكات والفوترة"
    AUDITOR = "AUDITOR", "مراجع"


class PlatformStaffStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "نشط"
    SUSPENDED = "SUSPENDED", "موقوف"


class PlatformStaffMembership(TimestampedModel):
    """وصول موظف إلى المنصة؛ منفصل تماماً عن عضويات المدارس وعن مالك المنصة."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_staff_membership",
    )
    role = models.CharField(max_length=30, choices=PlatformStaffRole.choices)
    status = models.CharField(
        max_length=20,
        choices=PlatformStaffStatus.choices,
        default=PlatformStaffStatus.ACTIVE,
    )
    job_title = models.CharField(max_length=120, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="platform_staff_created",
    )

    class Meta:
        verbose_name = "موظف منصة"
        verbose_name_plural = "موظفو المنصة"
        indexes = [models.Index(fields=["status", "role"], name="platform_staff_status_role_idx")]

    def __str__(self) -> str:
        return f"{self.user} - {self.get_role_display()}"
