"""SchoolSettings — الإعدادات التشغيلية العامة للمدرسة (حقول صريحة، لا JSON شامل)."""

from datetime import time

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from common.models import TimestampedModel


class EducationStage(models.TextChoices):
    ELEMENTARY = "ELEMENTARY", "ابتدائي"
    MIDDLE = "MIDDLE", "متوسط"
    SECONDARY = "SECONDARY", "ثانوي"
    MULTI_STAGE = "MULTI_STAGE", "متعدد المراحل"


def school_logo_path(instance, filename: str) -> str:
    # الاسم الأصلي لا يستخدم في التخزين (تعقيم) — الامتداد فقط بعد التحقق
    from pathlib import Path

    return f"school_logos/school_{instance.school_id}/logo{Path(filename).suffix.lower()}"


class SchoolSettings(TimestampedModel):
    """إعداد واحد لكل مدرسة (OneToOne = قيد unique على مستوى قاعدة البيانات).

    - اسم المدرسة يبقى في School.name — لا تكرار هنا.
    - المدير/الوكلاء/المرشدون يستمدون من Memberships — لا أسماء نصية كمصدر صلاحية.
    - official_principal_name اختياري للنماذج الرسمية والطباعة فقط.
    """

    school = models.OneToOneField(
        "schools.School", on_delete=models.CASCADE, related_name="settings"
    )
    ministry_school_number = models.CharField(
        "الرقم الوزاري", max_length=30, blank=True, default=""
    )
    education_stage = models.CharField(
        "المرحلة التعليمية",
        max_length=20,
        choices=EducationStage.choices,
        default=EducationStage.SECONDARY,
    )
    city = models.CharField("المدينة", max_length=100, blank=True, default="")
    official_principal_name = models.CharField(
        "اسم المدير الرسمي (للطباعة)", max_length=150, blank=True, default=""
    )
    logo = models.ImageField(upload_to=school_logo_path, null=True, blank=True)
    timezone = models.CharField(max_length=50, default="Asia/Riyadh")

    # إعدادات التحضير — تُحفظ الآن، وتفعيلها الفعلي في المراحل 6 و7
    attendance_edit_window_minutes = models.PositiveSmallIntegerField(
        "مهلة تعديل التحضير (دقائق)",
        default=15,
        validators=[MinValueValidator(0), MaxValueValidator(120)],
    )
    unprepared_period_alert_minutes = models.PositiveSmallIntegerField(
        "تنبيه عدم التحضير بعد (دقائق)",
        default=25,
        validators=[MinValueValidator(1), MaxValueValidator(120)],
    )

    # الحضور الصباحي (م8.5) — بداية الدوام مستقلة عن الحصة الأولى عمدًا
    school_day_start_time = models.TimeField("بداية الدوام الصباحي", default=time(7, 0))
    morning_late_grace_minutes = models.PositiveSmallIntegerField(
        "فترة السماح الصباحية (دقائق)",
        default=5,
        validators=[MinValueValidator(0), MaxValueValidator(120)],
    )

    class Meta:
        verbose_name = "إعدادات مدرسة"
        verbose_name_plural = "إعدادات المدارس"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(attendance_edit_window_minutes__lte=120),
                name="settings_edit_window_max",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    unprepared_period_alert_minutes__gte=1,
                    unprepared_period_alert_minutes__lte=120,
                ),
                name="settings_alert_minutes_range",
            ),
        ]

    def __str__(self) -> str:
        return f"إعدادات {self.school}"
