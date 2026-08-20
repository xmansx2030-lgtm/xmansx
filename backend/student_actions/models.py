"""الإجراءات الطلابية (م12) — سجل إداري لما فُعل، لا لما استحقه الطالب.

الفصل الصلب بين ثلاثة مفاهيم (البند 1):
- ‏`StudentWarning` (م11): الطالب **بلغ** الإنذار الثاني.
- ‏`StudentAction` (هنا): **تم** التواصل مع ولي الأمر / أخذ تعهد / تسليم إنذار.
- ‏`GeneratedDocument` (م12): **صدر وطُبع** مستند الإنذار الثاني.

قواعد:
- الإجراء لا يعدّل أي مصدر حضور/عذر/إنذار (البند 2) — تسجيل فقط.
- لا حذف نهائي: الخطأ يعالج بالإلغاء (CANCELLED) بسبب وفاعل ووقت (البند 11).
- ربط الإنذار اختياري، وإن وُجد فيجب أن يكون لنفس الطالب ونفس المدرسة (البند 101).
- student بـ PROTECT: نسيان تسجيل الحذف النهائي يفشل صاخبًا (إلزام م4.1).
"""

from django.db import models

from common.models import TimestampedModel


class StudentActionType(models.TextChoices):
    PARENT_CONTACT = "PARENT_CONTACT", "التواصل مع ولي الأمر"
    STUDENT_MEETING = "STUDENT_MEETING", "مقابلة الطالب"
    PARENT_MEETING = "PARENT_MEETING", "مقابلة ولي الأمر"
    COMMITMENT_TAKEN = "COMMITMENT_TAKEN", "أخذ تعهد"
    WARNING_DELIVERED = "WARNING_DELIVERED", "تسليم إنذار"
    # دمج م12+م13: لا نوع مكافئ في القائمة أعلاه (فحص صريح قبل الإضافة). يسجل
    # للمدير/الوكيل عند إنشاء الإحالة فقط — إحالة المعلم سجلها هي نفسها، ولا إجراء
    # إداري ينسب إليه. مصدر الحقيقة يبقى StudentReferral والإجراء أثر إداري.
    REFERRED_TO_COUNSELOR = "REFERRED_TO_COUNSELOR", "إحالة إلى المرشد الطلابي"
    ADMINISTRATIVE_NOTE = "ADMINISTRATIVE_NOTE", "ملاحظة إدارية"
    OTHER = "OTHER", "إجراء آخر"


class StudentActionStatus(models.TextChoices):
    COMPLETED = "COMPLETED", "منفذ"
    CANCELLED = "CANCELLED", "ملغى"


class StudentAction(TimestampedModel):
    """إجراء إداري موثق على طالب — النوع Enum لا نص عربي (البند 6)."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="student_actions"
    )
    student = models.ForeignKey(  # PROTECT: حارس تسجيل Purge
        "students.Student", on_delete=models.PROTECT, related_name="actions"
    )
    # PROTECT كذلك: حذف الطالب يمر بخطوات Purge المرتبة (إجراءات ثم إنذارات)
    warning = models.ForeignKey(
        "student_warnings.StudentWarning",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="actions",
    )

    action_type = models.CharField(max_length=24, choices=StudentActionType.choices)
    status = models.CharField(
        max_length=12, choices=StudentActionStatus.choices, default=StudentActionStatus.COMPLETED
    )

    performed_by_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )
    performed_at = models.DateTimeField()
    # ملاحظة إدارية موجزة — ليست مصدر الحقيقة لنوع الإجراء (البند 10)
    notes = models.CharField(max_length=500, blank=True, default="")

    cancelled_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        verbose_name = "إجراء طلابي"
        verbose_name_plural = "الإجراءات الطلابية"
        indexes = [
            models.Index(
                fields=["school", "student", "-performed_at"], name="action_school_student_idx"
            ),
            models.Index(fields=["school", "action_type"], name="action_school_type_idx"),
            models.Index(fields=["warning"], name="action_warning_idx"),
        ]
        constraints = [
            # الإلغاء لا يكون بلا فاعل/وقت — يمنع سجلات إلغاء شبحية
            models.CheckConstraint(
                condition=(
                    models.Q(status=StudentActionStatus.COMPLETED, cancelled_at__isnull=True)
                    | models.Q(status=StudentActionStatus.CANCELLED, cancelled_at__isnull=False)
                ),
                name="action_cancelled_requires_timestamp",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student_id} — {self.action_type} ({self.status})"
