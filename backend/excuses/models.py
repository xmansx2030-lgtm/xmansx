"""أعذار الغياب (م10) — طبقة تصنيف إداري منفصلة عن حقيقة سجل الحضور.

القاعدة الأساسية: AttendanceMark.status يبقى ABSENT دائمًا؛ «بعذر/بدون عذر» تصنيف
مشتق من AbsenceExcuseCoverage النشطة لعذر معتمد — لا ازدواج مصادر حقيقة
(ADR-010: التاريخ لا يُمحى، والإلغاء Void لا Delete).
"""

from pathlib import Path
from uuid import uuid4

from django.db import models

from common.models import TimestampedModel


class AbsenceExcuseStatus(models.TextChoices):
    PENDING = "PENDING", "بانتظار الاعتماد"
    APPROVED = "APPROVED", "معتمد"
    REJECTED = "REJECTED", "مرفوض"
    CANCELLED = "CANCELLED", "ملغى"


class ExcuseReasonType(models.TextChoices):
    MEDICAL_REPORT = "MEDICAL_REPORT", "تقرير طبي"
    MEDICAL_APPOINTMENT = "MEDICAL_APPOINTMENT", "موعد طبي"
    OFFICIAL = "OFFICIAL", "عذر رسمي"
    FAMILY = "FAMILY", "ظرف أسري"
    OTHER = "OTHER", "أخرى"


class ExcuseCoverageStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "نشطة"
    VOIDED = "VOIDED", "ملغاة"


class AbsenceExcuse(TimestampedModel):
    """العذر الإداري — دورة حياته منفصلة تمامًا عن سجل الحضور الخام."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="absence_excuses"
    )
    # PROTECT عمدًا — يجبر تسجيل الحذف في PURGE_STEPS (إلزام المرحلة 4.1)
    student = models.ForeignKey(
        "students.Student", on_delete=models.PROTECT, related_name="absence_excuses"
    )

    status = models.CharField(
        max_length=10,
        choices=AbsenceExcuseStatus.choices,
        default=AbsenceExcuseStatus.PENDING,
    )
    reason_type = models.CharField(max_length=20, choices=ExcuseReasonType.choices)
    # اختيارية — لا تفاصيل صحية أكثر مما يحتاجه الغرض (data minimization)
    notes = models.CharField(max_length=500, blank=True, default="")

    recorded_by_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField()

    approved_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    rejected_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=300, blank=True, default="")

    cancelled_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(
                fields=["school", "student", "status"], name="excuse_school_student_idx"
            ),
            models.Index(fields=["school", "status"], name="excuse_school_status_idx"),
        ]

    def __str__(self):
        return f"عذر {self.get_reason_type_display()} — {self.student_id} ({self.status})"


class AbsenceExcuseTarget(TimestampedModel):
    """نطاق العذر المعلن: يوم كامل (period_sequence=NULL) أو حصة محددة."""

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    excuse = models.ForeignKey(
        AbsenceExcuse, on_delete=models.CASCADE, related_name="targets"
    )
    attendance_date = models.DateField()
    period_sequence = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            # ‏NULL = يوم كامل — nulls_distinct=False يمنع تكرار هدف اليوم الكامل
            models.UniqueConstraint(
                fields=["excuse", "attendance_date", "period_sequence"],
                nulls_distinct=False,
                name="uniq_excuse_target",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school", "attendance_date"], name="excuse_target_date_idx"
            ),
        ]

    def __str__(self):
        scope = "يوم كامل" if self.period_sequence is None else f"حصة {self.period_sequence}"
        return f"{self.attendance_date} — {scope}"


class AbsenceExcuseCoverage(TimestampedModel):
    """ربط العذر المعتمد بحالة غياب فعلية (جلسة معتمدة + طالب).

    ترتبط بالجلسة لا بالعلامة — التعديل الإداري يحذف العلامات ويعيد إنشاءها
    (edit_session) فمعرفاتها غير مستقرة، بينما (الجلسة، الطالب) ثابتان.
    """

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    excuse = models.ForeignKey(
        AbsenceExcuse, on_delete=models.CASCADE, related_name="coverages"
    )
    student = models.ForeignKey(
        "students.Student", on_delete=models.PROTECT, related_name="excuse_coverages"
    )
    attendance_session = models.ForeignKey(
        "attendance.AttendanceSession", on_delete=models.CASCADE, related_name="+"
    )
    attendance_date = models.DateField()
    period_sequence_snapshot = models.PositiveSmallIntegerField()

    status = models.CharField(
        max_length=10,
        choices=ExcuseCoverageStatus.choices,
        default=ExcuseCoverageStatus.ACTIVE,
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        constraints = [
            # غياب واحد لا يغطيه أكثر من عذر معتمد (م10 بند 42) — ويمنع تكرار
            # الاعتماد المزدوج/المتزامن على مستوى DB لا Frontend فقط
            models.UniqueConstraint(
                fields=["attendance_session", "student"],
                condition=models.Q(status="ACTIVE"),
                name="uniq_active_coverage_per_absence",
            ),
        ]
        indexes = [
            models.Index(
                fields=["student", "attendance_date", "status"],
                name="coverage_student_date_idx",
            ),
            models.Index(
                fields=["school", "attendance_date", "status"],
                name="coverage_school_date_idx",
            ),
        ]

    def __str__(self):
        return (
            f"تغطية {self.attendance_date} حصة {self.period_sequence_snapshot}"
            f" — {self.status}"
        )


def excuse_attachment_path(instance, filename: str) -> str:
    """مفتاح تخزين عشوائي — لا اسم مستخدم ولا اسم ملف أصلي في المسار."""
    extension = Path(filename).suffix.lower()
    return f"excuse_attachments/school_{instance.school_id}/{uuid4().hex}{extension}"


class AbsenceExcuseAttachment(TimestampedModel):
    """مرفق عذر (تقرير طبي...) — تخزين خاص، التنزيل عبر endpoint مصرح فقط."""

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    excuse = models.ForeignKey(
        AbsenceExcuse, on_delete=models.CASCADE, related_name="attachments"
    )

    file = models.FileField(upload_to=excuse_attachment_path)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=50)
    size_bytes = models.PositiveIntegerField()
    checksum = models.CharField(max_length=64)  # SHA-256 hex

    uploaded_by_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        indexes = [
            models.Index(fields=["school", "excuse"], name="excuse_attach_school_idx"),
        ]

    def __str__(self):
        return f"مرفق {self.original_filename} — عذر {self.excuse_id}"
