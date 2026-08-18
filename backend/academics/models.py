"""التقويم الأكاديمي وجداول الأجراس.

قواعد صلبة:
- كل جدول يحمل school (عزل المستأجرين) — يحدده الـ Backend حصرًا، لا يقبل من العميل.
- ACTIVE واحد لكل مدرسة (عام دراسي/فصل) بقيد partial unique في قاعدة البيانات.
- BellPeriod يحمل كل ما يلزم snapshot الحضور مستقبلًا (المرحلة 6) — التاريخ لن
  يعاد بناؤه من الجدول الحالي أبدًا (ADR-010).
"""

from django.db import models

from common.models import TimestampedModel


class AcademicYearStatus(models.TextChoices):
    UPCOMING = "UPCOMING", "قادم"
    ACTIVE = "ACTIVE", "نشط"
    CLOSED = "CLOSED", "منتهي"
    ARCHIVED = "ARCHIVED", "مؤرشف"


class AcademicYear(TimestampedModel):
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="academic_years"
    )
    name = models.CharField("اسم العام", max_length=50)  # مثال: 2026/2027
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=AcademicYearStatus.choices, default=AcademicYearStatus.UPCOMING
    )

    class Meta:
        verbose_name = "عام دراسي"
        verbose_name_plural = "الأعوام الدراسية"
        constraints = [
            # عام نشط واحد فقط لكل مدرسة — الحكم النهائي ضد التزامن
            models.UniqueConstraint(
                fields=["school"],
                condition=models.Q(status="ACTIVE"),
                name="uniq_active_year_per_school",
            ),
            models.CheckConstraint(
                condition=models.Q(start_date__lt=models.F("end_date")),
                name="year_start_before_end",
            ),
        ]
        indexes = [models.Index(fields=["school", "status"], name="year_school_status_idx")]

    def __str__(self) -> str:
        return f"{self.name} — {self.school}"


class SemesterStatus(models.TextChoices):
    UPCOMING = "UPCOMING", "قادم"
    ACTIVE = "ACTIVE", "نشط"
    CLOSED = "CLOSED", "منتهي"


class Semester(TimestampedModel):
    school = models.ForeignKey(  # denormalized للعزل والفهارس
        "schools.School", on_delete=models.CASCADE, related_name="semesters"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="semesters"
    )
    name = models.CharField("اسم الفصل", max_length=50)
    sequence = models.PositiveSmallIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=SemesterStatus.choices, default=SemesterStatus.UPCOMING
    )

    class Meta:
        verbose_name = "فصل دراسي"
        verbose_name_plural = "الفصول الدراسية"
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "sequence"], name="uniq_semester_sequence_per_year"
            ),
            models.UniqueConstraint(
                fields=["school"],
                condition=models.Q(status="ACTIVE"),
                name="uniq_active_semester_per_school",
            ),
            models.CheckConstraint(
                condition=models.Q(start_date__lte=models.F("end_date")),
                name="semester_start_before_end",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.academic_year.name})"


class BellScheduleStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "نشط"
    INACTIVE = "INACTIVE", "غير نشط"
    ARCHIVED = "ARCHIVED", "مؤرشف"


class BellSchedule(TimestampedModel):
    """جدول أوقات الحصص: العادي / رمضان / الاختبارات / مؤقت — يعاد استخدامه لعدة أيام."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="bell_schedules"
    )
    name = models.CharField("اسم الجدول", max_length=100)
    status = models.CharField(
        max_length=20, choices=BellScheduleStatus.choices, default=BellScheduleStatus.ACTIVE
    )
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "جدول حصص"
        verbose_name_plural = "جداول الحصص"
        indexes = [models.Index(fields=["school", "status"], name="bell_school_status_idx")]

    def __str__(self) -> str:
        return f"{self.name} — {self.school}"


class BellPeriod(TimestampedModel):
    """حصة داخل جدول — تحمل كل حقول snapshot الحضور المستقبلي.

    الفسحة/الاصطفاف: is_attendance_period=False (لا تدخل في التحضير).
    """

    school = models.ForeignKey(  # denormalized للعزل
        "schools.School", on_delete=models.CASCADE, related_name="bell_periods"
    )
    bell_schedule = models.ForeignKey(
        BellSchedule, on_delete=models.CASCADE, related_name="periods"
    )
    sequence = models.PositiveSmallIntegerField()
    name = models.CharField("اسم الحصة", max_length=50)  # مثال: الحصة الأولى / الفسحة
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_attendance_period = models.BooleanField(default=True)

    class Meta:
        verbose_name = "حصة"
        verbose_name_plural = "الحصص"
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["bell_schedule", "sequence"], name="uniq_period_sequence_per_schedule"
            ),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="period_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.start_time:%H:%M}-{self.end_time:%H:%M})"


class Weekday(models.IntegerChoices):
    SUNDAY = 0, "الأحد"
    MONDAY = 1, "الاثنين"
    TUESDAY = 2, "الثلاثاء"
    WEDNESDAY = 3, "الأربعاء"
    THURSDAY = 4, "الخميس"
    FRIDAY = 5, "الجمعة"
    SATURDAY = 6, "السبت"


class SchoolWeekDay(TimestampedModel):
    """يوم أسبوع للمدرسة: هل هو يوم دراسة؟ وأي جدول حصص يطبق فيه.

    ربط الجدول هنا = «الجدول النشط لكل يوم» (حل MVP) — نفس BellSchedule
    يخدم عدة أيام بلا نسخ للحصص.
    """

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="week_days"
    )
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    is_school_day = models.BooleanField(default=False)
    bell_schedule = models.ForeignKey(
        BellSchedule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_days",
    )

    class Meta:
        verbose_name = "يوم دراسي"
        verbose_name_plural = "أيام الدراسة"
        ordering = ["weekday"]
        constraints = [
            models.UniqueConstraint(fields=["school", "weekday"], name="uniq_school_weekday"),
        ]

    def __str__(self) -> str:
        return f"{self.get_weekday_display()} — {self.school}"
