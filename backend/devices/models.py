"""أجهزة الحضور والجسر المحلي والحضور الصباحي (م8.5).

قواعد صلبة:
- **لا بيانات بيومترية إطلاقًا**: لا قوالب بصمة/وجه ولا صور — أحداث إثبات حضور فقط
  (external_user_id + occurred_at + طريقة التحقق).
- مصدران منفصلان بلا دمج: الحضور الصباحي (SchoolArrival) ≠ حضور الحصص
  (AttendanceSession/Mark) — وعداد تأخر الدوام ≠ عداد تأخر الحصص.
- عدم وجود Arrival لا يعني غيابًا أبدًا (جهاز معطل/بوابة أخرى/مزامنة متأخرة).
- هوية المدرسة من credential الجسر — لا school_id من أي payload.
- أسرار الجهاز مشفرة At-Rest ولا تعود في أي API/Log/Audit.
- student بـ PROTECT في السجلات الشخصية: نسيان تسجيل Purge يفشل صاخبًا.
"""

from django.db import models

from common.models import TimestampedModel

# الجسر/الجهاز يعد Offline بعد هذه المدة بلا إشارة حياة — سياسة نظام موثقة
# (‏heartbeat كل 60 ثانية → 5 دقائق = 5 دورات فائتة)
OFFLINE_AFTER_MINUTES = 5


class BridgeStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "فعال"
    DISABLED = "DISABLED", "موقوف"


class DeviceBridgeInstallation(TimestampedModel):
    """تثبيت جسر أجهزة لمدرسة — credential يظهر مرة واحدة ويخزن hash فقط."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="device_bridges"
    )
    installation_name = models.CharField("اسم التثبيت", max_length=100)
    installation_identifier = models.CharField(max_length=32, unique=True)
    # SHA-256 للسر العشوائي عالي الإنتروبيا (لا حاجة KDF بطيء — يتحقق كل طلب جسر)
    credential_hash = models.CharField(max_length=64)
    status = models.CharField(
        max_length=10, choices=BridgeStatus.choices, default=BridgeStatus.ACTIVE
    )
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "جسر أجهزة"
        verbose_name_plural = "جسور الأجهزة"

    def __str__(self) -> str:
        return f"{self.installation_name} ({self.school_id})"


class DeviceStatus(models.TextChoices):
    ONLINE = "ONLINE", "متصل"
    OFFLINE = "OFFLINE", "غير متصل"
    DEGRADED = "DEGRADED", "متقطع"
    DISABLED = "DISABLED", "موقوف"
    UNKNOWN = "UNKNOWN", "غير معروف"


class AttendanceDevice(TimestampedModel):
    """جهاز حضور داخل شبكة المدرسة — الجسر وحده يتصل به (لا اتصال من SaaS)."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="attendance_devices"
    )
    name = models.CharField("اسم الجهاز", max_length=100)
    vendor = models.CharField("الشركة", max_length=50, blank=True, default="")
    model = models.CharField("الموديل", max_length=100, blank=True, default="")
    serial_number = models.CharField(max_length=100, blank=True, default="")

    connection_type = models.CharField(max_length=20, default="TCP")
    local_ip = models.CharField("عنوان IP المحلي", max_length=45, blank=True, default="")
    local_port = models.PositiveIntegerField(null=True, blank=True)
    # سر اتصال الجهاز (إن لزم) — مشفر At-Rest، يعاد للجسر الموثق فقط
    connection_secret_encrypted = models.TextField(blank=True, default="")

    status = models.CharField(
        max_length=10, choices=DeviceStatus.choices, default=DeviceStatus.UNKNOWN
    )
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_successful_sync_at = models.DateTimeField(null=True, blank=True)
    # طلب اختبار اتصال معلق — الجسر يلتقطه في المزامنة التالية ويعيد النتيجة
    test_requested_at = models.DateTimeField(null=True, blank=True)
    test_result = models.JSONField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "جهاز حضور"
        verbose_name_plural = "أجهزة الحضور"

    def __str__(self) -> str:
        return f"{self.name} — {self.school_id}"


class IdentityStatus(models.TextChoices):
    MATCHED = "MATCHED", "مطابق"
    UNMATCHED = "UNMATCHED", "غير مطابق"
    CONFLICT = "CONFLICT", "متعارض"
    IGNORED = "IGNORED", "متجاهل"


class StudentDeviceIdentity(TimestampedModel):
    """ربط مستخدم الجهاز بطالب — لكل جهاز (قرار موثق: لا نفترض توحيد المعرفات
    بين أجهزة المدرسة؛ Device Group يضاف لاحقًا إن ثبت التوحيد)."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="device_identities"
    )
    device = models.ForeignKey(
        AttendanceDevice, on_delete=models.CASCADE, related_name="identities"
    )
    external_user_id = models.CharField(max_length=64)
    display_name = models.CharField(max_length=150, blank=True, default="")
    student = models.ForeignKey(  # PROTECT: حارس تسجيل Purge
        "students.Student",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="device_identities",
    )
    status = models.CharField(
        max_length=10, choices=IdentityStatus.choices, default=IdentityStatus.UNMATCHED
    )
    mapped_at = models.DateTimeField(null=True, blank=True)
    mapped_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "هوية مستخدم جهاز"
        verbose_name_plural = "هويات مستخدمي الأجهزة"
        constraints = [
            # نفس المعرف على نفس الجهاز لا يشير لطالبين
            models.UniqueConstraint(
                fields=["device", "external_user_id"],
                name="uniq_identity_per_device_external_id",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "student"], name="identity_school_student_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.device_id}#{self.external_user_id} → {self.student_id}"


class VerificationMethod(models.TextChoices):
    FINGERPRINT = "FINGERPRINT", "بصمة إصبع"
    FACE = "FACE", "وجه"
    CARD = "CARD", "بطاقة"
    PIN = "PIN", "رقم سري"
    OTHER = "OTHER", "أخرى"
    UNKNOWN = "UNKNOWN", "غير معروف"


class EventProcessingStatus(models.TextChoices):
    PROCESSED = "PROCESSED", "معالج"
    UNMATCHED = "UNMATCHED", "غير مطابق"
    IGNORED = "IGNORED", "متجاهل"


class DeviceEvent(TimestampedModel):
    """حدث إثبات حضور من جهاز — تشغيليّ (لا Audit لكل بصمة: ضجيج ممنوع)."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="device_events"
    )
    device = models.ForeignKey(
        AttendanceDevice, on_delete=models.CASCADE, related_name="events"
    )
    external_event_id = models.CharField(max_length=100, blank=True, default="")
    # مفتاح منع التكرار: external_event_id أو بصمة حتمية (device|user|time|type)
    dedupe_key = models.CharField(max_length=128)
    external_user_id = models.CharField(max_length=64)

    occurred_at = models.DateTimeField()  # وقت الحدث الحقيقي (من الجهاز)
    received_at = models.DateTimeField(auto_now_add=True)  # وقت وصوله للسحابة

    verification_method = models.CharField(
        max_length=15, choices=VerificationMethod.choices, default=VerificationMethod.UNKNOWN
    )
    event_type = models.CharField(max_length=20, default="CHECK_IN")

    student = models.ForeignKey(  # PROTECT: الحدث المرتبط بطالب يحذف في Purge (سياسة موثقة)
        "students.Student",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="device_events",
    )
    processing_status = models.CharField(
        max_length=10,
        choices=EventProcessingStatus.choices,
        default=EventProcessingStatus.UNMATCHED,
    )

    class Meta:
        verbose_name = "حدث جهاز"
        verbose_name_plural = "أحداث الأجهزة"
        constraints = [
            # الحكم النهائي ضد مضاعفة الحدث — ولو وصل 5 مرات
            models.UniqueConstraint(
                fields=["device", "dedupe_key"], name="uniq_event_per_device_key"
            ),
        ]
        indexes = [
            models.Index(fields=["school", "occurred_at"], name="devevent_school_time_idx"),
            models.Index(
                fields=["device", "processing_status"], name="devevent_device_status_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.device_id}#{self.external_user_id} @ {self.occurred_at}"


class ArrivalStatus(models.TextChoices):
    # لا ABSENT هنا — غياب البصمة ليس غيابًا عن المدرسة
    ON_TIME = "ON_TIME", "في الوقت"
    LATE = "LATE", "متأخر"


class ArrivalSource(models.TextChoices):
    BIOMETRIC = "BIOMETRIC", "جهاز"
    MANUAL = "MANUAL", "يدوي"


class SchoolArrival(TimestampedModel):
    """وصول الطالب للمدرسة صباحًا — سجل واحد لليوم، أول بصمة تحدده.

    الدقائق مخزنة (لا تشتق عند القراءة) — تغيير إعدادات الدوام لاحقًا لا يعيد
    كتابة أيام مضت؛ يعاد الحساب فقط عند تعديل الوصول نفسه.
    """

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="school_arrivals"
    )
    student = models.ForeignKey(  # PROTECT: حارس تسجيل Purge
        "students.Student", on_delete=models.PROTECT, related_name="school_arrivals"
    )
    attendance_date = models.DateField()

    first_arrival_at = models.DateTimeField()
    raw_late_minutes = models.PositiveIntegerField(default=0)
    counted_late_minutes = models.PositiveIntegerField(default=0)  # بعد فترة السماح

    status = models.CharField(max_length=10, choices=ArrivalStatus.choices)
    source = models.CharField(max_length=10, choices=ArrivalSource.choices)

    device_event = models.ForeignKey(
        DeviceEvent, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    recorded_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "وصول صباحي"
        verbose_name_plural = "الوصول الصباحي"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "student", "attendance_date"],
                name="uniq_arrival_per_student_date",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school", "attendance_date", "status"],
                name="arrival_school_date_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student_id} — {self.attendance_date} ({self.status})"


class SchoolArrivalChange(models.Model):
    """سجل تصحيحات الوصول — التاريخ لا يحذف (07:22 بصمة ← 07:08 تصحيح يبقى مرئيًا)."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="arrival_changes"
    )
    arrival = models.ForeignKey(
        SchoolArrival, on_delete=models.CASCADE, related_name="changes"
    )
    actor_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )
    previous_arrival_time = models.DateTimeField()
    new_arrival_time = models.DateTimeField()
    previous_status = models.CharField(max_length=10)
    new_status = models.CharField(max_length=10)
    previous_counted_late_minutes = models.PositiveIntegerField()
    new_counted_late_minutes = models.PositiveIntegerField()
    reason = models.CharField(max_length=300, blank=True, default="")
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تعديل وصول"
        verbose_name_plural = "تعديلات الوصول"

    def __str__(self) -> str:
        return f"{self.arrival_id}: {self.previous_arrival_time} → {self.new_arrival_time}"


class DeviceRosterSyncStatus(models.TextChoices):
    ANALYZING = "ANALYZING", "جارٍ الفحص"
    READY_FOR_REVIEW = "READY_FOR_REVIEW", "جاهز للمراجعة"
    APPROVED = "APPROVED", "معتمد"
    RUNNING = "RUNNING", "قيد التنفيذ"
    COMPLETED = "COMPLETED", "مكتمل"
    PARTIALLY_FAILED = "PARTIALLY_FAILED", "مكتمل جزئياً"
    FAILED = "FAILED", "فشل"
    CANCELLED = "CANCELLED", "ملغى"
    STALE = "STALE", "قديم"


class DeviceRosterSyncAction(models.TextChoices):
    MATCHED = "MATCHED", "مطابق"
    CREATE = "CREATE", "إضافة"
    UPDATE = "UPDATE", "تحديث"
    DELETE = "DELETE", "إزالة"
    CONFLICT = "CONFLICT", "تعارض"


class DeviceRosterSyncItemStatus(models.TextChoices):
    PENDING = "PENDING", "بانتظار التنفيذ"
    RUNNING = "RUNNING", "قيد التنفيذ"
    SUCCEEDED = "SUCCEEDED", "ناجح"
    FAILED_RETRYABLE = "FAILED_RETRYABLE", "فشل قابل للإعادة"
    FAILED_FINAL = "FAILED_FINAL", "فشل نهائي"
    SKIPPED = "SKIPPED", "متجاوز"


class DeviceRosterSyncJob(TimestampedModel):
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="device_roster_sync_jobs"
    )
    device = models.ForeignKey(
        AttendanceDevice, on_delete=models.CASCADE, related_name="roster_sync_jobs"
    )
    created_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        on_delete=models.PROTECT,
        related_name="device_roster_sync_jobs",
    )
    status = models.CharField(
        max_length=24,
        choices=DeviceRosterSyncStatus.choices,
        default=DeviceRosterSyncStatus.ANALYZING,
    )
    source_academic_year = models.ForeignKey(
        "academics.AcademicYear", null=True, blank=True, on_delete=models.PROTECT,
        related_name="device_roster_sync_jobs",
    )
    source_student_import = models.ForeignKey(
        "students.StudentImportJob", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="device_roster_sync_jobs",
    )
    roster_version = models.CharField(max_length=64, blank=True, default="")
    device_roster_version = models.CharField(max_length=64, blank=True, default="")
    matched_count = models.PositiveIntegerField(default=0)
    create_count = models.PositiveIntegerField(default=0)
    update_count = models.PositiveIntegerField(default=0)
    delete_count = models.PositiveIntegerField(default=0)
    conflict_count = models.PositiveIntegerField(default=0)
    read_requested_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["school", "device", "status"],
                name="roster_job_school_device_idx",
            ),
        ]


class DeviceRosterSyncItem(TimestampedModel):
    job = models.ForeignKey(DeviceRosterSyncJob, on_delete=models.CASCADE, related_name="items")
    device = models.ForeignKey(
        AttendanceDevice, on_delete=models.CASCADE, related_name="roster_sync_items"
    )
    student = models.ForeignKey(
        "students.Student", null=True, blank=True, on_delete=models.PROTECT,
        related_name="device_roster_sync_items",
    )
    external_user_id = models.CharField(max_length=64)
    action = models.CharField(max_length=10, choices=DeviceRosterSyncAction.choices)
    status = models.CharField(
        max_length=24,
        choices=DeviceRosterSyncItemStatus.choices,
        default=DeviceRosterSyncItemStatus.PENDING,
    )
    reason = models.CharField(max_length=200, blank=True, default="")
    error_code = models.CharField(max_length=80, blank=True, default="")
    safe_before_snapshot = models.JSONField(default=dict, blank=True)
    safe_after_snapshot = models.JSONField(default=dict, blank=True)
    command_id = models.CharField(max_length=64, blank=True, default="")
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["job", "action", "status"],
                name="roster_item_job_action_idx",
            ),
        ]
