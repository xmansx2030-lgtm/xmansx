from django.db import models

from common.models import TimestampedModel
from schools.settings_models import EducationStage, SchoolSettings

__all__ = ["School", "SchoolStatus", "SchoolType", "SchoolSettings", "EducationStage"]


class SchoolStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "نشطة"
    SUSPENDED = "SUSPENDED", "موقوفة"
    ARCHIVED = "ARCHIVED", "مؤرشفة"


class SchoolType(models.TextChoices):
    BOYS = "BOYS", "بنين"
    GIRLS = "GIRLS", "بنات"


class School(TimestampedModel):
    """المدرسة = المستأجر (Tenant). الأساس فقط — إعدادات التشغيل في المرحلة 3."""

    name = models.CharField("اسم المدرسة", max_length=200)
    slug = models.SlugField("المعرف", max_length=100, unique=True, allow_unicode=False)
    status = models.CharField(
        "الحالة",
        max_length=20,
        choices=SchoolStatus.choices,
        default=SchoolStatus.ACTIVE,
    )
    school_type = models.CharField(
        "نوع المدرسة",
        max_length=10,
        choices=SchoolType.choices,
        default=SchoolType.BOYS,
    )

    class Meta:
        verbose_name = "مدرسة"
        verbose_name_plural = "المدارس"
        indexes = [models.Index(fields=["status"], name="school_status_idx")]

    def __str__(self) -> str:
        return self.name

    @property
    def is_operational(self) -> bool:
        return self.status == SchoolStatus.ACTIVE
