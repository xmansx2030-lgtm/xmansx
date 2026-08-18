from django.conf import settings
from django.db import models

from common.models import TimestampedModel


class MembershipStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "فعالة"
    INVITED = "INVITED", "مدعو"
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
