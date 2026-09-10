from django.conf import settings
from django.db import models

from common.models import TimestampedModel


class MembershipStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "فعالة"
    INVITED = "INVITED", "مدعو"
    DECLINED = "DECLINED", "مرفوضة"  # المرحلة 5: رفض الدعوة لا يحذف السجل
    SUSPENDED = "SUSPENDED", "موقوفة"
    LEFT = "LEFT", "منتهية"


class SchoolRole(models.TextChoices):
    """الأدوار المدرسية — القيم إنجليزية ثابتة، العربية للعرض فقط.

    PLATFORM_ADMIN ليس هنا عمداً: صلاحية منصة على User (ADR-003).
    """

    SCHOOL_MANAGER = "SCHOOL_MANAGER", "مدير المدرسة"
    VICE_PRINCIPAL = "VICE_PRINCIPAL", "الوكيل"
    COUNSELOR = "COUNSELOR", "المرشد الطلابي"
    TEACHER = "TEACHER", "معلم"
    GATE_GUARD = "GATE_GUARD", "حارس البوابة"


class SchoolCapability(models.TextChoices):
    """تكليفات تشغيلية تضاف للعضوية ولا تستبدل أدوار الموظف الأصلية."""

    MORNING_ATTENDANCE = "MORNING_ATTENDANCE", "متابعة التأخر الصباحي"


class SchoolMembership(TimestampedModel):
    """عضوية مستخدم عالمي في مدرسة — العمود الفقري للـ Multi-Tenancy."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    status = models.CharField(
        max_length=20,
        choices=MembershipStatus.choices,
        default=MembershipStatus.ACTIVE,
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "عضوية مدرسية"
        verbose_name_plural = "العضويات المدرسية"
        constraints = [
            # منع تكرار العضوية على مستوى قاعدة البيانات (وليس Validation فقط)
            models.UniqueConstraint(fields=["user", "school"], name="uniq_membership_user_school"),
        ]
        indexes = [
            models.Index(fields=["school", "status"], name="membership_school_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.school} ({self.status})"

    @property
    def is_active_membership(self) -> bool:
        return self.status == MembershipStatus.ACTIVE

    def role_codes(self) -> list[str]:
        return [r.role for r in self.roles.all()]

    def capability_codes(self) -> list[str]:
        return [row.capability for row in self.capabilities.all()]


class SchoolMembershipRole(TimestampedModel):
    """دور داخل عضوية — يسمح بتعدد الأدوار في نفس المدرسة."""

    membership = models.ForeignKey(
        SchoolMembership,
        on_delete=models.CASCADE,
        related_name="roles",
    )
    role = models.CharField(max_length=30, choices=SchoolRole.choices)

    class Meta:
        verbose_name = "دور العضوية"
        verbose_name_plural = "أدوار العضويات"
        constraints = [
            models.UniqueConstraint(fields=["membership", "role"], name="uniq_membership_role"),
        ]

    def __str__(self) -> str:
        return f"{self.membership} → {self.role}"


class SchoolMembershipCapability(TimestampedModel):
    """تكليف دائم داخل مدرسة واحدة؛ يبقى حتى يسحبه مدير المدرسة."""

    membership = models.ForeignKey(
        SchoolMembership,
        on_delete=models.CASCADE,
        related_name="capabilities",
    )
    capability = models.CharField(max_length=40, choices=SchoolCapability.choices)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "تكليف تشغيلي"
        verbose_name_plural = "التكليفات التشغيلية"
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "capability"],
                name="uniq_membership_capability",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.membership} → {self.capability}"
