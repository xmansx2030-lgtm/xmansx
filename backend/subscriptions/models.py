"""طبقة SaaS: الباقات والاشتراكات والاستحقاقات (م16).

الفصل الحاكم:
- ‏`School` = المستأجر نفسه (بياناته التشغيلية).
- ‏`SaaSPlan` = عرض تجاري قابل لإعادة الاستخدام.
- ‏`SchoolSubscription` = عقد مدرسة بمدة وحالة.
- ‏`SubscriptionEntitlement` = **لقطة** حدود العقد وقت التفعيل.

قواعد بنيوية:
- حالة الاشتراك ليست حقلًا على School — School تبقى تعريف المستأجر.
- انتهاء/تعليق/تخفيض الاشتراك **لا يحذف أي بيان مدرسي** إطلاقًا.
- تعديل الباقة لاحقًا لا يغير عقود المدارس القائمة (اللقطة تحكم).
- لا اسم باقة داخل منطق الأعمال — القرار من الاستحقاقات.
"""

from django.db import models

from common.models import TimestampedModel


class BillingPeriod(models.TextChoices):
    MONTHLY = "MONTHLY", "شهري"
    SEMI_ANNUAL = "SEMI_ANNUAL", "نصف سنوي"
    ANNUAL = "ANNUAL", "سنوي"
    CUSTOM = "CUSTOM", "مخصص"


class EntitlementKey(models.TextChoices):
    """مفاتيح الاستحقاق — رقمية (حدود) أو منطقية (ميزات)."""

    MAX_STUDENTS = "MAX_STUDENTS", "حد الطلاب"
    MAX_STAFF = "MAX_STAFF", "حد الموظفين"
    MAX_DEVICES = "MAX_DEVICES", "حد الأجهزة"
    MAX_STORAGE_GB = "MAX_STORAGE_GB", "حد التخزين (جيجابايت)"

    ATTENDANCE = "ATTENDANCE", "الحضور"
    BIOMETRIC_DEVICES = "BIOMETRIC_DEVICES", "أجهزة البصمة"
    ROSTER_SYNC = "ROSTER_SYNC", "مزامنة القوائم"
    EXCUSES = "EXCUSES", "الأعذار"
    WARNINGS = "WARNINGS", "الإنذارات"
    DOCUMENTS = "DOCUMENTS", "المستندات"
    REFERRALS = "REFERRALS", "الإحالات"
    COUNSELING = "COUNSELING", "الإرشاد"
    EXECUTIVE_DASHBOARD = "EXECUTIVE_DASHBOARD", "لوحة الإدارة"


#: الحدود الرقمية — قيمتها عدد. البقية منطقية (مفعّلة/غير مفعّلة).
NUMERIC_ENTITLEMENTS = frozenset(
    {
        EntitlementKey.MAX_STUDENTS,
        EntitlementKey.MAX_STAFF,
        EntitlementKey.MAX_DEVICES,
        EntitlementKey.MAX_STORAGE_GB,
    }
)

FEATURE_ENTITLEMENTS = frozenset(set(EntitlementKey.values) - set(NUMERIC_ENTITLEMENTS))


class SaaSPlan(TimestampedModel):
    """باقة تجارية — التسعير هنا **بيانات وصفية** لا محرك دفع (م16 بلا دفع)."""

    code = models.SlugField("الرمز", max_length=40, unique=True)
    name_ar = models.CharField("الاسم", max_length=100)
    name_en = models.CharField(max_length=100, blank=True, default="")
    description = models.TextField(max_length=1000, blank=True, default="")

    is_active = models.BooleanField("متاحة", default=True)
    is_public = models.BooleanField("معروضة للعامة", default=False)

    billing_period = models.CharField(
        max_length=12, choices=BillingPeriod.choices, default=BillingPeriod.ANNUAL
    )
    price_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="SAR")

    trial_days_default = models.PositiveSmallIntegerField(default=30)

    class Meta:
        verbose_name = "باقة"
        verbose_name_plural = "الباقات"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.name_ar} ({self.code})"


class PlanEntitlement(TimestampedModel):
    """قيمة استحقاق افتراضية للباقة — تُنسخ إلى العقد عند التفعيل."""

    plan = models.ForeignKey(SaaSPlan, on_delete=models.CASCADE, related_name="entitlements")
    key = models.CharField(max_length=32, choices=EntitlementKey.choices)
    # الحد الرقمي: None = بلا حد. الميزة المنطقية تقرأ is_enabled.
    numeric_value = models.IntegerField(null=True, blank=True)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = "استحقاق باقة"
        verbose_name_plural = "استحقاقات الباقات"
        constraints = [
            models.UniqueConstraint(fields=["plan", "key"], name="uniq_entitlement_per_plan"),
        ]

    def __str__(self) -> str:
        return f"{self.plan_id}:{self.key}"


class SubscriptionStatus(models.TextChoices):
    TRIAL = "TRIAL", "تجريبي"
    ACTIVE = "ACTIVE", "نشط"
    GRACE_PERIOD = "GRACE_PERIOD", "مهلة سماح"
    EXPIRED = "EXPIRED", "منتهٍ"
    SUSPENDED = "SUSPENDED", "موقوف"
    CANCELLED = "CANCELLED", "ملغى"


#: الحالات التي تحجز المدرسة عن عقد ثانٍ (عقد فعّال واحد فقط في اللحظة)
LIVE_SUBSCRIPTION_STATUSES = (
    SubscriptionStatus.TRIAL,
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.GRACE_PERIOD,
)


class SchoolSubscription(TimestampedModel):
    """عقد اشتراك مدرسة — التاريخ يحفظ ولا يعاد كتابته عند التجديد."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="subscriptions"
    )
    # PROTECT: باقة عليها عقود لا تحذف — تعطّل بـ is_active
    plan = models.ForeignKey(SaaSPlan, on_delete=models.PROTECT, related_name="subscriptions")

    status = models.CharField(
        max_length=14, choices=SubscriptionStatus.choices, default=SubscriptionStatus.TRIAL
    )

    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()

    trial_started_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    grace_ends_at = models.DateTimeField(null=True, blank=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True, default="")

    suspended_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.CharField(max_length=300, blank=True, default="")

    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = "اشتراك مدرسة"
        verbose_name_plural = "اشتراكات المدارس"
        ordering = ["-starts_at", "-id"]
        constraints = [
            # عقد حي واحد لكل مدرسة — النقر المزدوج/التزامن يفشل هنا لا في التطبيق
            models.UniqueConstraint(
                fields=["school"],
                condition=models.Q(status__in=LIVE_SUBSCRIPTION_STATUSES),
                name="uniq_live_subscription_per_school",
            ),
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="subscription_ends_after_start",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=SubscriptionStatus.SUSPENDED)
                    | (models.Q(suspended_at__isnull=False) & ~models.Q(suspension_reason=""))
                ),
                name="suspension_requires_reason",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "ends_at"], name="sub_status_ends_idx"),
            models.Index(fields=["school", "status"], name="sub_school_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.school_id} — {self.plan_id} ({self.status})"


class SubscriptionEntitlement(TimestampedModel):
    """لقطة الحدود على العقد — تعديل الباقة لاحقًا لا يغير عقدًا قائمًا (بند 105)."""

    subscription = models.ForeignKey(
        SchoolSubscription, on_delete=models.CASCADE, related_name="entitlements"
    )
    key = models.CharField(max_length=32, choices=EntitlementKey.choices)
    numeric_value = models.IntegerField(null=True, blank=True)
    is_enabled = models.BooleanField(default=True)
    # تجاوز إداري لمدرسة بعينها فوق قيمة الباقة (بند 110)
    is_override = models.BooleanField(default=False)

    class Meta:
        verbose_name = "استحقاق اشتراك"
        verbose_name_plural = "استحقاقات الاشتراكات"
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "key"], name="uniq_entitlement_per_subscription"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.subscription_id}:{self.key}"


class SubscriptionEventType(models.TextChoices):
    CREATED = "CREATED", "إنشاء"
    TRIAL_STARTED = "TRIAL_STARTED", "بدء تجربة"
    TRIAL_EXTENDED = "TRIAL_EXTENDED", "تمديد تجربة"
    ACTIVATED = "ACTIVATED", "تفعيل"
    PLAN_CHANGED = "PLAN_CHANGED", "تغيير باقة"
    EXTENDED = "EXTENDED", "تمديد"
    GRACE_STARTED = "GRACE_STARTED", "بدء مهلة السماح"
    EXPIRED = "EXPIRED", "انتهاء"
    SUSPENDED = "SUSPENDED", "إيقاف"
    REACTIVATED = "REACTIVATED", "إعادة تفعيل"
    CANCELLED = "CANCELLED", "إلغاء"
    ENTITLEMENT_OVERRIDDEN = "ENTITLEMENT_OVERRIDDEN", "تجاوز استحقاق"


class SubscriptionEvent(models.Model):
    """الخط الزمني للعقد — أعداد وتواريخ فقط، لا بيانات حساسة."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="subscription_events"
    )
    subscription = models.ForeignKey(
        SchoolSubscription, on_delete=models.CASCADE, related_name="events"
    )
    event_type = models.CharField(max_length=24, choices=SubscriptionEventType.choices)
    actor = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reason = models.CharField(max_length=300, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "حدث اشتراك"
        verbose_name_plural = "أحداث الاشتراكات"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["school", "-created_at"], name="sub_event_school_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} — {self.subscription_id}"
