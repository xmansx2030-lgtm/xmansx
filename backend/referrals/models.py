"""إحالات الطلاب إلى المرشد الطلابي (م13).

الإحالة **طلب متابعة رسمي يفتح حالة** لدى المرشد — ليست إنذارًا ولا إجراءً ولا
جلسة إرشادية ولا تشخيصًا. لا توجد ولن توجد حقول تشخيص طبي/نفسي هنا: ما يسجله
المعلم/الوكيل ملاحظة واقعية قابلة للملاحظة فقط (`description`).

ثلاثة نماذج:
- StudentReferral: الحالة نفسها + Snapshot لحظة الإحالة.
- StudentReferralContribution: ملاحظات معلمين آخرين على نفس الحالة (بدل إحالات مكررة).
- StudentReferralEvent: خط زمني للعرض (‏Audit للأمان، وهذا للمستخدم).
"""

from django.db import models

from common.models import TimestampedModel


class ReferralSourceType(models.TextChoices):
    """دور المُحيل لحظة الإحالة — snapshot لا يتغير إن تغيرت أدواره لاحقًا."""

    TEACHER = "TEACHER", "معلم"
    VICE_PRINCIPAL = "VICE_PRINCIPAL", "وكيل"
    SCHOOL_MANAGER = "SCHOOL_MANAGER", "مدير المدرسة"


class ReferralCategory(models.TextChoices):
    ATTENDANCE = "ATTENDANCE", "المواظبة"
    ACADEMIC = "ACADEMIC", "الأداء الدراسي"
    CLASSROOM_BEHAVIOR = "CLASSROOM_BEHAVIOR", "سلوك صفي"
    SOCIAL = "SOCIAL", "اجتماعي"
    OTHER = "OTHER", "أخرى"


class ReferralReason(models.TextChoices):
    # المواظبة — غالبًا من الوكيل/المدير
    REPEATED_ABSENCE = "REPEATED_ABSENCE", "غياب متكرر"
    REPEATED_MORNING_LATE = "REPEATED_MORNING_LATE", "تأخر صباحي متكرر"
    WARNING_ESCALATION = "WARNING_ESCALATION", "بلوغ إنذار"
    NO_IMPROVEMENT = "NO_IMPROVEMENT", "عدم تحسن بعد الإنذار"
    OTHER_ATTENDANCE = "OTHER_ATTENDANCE", "سبب مواظبة آخر"
    # الأداء الدراسي — للمعلم
    ACADEMIC_WEAKNESS = "ACADEMIC_WEAKNESS", "ضعف دراسي"
    ACADEMIC_DECLINE = "ACADEMIC_DECLINE", "تراجع دراسي"
    HOMEWORK_NONCOMPLIANCE = "HOMEWORK_NONCOMPLIANCE", "عدم إنجاز المهام"
    LOW_PARTICIPATION = "LOW_PARTICIPATION", "عدم المشاركة"
    OTHER_ACADEMIC = "OTHER_ACADEMIC", "سبب دراسي آخر"
    # سلوك صفي — للمعلم
    SLEEPING_IN_CLASS = "SLEEPING_IN_CLASS", "النوم داخل الحصة"
    REPEATED_DISTRACTION = "REPEATED_DISTRACTION", "تشتت متكرر"
    CLASSROOM_DISRUPTION = "CLASSROOM_DISRUPTION", "سلوك يؤثر في التعلم"
    LEARNING_BEHAVIOR_CONCERN = "LEARNING_BEHAVIOR_CONCERN", "سلوك تعلمي يحتاج متابعة"
    OTHER_CLASSROOM = "OTHER_CLASSROOM", "سبب صفي آخر"
    # اجتماعي — وصف ظاهر فقط بلا تشخيص
    PEER_INTERACTION_CONCERN = "PEER_INTERACTION_CONCERN", "مشكلة في التفاعل مع الزملاء"
    ISOLATION_CONCERN = "ISOLATION_CONCERN", "انعزال ملحوظ"
    OTHER_SOCIAL = "OTHER_SOCIAL", "سبب اجتماعي آخر"
    # عام
    COUNSELOR_MEETING_REQUEST = "COUNSELOR_MEETING_REQUEST", "طلب مقابلة المرشد"
    OTHER_GENERAL = "OTHER_GENERAL", "سبب آخر"


#: الأسباب المسموحة داخل كل فئة — مصدر الحقيقة الوحيد للتحقق والواجهة معًا
REASONS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    ReferralCategory.ATTENDANCE: (
        ReferralReason.REPEATED_ABSENCE,
        ReferralReason.REPEATED_MORNING_LATE,
        ReferralReason.WARNING_ESCALATION,
        ReferralReason.NO_IMPROVEMENT,
        ReferralReason.OTHER_ATTENDANCE,
    ),
    ReferralCategory.ACADEMIC: (
        ReferralReason.ACADEMIC_WEAKNESS,
        ReferralReason.ACADEMIC_DECLINE,
        ReferralReason.HOMEWORK_NONCOMPLIANCE,
        ReferralReason.LOW_PARTICIPATION,
        ReferralReason.OTHER_ACADEMIC,
    ),
    ReferralCategory.CLASSROOM_BEHAVIOR: (
        ReferralReason.SLEEPING_IN_CLASS,
        ReferralReason.REPEATED_DISTRACTION,
        ReferralReason.CLASSROOM_DISRUPTION,
        ReferralReason.LEARNING_BEHAVIOR_CONCERN,
        ReferralReason.OTHER_CLASSROOM,
    ),
    ReferralCategory.SOCIAL: (
        ReferralReason.PEER_INTERACTION_CONCERN,
        ReferralReason.ISOLATION_CONCERN,
        ReferralReason.OTHER_SOCIAL,
    ),
    ReferralCategory.OTHER: (
        ReferralReason.COUNSELOR_MEETING_REQUEST,
        ReferralReason.OTHER_GENERAL,
    ),
}

#: أسباب تُلزم بوصف مكتوب — «أخرى» بلا وصف لا تفيد المرشد بشيء
REASONS_REQUIRING_DESCRIPTION = frozenset(
    {
        ReferralReason.OTHER_ATTENDANCE,
        ReferralReason.OTHER_ACADEMIC,
        ReferralReason.OTHER_CLASSROOM,
        ReferralReason.OTHER_SOCIAL,
        ReferralReason.OTHER_GENERAL,
    }
)

#: المعلم يحيل لما يلاحظه في صفه؛ فئة المواظبة بيد الوكيل/المدير (بند 121)
CATEGORIES_BY_SOURCE: dict[str, tuple[str, ...]] = {
    ReferralSourceType.TEACHER: (
        ReferralCategory.ACADEMIC,
        ReferralCategory.CLASSROOM_BEHAVIOR,
        ReferralCategory.SOCIAL,
        ReferralCategory.OTHER,
    ),
    ReferralSourceType.VICE_PRINCIPAL: tuple(ReferralCategory.values),
    ReferralSourceType.SCHOOL_MANAGER: tuple(ReferralCategory.values),
}


class ReferralStatus(models.TextChoices):
    """دورة الإحالة من المعلم، مرورًا بالوكيل، ثم المرشد عند الحاجة."""

    PENDING_VICE = "PENDING_VICE", "بانتظار الوكيل"
    UNDER_VICE_REVIEW = "UNDER_VICE_REVIEW", "قيد معالجة الوكيل"
    REFERRED = "REFERRED", "محوّلة للمرشد"
    ACKNOWLEDGED = "ACKNOWLEDGED", "قيد متابعة المرشد"
    CLOSED = "CLOSED", "مغلقة"
    CANCELLED = "CANCELLED", "ملغاة"


#: الحالات المفتوحة — أساس كشف التكرار
OPEN_STATUSES = (
    ReferralStatus.PENDING_VICE,
    ReferralStatus.UNDER_VICE_REVIEW,
    ReferralStatus.REFERRED,
    ReferralStatus.ACKNOWLEDGED,
)


class ReferralPriority(models.TextChoices):
    NORMAL = "NORMAL", "عادية"
    HIGH = "HIGH", "عاجلة"


class StudentReferral(TimestampedModel):
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="student_referrals"
    )
    # PROTECT عمدًا — نسيان تسجيل الحذف النهائي يفشل صاخبًا (نمط م4.1)
    student = models.ForeignKey(
        "students.Student", on_delete=models.PROTECT, related_name="referrals"
    )

    source_type = models.CharField(max_length=20, choices=ReferralSourceType.choices)
    category = models.CharField(max_length=20, choices=ReferralCategory.choices)
    reason_code = models.CharField(max_length=30, choices=ReferralReason.choices)
    description = models.TextField(max_length=1000, blank=True, default="")

    created_by_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )
    # المسؤولية الإدارية تُجمّد على الإحالة؛ تغيير توزيع الصفوف يؤثر في الجديد فقط.
    assigned_vice_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        on_delete=models.SET_NULL,
        related_name="assigned_vice_referrals",
        null=True,
        blank=True,
    )
    # SET_NULL: مغادرة المرشد المدرسة لا تحذف تاريخ الحالة (بند 89)
    assigned_counselor_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        on_delete=models.SET_NULL,
        related_name="assigned_referrals",
        null=True,
        blank=True,
    )
    # إحالة نابعة من إنذار (اختيارية) — الإحالة مستقلة ولا تشترط إنذارًا (بند 49)
    source_warning = models.ForeignKey(
        "student_warnings.StudentWarning",
        on_delete=models.SET_NULL,
        related_name="referrals",
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=25, choices=ReferralStatus.choices, default=ReferralStatus.PENDING_VICE
    )
    priority = models.CharField(
        max_length=10, choices=ReferralPriority.choices, default=ReferralPriority.NORMAL
    )

    # لقطة مختصرة لحالة الطالب لحظة الإحالة — لا نسخة من ملفه ولا هوية ولا جوال
    snapshot_data = models.JSONField(default=dict, blank=True)

    accepted_at = models.DateTimeField(null=True, blank=True)
    vice_reviewed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    closure_reason = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        verbose_name = "إحالة طالب"
        verbose_name_plural = "إحالات الطلاب"
        indexes = [
            models.Index(
                fields=["school", "student", "status"], name="referral_student_idx"
            ),
            models.Index(
                fields=["school", "assigned_counselor_membership", "status"],
                name="referral_counselor_idx",
            ),
            models.Index(
                fields=["school", "assigned_vice_membership", "status"],
                name="referral_vice_idx",
            ),
            models.Index(
                fields=["school", "category", "status"], name="referral_category_idx"
            ),
            models.Index(fields=["school", "-created_at"], name="referral_recent_idx"),
        ]
        constraints = [
            # الحالات المنتهية تحمل تاريخ إغلاق دائمًا، والمفتوحة لا تحمله
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=[ReferralStatus.CLOSED, ReferralStatus.CANCELLED],
                        closed_at__isnull=False,
                    )
                    | models.Q(
                        status__in=OPEN_STATUSES,
                        closed_at__isnull=True,
                    )
                ),
                name="referral_closed_at_matches_status",
            ),
            # لا يمكن إظهار حالة للمرشد قبل مرحلة التحويل، ولا دخول مرحلة
            # المرشد بلا مسؤول معيّن. الحالات المنتهية تحتفظ بتاريخها كما هو.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=[
                            ReferralStatus.PENDING_VICE,
                            ReferralStatus.UNDER_VICE_REVIEW,
                        ],
                        assigned_counselor_membership__isnull=True,
                    )
                    | models.Q(
                        status__in=[
                            ReferralStatus.REFERRED,
                            ReferralStatus.ACKNOWLEDGED,
                        ],
                        assigned_counselor_membership__isnull=False,
                    )
                    | models.Q(
                        status__in=[ReferralStatus.CLOSED, ReferralStatus.CANCELLED]
                    )
                ),
                name="referral_counselor_matches_stage",
            ),
        ]

    def __str__(self):
        return f"إحالة {self.get_reason_code_display()} — طالب {self.student_id}"

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


class ReferralObservationType(models.TextChoices):
    """نوع الملاحظة المضافة لحالة قائمة — وصف ما لوحظ لا تفسيره."""

    CLASSROOM_OBSERVATION = "CLASSROOM_OBSERVATION", "ملاحظة صفية"
    ACADEMIC_OBSERVATION = "ACADEMIC_OBSERVATION", "ملاحظة دراسية"
    ATTENDANCE_OBSERVATION = "ATTENDANCE_OBSERVATION", "ملاحظة مواظبة"
    COUNSELOR_INTAKE_NOTE = "COUNSELOR_INTAKE_NOTE", "ملاحظة استلام المرشد"
    OTHER_OBSERVATION = "OTHER_OBSERVATION", "ملاحظة أخرى"


class StudentReferralContribution(TimestampedModel):
    """ملاحظة تُضاف لحالة قائمة بدل فتح إحالة مكررة (بنود 34-37).

    غير قابلة للتعديل في م13: ما أُرسل يبقى كما كُتب (لا تعديل صامت).
    """

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    referral = models.ForeignKey(
        StudentReferral, on_delete=models.CASCADE, related_name="contributions"
    )
    created_by_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )
    observation_type = models.CharField(
        max_length=25, choices=ReferralObservationType.choices
    )
    notes = models.TextField(max_length=1000)

    class Meta:
        verbose_name = "ملاحظة على إحالة"
        verbose_name_plural = "ملاحظات الإحالات"
        indexes = [
            models.Index(fields=["referral", "created_at"], name="contribution_time_idx"),
        ]

    def __str__(self):
        return f"ملاحظة على الإحالة {self.referral_id}"


class ReferralEventType(models.TextChoices):
    CREATED = "CREATED", "أنشئت الإحالة"
    ROUTED_TO_VICE = "ROUTED_TO_VICE", "وُجّهت إلى الوكيل المسؤول"
    VICE_REVIEW_STARTED = "VICE_REVIEW_STARTED", "بدأ الوكيل معالجة الإحالة"
    FORWARDED_TO_COUNSELOR = "FORWARDED_TO_COUNSELOR", "حوّلها الوكيل إلى المرشد"
    ASSIGNED = "ASSIGNED", "تم تعيين مرشد"
    REASSIGNED = "REASSIGNED", "تم تغيير المرشد"
    ACKNOWLEDGED = "ACKNOWLEDGED", "تم استلام الإحالة"
    CONTRIBUTION_ADDED = "CONTRIBUTION_ADDED", "أضيفت ملاحظة"
    CLOSED = "CLOSED", "أُغلقت الإحالة"
    CANCELLED = "CANCELLED", "أُلغيت الإحالة"


class StudentReferralEvent(models.Model):
    """خط زمني للعرض داخل الحالة — منفصل عن Audit (الأخير للأمان لا للواجهة).

    ‏append-only: لا تعديل ولا حذف؛ ‏metadata_safe أعداد ومعرفات فقط بلا PII.
    """

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    referral = models.ForeignKey(
        StudentReferral, on_delete=models.CASCADE, related_name="events"
    )
    event_type = models.CharField(max_length=25, choices=ReferralEventType.choices)
    actor_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    metadata_safe = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "حدث إحالة"
        verbose_name_plural = "أحداث الإحالات"
        indexes = [
            models.Index(fields=["referral", "created_at"], name="referral_event_idx"),
        ]

    def __str__(self):
        return f"{self.event_type} @ {self.referral_id}"
