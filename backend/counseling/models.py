"""إدارة الحالات الإرشادية وخطط المتابعة (م14).

**ليست نظامًا صحيًا** (البند 2): لا تشخيص نفسي ولا طبي ولا خطة علاجية ولا دواء.
المرشد يسجل ملاحظات تربوية وإجراءات متابعة وأهدافًا ونتائج — لا أكثر.

الفصل الحاكم (البند 6):
- ‏`StudentReferral` (م13) = **سبب** الإحالة وطلب المتابعة.
- ‏`CounselorCase` (هنا) = **ملف** المتابعة الإرشادية وما جرى فيه.

قواعد بنيوية:
- لا حذف نهائي من سير العمل: الجلسة الخاطئة تُلغى (VOIDED)، والحالة تُغلق بسبب.
- ‏`status` مصدر الحقيقة الوحيد — لا `is_closed` موازٍ (البند 10).
- ‏student بـ PROTECT: نسيان تسجيل الحذف النهائي يفشل صاخبًا (إلزام م4.1).
"""

from django.db import models

from common.models import TimestampedModel


class CaseStatus(models.TextChoices):
    """الحالات المطبقة فعليًا فقط (البند 9) — لا حالة بلا انتقال مستخدم."""

    OPEN = "OPEN", "مفتوحة"
    UNDER_ASSESSMENT = "UNDER_ASSESSMENT", "قيد الدراسة"
    FOLLOW_UP_ACTIVE = "FOLLOW_UP_ACTIVE", "متابعة جارية"
    RESOLVED = "RESOLVED", "تم التحسن"
    CLOSED = "CLOSED", "مغلقة"


#: الحالات التي تعتبر الملف حيًا (تحجز الطالب عن ملف ثانٍ)
LIVE_CASE_STATUSES = (
    CaseStatus.OPEN,
    CaseStatus.UNDER_ASSESSMENT,
    CaseStatus.FOLLOW_UP_ACTIVE,
    CaseStatus.RESOLVED,
)

#: انتقالات مسموحة — تمنع قفزات غير مفهومة في سير العمل
ALLOWED_STATUS_FLOW: dict[str, tuple[str, ...]] = {
    CaseStatus.OPEN: (CaseStatus.UNDER_ASSESSMENT, CaseStatus.FOLLOW_UP_ACTIVE),
    CaseStatus.UNDER_ASSESSMENT: (CaseStatus.FOLLOW_UP_ACTIVE, CaseStatus.RESOLVED),
    CaseStatus.FOLLOW_UP_ACTIVE: (CaseStatus.UNDER_ASSESSMENT, CaseStatus.RESOLVED),
    CaseStatus.RESOLVED: (CaseStatus.FOLLOW_UP_ACTIVE,),
    CaseStatus.CLOSED: (),  # الإغلاق والفتح عمليتان مستقلتان لهما سببهما
}


class CasePriority(models.TextChoices):
    NORMAL = "NORMAL", "عادية"
    HIGH = "HIGH", "مرتفعة"
    # لا تصنيف خطر آلي في م14 (البند 58) — الأولوية قرار بشري


class ImprovementStatus(models.TextChoices):
    IMPROVED = "IMPROVED", "تحسن"
    PARTIALLY_IMPROVED = "PARTIALLY_IMPROVED", "تحسن جزئي"
    UNCHANGED = "UNCHANGED", "بلا تغيير"
    WORSENED = "WORSENED", "تراجع"
    NOT_ASSESSED = "NOT_ASSESSED", "لم يقيّم"


class CaseClosureReason(models.TextChoices):
    GOALS_MET = "GOALS_MET", "تحققت أهداف الخطة"
    IMPROVED = "IMPROVED", "تحسن الطالب"
    NO_LONGER_REQUIRES_FOLLOW_UP = "NO_LONGER_REQUIRES_FOLLOW_UP", "لم تعد المتابعة لازمة"
    TRANSFERRED = "TRANSFERRED", "انتقل الطالب"
    GRADUATED = "GRADUATED", "تخرج الطالب"
    REFERRED_EXTERNALLY = "REFERRED_EXTERNALLY", "أُحيل لجهة خارجية"
    OTHER = "OTHER", "سبب آخر"


class CounselorCase(TimestampedModel):
    """ملف متابعة إرشادية لطالب — مفتوح من إحالة مستلمة."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="counselor_cases"
    )
    student = models.ForeignKey(  # PROTECT: حارس تسجيل Purge
        "students.Student", on_delete=models.PROTECT, related_name="counselor_cases"
    )
    # PROTECT: الحالة تُحذف قبل الإحالة في دورة الحذف (ترتيب مسجل ومختبر)
    primary_referral = models.ForeignKey(
        "referrals.StudentReferral", on_delete=models.PROTECT, related_name="cases"
    )
    # ‏SET_NULL كإحالات م13: إيقاف عضوية المرشد لا يمحو تاريخ الحالة (البند 96)
    assigned_counselor_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="counselor_cases",
    )

    status = models.CharField(
        max_length=20, choices=CaseStatus.choices, default=CaseStatus.OPEN
    )
    priority = models.CharField(
        max_length=10, choices=CasePriority.choices, default=CasePriority.NORMAL
    )

    opened_by_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )
    opened_at = models.DateTimeField()
    # لقطة وقت فتح الملف — لا يعاد حسابها، والمؤشر الحالي يقرأ منفصلًا (البند 18)
    snapshot_data = models.JSONField(default=dict, blank=True)

    summary = models.TextField(max_length=2000, blank=True, default="")

    closed_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closure_reason = models.CharField(
        max_length=32, choices=CaseClosureReason.choices, blank=True, default=""
    )
    outcome_summary = models.TextField(max_length=2000, blank=True, default="")
    improvement_status = models.CharField(
        max_length=20,
        choices=ImprovementStatus.choices,
        blank=True,
        default="",
    )

    last_activity_at = models.DateTimeField()  # لفرز «الأقدم بلا متابعة» بلا N+1

    class Meta:
        verbose_name = "حالة إرشادية"
        verbose_name_plural = "الحالات الإرشادية"
        constraints = [
            # ملف واحد لكل إحالة: النقر المزدوج أو طلبان متزامنان ⇒ ملف واحد
            models.UniqueConstraint(
                fields=["primary_referral"], name="uniq_case_per_referral"
            ),
            # الإغلاق يلزمه سبب وفاعل ووقت — لا إغلاق شبحي (البند 49)
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=CaseStatus.CLOSED)
                    | (
                        models.Q(closed_at__isnull=False)
                        & ~models.Q(closure_reason="")
                    )
                ),
                name="case_closed_requires_reason",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school", "assigned_counselor_membership", "status"],
                name="case_school_counselor_idx",
            ),
            models.Index(fields=["school", "student", "status"], name="case_school_student_idx"),
            models.Index(fields=["school", "-last_activity_at"], name="case_school_activity_idx"),
        ]

    def __str__(self) -> str:
        return f"حالة {self.student_id} ({self.status})"


class SessionType(models.TextChoices):
    STUDENT_MEETING = "STUDENT_MEETING", "مقابلة الطالب"
    PARENT_MEETING = "PARENT_MEETING", "مقابلة ولي الأمر"
    PHONE_CALL = "PHONE_CALL", "اتصال هاتفي"
    TEACHER_CONSULTATION = "TEACHER_CONSULTATION", "تشاور مع معلم"
    CASE_REVIEW = "CASE_REVIEW", "مراجعة الحالة"
    OTHER = "OTHER", "أخرى"


class SessionStatus(models.TextChoices):
    RECORDED = "RECORDED", "مسجلة"
    VOIDED = "VOIDED", "ملغاة"


class CounselorSession(TimestampedModel):
    """جلسة/تواصل موثق داخل الحالة — حقول واضحة لا نص حر واحد (البند 22)."""

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    case = models.ForeignKey(
        CounselorCase, on_delete=models.CASCADE, related_name="sessions"
    )

    session_type = models.CharField(max_length=24, choices=SessionType.choices)
    occurred_at = models.DateTimeField()

    summary = models.TextField(max_length=2000)
    observations = models.TextField(max_length=2000, blank=True, default="")
    outcome = models.TextField(max_length=1000, blank=True, default="")

    status = models.CharField(
        max_length=10, choices=SessionStatus.choices, default=SessionStatus.RECORDED
    )
    created_by_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )
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
        verbose_name = "جلسة إرشادية"
        verbose_name_plural = "الجلسات الإرشادية"
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=SessionStatus.VOIDED)
                    | models.Q(voided_at__isnull=False)
                ),
                name="session_voided_requires_timestamp",
            ),
        ]
        indexes = [
            models.Index(fields=["case", "-occurred_at"], name="session_case_time_idx"),
            models.Index(fields=["school", "session_type"], name="session_school_type_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.session_type} — حالة {self.case_id}"


class PlanStatus(models.TextChoices):
    DRAFT = "DRAFT", "مسودة"
    ACTIVE = "ACTIVE", "نشطة"
    COMPLETED = "COMPLETED", "مكتملة"
    CANCELLED = "CANCELLED", "ملغاة"


class CounselorFollowUpPlan(TimestampedModel):
    """خطة متابعة داخل الحالة — نشطة واحدة كحد أقصى (البند 27، بقيد قاعدة بيانات)."""

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    case = models.ForeignKey(CounselorCase, on_delete=models.CASCADE, related_name="plans")

    title = models.CharField(max_length=200)
    status = models.CharField(
        max_length=10, choices=PlanStatus.choices, default=PlanStatus.DRAFT
    )
    start_date = models.DateField()
    target_end_date = models.DateField(null=True, blank=True)

    created_by_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(max_length=2000, blank=True, default="")

    class Meta:
        verbose_name = "خطة متابعة"
        verbose_name_plural = "خطط المتابعة"
        constraints = [
            models.UniqueConstraint(
                fields=["case"],
                condition=models.Q(status=PlanStatus.ACTIVE),
                name="uniq_active_plan_per_case",
            ),
        ]
        indexes = [
            models.Index(fields=["case", "status"], name="plan_case_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} — حالة {self.case_id}"


class GoalType(models.TextChoices):
    ATTENDANCE = "ATTENDANCE", "المواظبة"
    MORNING_LATENESS = "MORNING_LATENESS", "التأخر الصباحي"
    PERIOD_LATENESS = "PERIOD_LATENESS", "التأخر عن الحصص"
    ACADEMIC = "ACADEMIC", "الأداء الدراسي"
    CLASSROOM_BEHAVIOR = "CLASSROOM_BEHAVIOR", "السلوك الصفي"
    PARTICIPATION = "PARTICIPATION", "المشاركة"
    CUSTOM = "CUSTOM", "هدف مخصص"


class GoalStatus(models.TextChoices):
    OPEN = "OPEN", "قائم"
    COMPLETED = "COMPLETED", "تحقق"
    CANCELLED = "CANCELLED", "ملغى"


class FollowUpGoal(TimestampedModel):
    """هدف داخل الخطة — رقمي أو وصفي (القيم اختيارية عمدًا — البند 32)."""

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    plan = models.ForeignKey(
        CounselorFollowUpPlan, on_delete=models.CASCADE, related_name="goals"
    )

    goal_type = models.CharField(max_length=24, choices=GoalType.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(max_length=1000, blank=True, default="")

    baseline_value = models.IntegerField(null=True, blank=True)
    target_value = models.IntegerField(null=True, blank=True)
    unit = models.CharField(max_length=20, blank=True, default="")

    status = models.CharField(
        max_length=10, choices=GoalStatus.choices, default=GoalStatus.OPEN
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "هدف متابعة"
        verbose_name_plural = "أهداف المتابعة"
        indexes = [models.Index(fields=["plan", "status"], name="goal_plan_status_idx")]

    def __str__(self) -> str:
        return f"{self.title} — خطة {self.plan_id}"


class ActivityType(models.TextChoices):
    STUDENT_CHECK_IN = "STUDENT_CHECK_IN", "متابعة مع الطالب"
    PARENT_CONTACT = "PARENT_CONTACT", "تواصل مع ولي الأمر"
    TEACHER_OBSERVATION = "TEACHER_OBSERVATION", "طلب ملاحظة معلم"
    ATTENDANCE_REVIEW = "ATTENDANCE_REVIEW", "مراجعة المواظبة"
    BEHAVIOR_OBSERVATION = "BEHAVIOR_OBSERVATION", "ملاحظة سلوكية"
    FOLLOW_UP_MEETING = "FOLLOW_UP_MEETING", "لقاء متابعة"
    OTHER = "OTHER", "أخرى"


class ActivityStatus(models.TextChoices):
    PENDING = "PENDING", "قيد التنفيذ"
    COMPLETED = "COMPLETED", "منفذ"
    CANCELLED = "CANCELLED", "ملغى"


class FollowUpActivity(TimestampedModel):
    """إجراء ضمن خطة المتابعة — له موعد وحالة تنفيذ."""

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    plan = models.ForeignKey(
        CounselorFollowUpPlan, on_delete=models.CASCADE, related_name="activities"
    )

    activity_type = models.CharField(max_length=24, choices=ActivityType.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(max_length=1000, blank=True, default="")
    due_date = models.DateField(null=True, blank=True)

    status = models.CharField(
        max_length=10, choices=ActivityStatus.choices, default=ActivityStatus.PENDING
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "إجراء متابعة"
        verbose_name_plural = "إجراءات المتابعة"
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=ActivityStatus.COMPLETED)
                    | models.Q(completed_at__isnull=False)
                ),
                name="activity_completed_requires_timestamp",
            ),
        ]
        indexes = [
            models.Index(
                fields=["plan", "status", "due_date"], name="activity_plan_status_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} — خطة {self.plan_id}"


class FollowUpRequestType(models.TextChoices):
    ACADEMIC_OBSERVATION = "ACADEMIC_OBSERVATION", "ملاحظة دراسية"
    CLASSROOM_BEHAVIOR = "CLASSROOM_BEHAVIOR", "سلوك صفي"
    PARTICIPATION = "PARTICIPATION", "المشاركة"
    HOMEWORK = "HOMEWORK", "الواجبات"
    ATTENDANCE_OBSERVATION = "ATTENDANCE_OBSERVATION", "ملاحظة مواظبة"
    CUSTOM = "CUSTOM", "أخرى"


class FollowUpRequestStatus(models.TextChoices):
    PENDING = "PENDING", "بانتظار الرد"
    ANSWERED = "ANSWERED", "تم الرد"
    CANCELLED = "CANCELLED", "ملغى"


class TeacherFollowUpRequest(TimestampedModel):
    """طلب المرشد ملاحظة من معلم عن طالب الحالة.

    **خصوصية المعلم (البنود 70-71):** المعلم يرى سؤاله وطالبه وردّه فقط — لا جلسات
    ولا ملاحظات مرشد ولا ردود زملائه ولا تحليل الإغلاق.
    """

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    case = models.ForeignKey(
        CounselorCase, on_delete=models.CASCADE, related_name="teacher_requests"
    )

    requested_from_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )
    requested_by_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )

    request_type = models.CharField(max_length=24, choices=FollowUpRequestType.choices)
    question = models.TextField(max_length=1000)
    due_date = models.DateField(null=True, blank=True)

    status = models.CharField(
        max_length=10,
        choices=FollowUpRequestStatus.choices,
        default=FollowUpRequestStatus.PENDING,
    )
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "طلب متابعة معلم"
        verbose_name_plural = "طلبات متابعة المعلمين"
        indexes = [
            models.Index(
                fields=["school", "requested_from_membership", "status"],
                name="req_school_teacher_idx",
            ),
            models.Index(fields=["case", "status"], name="req_case_status_idx"),
        ]

    def __str__(self) -> str:
        return f"طلب {self.request_type} — حالة {self.case_id}"


class TeacherFollowUpResponse(TimestampedModel):
    """رد المعلم — **ثابت بعد الإرسال** (البند 44): التصحيح بطلب/رد جديد."""

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    request = models.OneToOneField(
        TeacherFollowUpRequest, on_delete=models.CASCADE, related_name="response"
    )
    responded_by_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )

    observation = models.TextField(max_length=2000)
    improvement_status = models.CharField(max_length=24)
    notes = models.TextField(max_length=1000, blank=True, default="")

    class Meta:
        verbose_name = "رد متابعة معلم"
        verbose_name_plural = "ردود متابعة المعلمين"

    def __str__(self) -> str:
        return f"رد على الطلب {self.request_id}"


class TeacherImprovementStatus(models.TextChoices):
    IMPROVED = "IMPROVED", "تحسن"
    UNCHANGED = "UNCHANGED", "بلا تغيير"
    WORSE = "WORSE", "تراجع"
    NOT_ENOUGH_INFORMATION = "NOT_ENOUGH_INFORMATION", "معلومات غير كافية"


class CaseEventType(models.TextChoices):
    CASE_OPENED = "CASE_OPENED", "فتح الحالة"
    SESSION_ADDED = "SESSION_ADDED", "إضافة جلسة"
    SESSION_VOIDED = "SESSION_VOIDED", "إلغاء جلسة"
    PLAN_CREATED = "PLAN_CREATED", "إنشاء خطة"
    PLAN_ACTIVATED = "PLAN_ACTIVATED", "تفعيل خطة"
    PLAN_COMPLETED = "PLAN_COMPLETED", "إكمال خطة"
    PLAN_CANCELLED = "PLAN_CANCELLED", "إلغاء خطة"
    GOAL_ADDED = "GOAL_ADDED", "إضافة هدف"
    GOAL_COMPLETED = "GOAL_COMPLETED", "تحقق هدف"
    ACTIVITY_ADDED = "ACTIVITY_ADDED", "إضافة إجراء"
    ACTIVITY_COMPLETED = "ACTIVITY_COMPLETED", "تنفيذ إجراء"
    TEACHER_FOLLOW_UP_REQUESTED = "TEACHER_FOLLOW_UP_REQUESTED", "طلب متابعة معلم"
    TEACHER_RESPONSE_RECEIVED = "TEACHER_RESPONSE_RECEIVED", "ورود رد معلم"
    STATUS_CHANGED = "STATUS_CHANGED", "تغيير الحالة"
    COUNSELOR_REASSIGNED = "COUNSELOR_REASSIGNED", "تغيير المرشد"
    CASE_CLOSED = "CASE_CLOSED", "إغلاق الحالة"
    CASE_REOPENED = "CASE_REOPENED", "إعادة فتح الحالة"


class CounselorCaseEvent(models.Model):
    """الخط الزمني للحالة — واجهة عمل، منفصل عن سجل التدقيق الأمني (البند 48)."""

    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    case = models.ForeignKey(CounselorCase, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=32, choices=CaseEventType.choices)
    actor_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "حدث حالة"
        verbose_name_plural = "أحداث الحالات"
        indexes = [
            models.Index(fields=["case", "-created_at"], name="caseevent_case_time_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} — حالة {self.case_id}"
