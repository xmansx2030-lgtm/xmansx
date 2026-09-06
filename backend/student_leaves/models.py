"""سجل استئذانات الطلاب — سجل تشغيلي مستقل محفوظ داخل ملف الطالب."""

from django.db import models

from common.models import TimestampedModel


class StudentLeaveStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "ساري"
    CANCELLED = "CANCELLED", "ملغى"


class StudentLeavePermission(TimestampedModel):
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="student_leave_permissions"
    )
    student = models.ForeignKey(
        "students.Student", on_delete=models.PROTECT, related_name="leave_permissions"
    )
    leave_date = models.DateField("تاريخ الاستئذان")
    leave_time = models.TimeField("وقت الخروج")
    reason = models.CharField("سبب الاستئذان", max_length=500)
    grade_name = models.CharField(max_length=100, blank=True, default="")
    section_name = models.CharField(max_length=50, blank=True, default="")
    status = models.CharField(
        max_length=12,
        choices=StudentLeaveStatus.choices,
        default=StudentLeaveStatus.ACTIVE,
    )
    recorded_by_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="recorded_leaves"
    )
    cancelled_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cancelled_leaves",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        verbose_name = "استئذان طالب"
        verbose_name_plural = "استئذانات الطلاب"
        ordering = ["-leave_date", "-leave_time", "-id"]
        indexes = [
            models.Index(
                fields=["school", "leave_date", "status"], name="leave_school_date_status_idx"
            ),
            models.Index(
                fields=["school", "student", "-leave_date"], name="leave_school_student_idx"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "student", "leave_date"],
                condition=models.Q(status=StudentLeaveStatus.ACTIVE),
                name="uniq_active_student_leave_day",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status=StudentLeaveStatus.ACTIVE, cancelled_at__isnull=True)
                    | models.Q(status=StudentLeaveStatus.CANCELLED, cancelled_at__isnull=False)
                ),
                name="leave_cancelled_requires_timestamp",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student} — {self.leave_date} {self.leave_time}"
