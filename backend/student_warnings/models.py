"""قواعد الإنذارات وإنذارات الطلاب (م11).

قواعد صلبة:
- **الاكتشاف تلقائي والإصدار قرار بشري**: لا إنذار ينشأ إلا بفعل صريح من الوكيل/المدير.
- **Snapshot ثابت**: كل ما تحتاجه م12 لإنتاج المستند كما صدر محفوظ لحظة الإصدار —
  العتبة والمقياس واسم الطالب وصفه وفصله؛ تغيير القواعد أو الأعذار أو النقل لاحقًا
  لا يعيد كتابة أي إنذار صادر.
- **النطاق الأكاديمي = العام الدراسي** (قرار موثق في docs/WARNING_RULES.md): ملخصات
  الحضور مرتبطة بالعام بلا فصل، والوصول الصباحي بلا الاثنين، والفصل الدراسي اختياري
  في المدارس — فالنطاق الفصلي ينكسر صامتًا.
- **لا حذف**: الخطأ يعالج بالإلغاء (VOIDED) مع سبب وفاعل ووقت.
- student بـ PROTECT: نسيان تسجيل الحذف النهائي يفشل صاخبًا (إلزام م4.1).
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from common.models import TimestampedModel

MAX_THRESHOLD = 200  # حد أعلى منطقي — أيام/مرات ضمن عام دراسي واحد


class WarningRuleType(models.TextChoices):
    UNEXCUSED_FULL_DAY_ABSENCE = "UNEXCUSED_FULL_DAY_ABSENCE", "غياب يوم كامل بدون عذر"
    MORNING_LATE_OCCURRENCES = "MORNING_LATE_OCCURRENCES", "التأخر عن الدوام الصباحي"
    # قابل للتوسعة لاحقًا (PERIOD_LATE_OCCURRENCES / UNEXCUSED_ABSENT_PERIODS)
    # دون تعديل بنية القواعد — لم تنفذ الآن عمدًا.


class WarningLevel(models.TextChoices):
    LEVEL_1 = "LEVEL_1", "الإنذار الأول"
    LEVEL_2 = "LEVEL_2", "الإنذار الثاني"
    LEVEL_3 = "LEVEL_3", "الإنذار الثالث"


LEVEL_ORDER = [WarningLevel.LEVEL_1, WarningLevel.LEVEL_2, WarningLevel.LEVEL_3]

DEFAULT_THRESHOLDS = {
    WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE: {"LEVEL_1": 3, "LEVEL_2": 5, "LEVEL_3": 10},
    WarningRuleType.MORNING_LATE_OCCURRENCES: {"LEVEL_1": 3, "LEVEL_2": 5, "LEVEL_3": 10},
}


class WarningRule(TimestampedModel):
    """عتبة مستوى واحد لنوع إنذار في مدرسة — صريحة لا JSON (قابلة للتوسعة والفهرسة)."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="warning_rules"
    )
    rule_type = models.CharField(max_length=32, choices=WarningRuleType.choices)
    level = models.CharField(max_length=10, choices=WarningLevel.choices)
    threshold = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(MAX_THRESHOLD)]
    )
    is_enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = "قاعدة إنذار"
        verbose_name_plural = "قواعد الإنذارات"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "rule_type", "level"],
                name="uniq_warning_rule_per_school_type_level",
            ),
            models.CheckConstraint(
                condition=models.Q(threshold__gte=1, threshold__lte=MAX_THRESHOLD),
                name="warning_rule_threshold_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school", "rule_type", "level"], name="warnrule_school_type_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.school_id} — {self.rule_type} {self.level} = {self.threshold}"


class WarningStatus(models.TextChoices):
    ISSUED = "ISSUED", "صادر"
    VOIDED = "VOIDED", "ملغى"


class StudentWarning(TimestampedModel):
    """إنذار صادر — سجل تاريخي إداري لا يعاد حسابه ولا يحذف.

    ‏metric_value_at_issue وthreshold_at_issue يجمّدان لحظة الإصدار؛ القيمة الحالية
    تحسب عند العرض بشكل منفصل (drift) — تحويل غياب إلى «بعذر» لاحقًا لا يمحو الإنذار.
    """

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="student_warnings"
    )
    student = models.ForeignKey(  # PROTECT: حارس تسجيل Purge
        "students.Student", on_delete=models.PROTECT, related_name="warnings"
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear", on_delete=models.PROTECT, related_name="student_warnings"
    )
    semester = models.ForeignKey(  # snapshot مرجعي فقط — النطاق هو العام
        "academics.Semester",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="student_warnings",
    )

    warning_type = models.CharField(max_length=32, choices=WarningRuleType.choices)
    level = models.CharField(max_length=10, choices=WarningLevel.choices)
    status = models.CharField(
        max_length=10, choices=WarningStatus.choices, default=WarningStatus.ISSUED
    )

    threshold_at_issue = models.PositiveSmallIntegerField()
    metric_value_at_issue = models.PositiveSmallIntegerField()

    # ---- Snapshot جاهزية م12: المستند يبنى من هذه الحقول وحدها ----
    student_name_snapshot = models.CharField(max_length=150)
    grade_name_snapshot = models.CharField(max_length=100, blank=True, default="")
    section_name_snapshot = models.CharField(max_length=50, blank=True, default="")
    # لا رقم هوية plaintext هنا — المقنع يكفي للمستند
    national_id_masked_snapshot = models.CharField(max_length=20, blank=True, default="")

    full_absence_days_at_issue = models.PositiveSmallIntegerField(default=0)
    unexcused_full_absence_days_at_issue = models.PositiveSmallIntegerField(default=0)
    excused_full_absence_days_at_issue = models.PositiveSmallIntegerField(default=0)
    absent_periods_at_issue = models.PositiveSmallIntegerField(default=0)
    unexcused_absent_periods_at_issue = models.PositiveSmallIntegerField(default=0)
    morning_late_occurrences_at_issue = models.PositiveSmallIntegerField(default=0)
    morning_late_minutes_at_issue = models.PositiveIntegerField(default=0)
    period_late_occurrences_at_issue = models.PositiveSmallIntegerField(default=0)
    period_late_minutes_at_issue = models.PositiveIntegerField(default=0)
    # تفاصيل النوع نفسه لحظة الإصدار فقط: أيام الغياب الكامل أو حالات التأخر
    # الصباحي. لا تخلط الأنواع ولا يعاد حسابها عند الطباعة لاحقًا.
    detail_rows_snapshot = models.JSONField(default=list, blank=True)

    issued_by_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )
    issued_at = models.DateTimeField()
    notes = models.CharField(max_length=300, blank=True, default="")

    voided_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        verbose_name = "إنذار طالب"
        verbose_name_plural = "إنذارات الطلاب"
        constraints = [
            # الحكم النهائي ضد التكرار (double click/تزامن): مستوى واحد صادر لكل
            # (طالب، عام، نوع). الملغى لا يحجز المستوى — يسمح بإعادة الإصدار (موثق).
            models.UniqueConstraint(
                fields=["school", "student", "academic_year", "warning_type", "level"],
                condition=models.Q(status=WarningStatus.ISSUED),
                name="uniq_issued_warning_per_scope",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school", "student", "warning_type", "level"],
                name="warn_school_student_type_idx",
            ),
            models.Index(fields=["school", "issued_at"], name="warn_school_issued_idx"),
            models.Index(
                fields=["school", "academic_year", "status"], name="warn_school_year_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student_id} — {self.warning_type} {self.level} ({self.status})"
