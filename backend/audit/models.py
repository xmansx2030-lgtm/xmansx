from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    LOGIN_SUCCESS = "LOGIN_SUCCESS", "تسجيل دخول ناجح"
    LOGIN_FAILED = "LOGIN_FAILED", "محاولة دخول فاشلة"
    LOGOUT = "LOGOUT", "تسجيل خروج"
    SWITCH_SCHOOL = "SWITCH_SCHOOL", "تبديل المدرسة"
    # المرحلة 3 — الإعدادات والتقويم والجداول
    SCHOOL_SETTINGS_UPDATED = "SCHOOL_SETTINGS_UPDATED", "تحديث إعدادات المدرسة"
    SCHOOL_NAME_UPDATED = "SCHOOL_NAME_UPDATED", "تحديث اسم المدرسة"
    ACADEMIC_YEAR_CREATED = "ACADEMIC_YEAR_CREATED", "إنشاء عام دراسي"
    ACADEMIC_YEAR_ACTIVATED = "ACADEMIC_YEAR_ACTIVATED", "تفعيل عام دراسي"
    ACADEMIC_YEAR_CLOSED = "ACADEMIC_YEAR_CLOSED", "إغلاق عام دراسي"
    SEMESTER_CREATED = "SEMESTER_CREATED", "إنشاء فصل دراسي"
    SEMESTER_ACTIVATED = "SEMESTER_ACTIVATED", "تفعيل فصل دراسي"
    BELL_SCHEDULE_CREATED = "BELL_SCHEDULE_CREATED", "إنشاء جدول حصص"
    BELL_SCHEDULE_UPDATED = "BELL_SCHEDULE_UPDATED", "تحديث جدول حصص"
    BELL_SCHEDULE_ARCHIVED = "BELL_SCHEDULE_ARCHIVED", "أرشفة جدول حصص"
    SCHOOL_DAY_SCHEDULE_CHANGED = "SCHOOL_DAY_SCHEDULE_CHANGED", "تغيير جداول أيام الدراسة"
    # المرحلة 4 — الطلاب والاستيراد
    STUDENT_IMPORT_UPLOADED = "STUDENT_IMPORT_UPLOADED", "رفع ملف استيراد"
    STUDENT_IMPORT_VALIDATED = "STUDENT_IMPORT_VALIDATED", "تحقق ملف استيراد"
    STUDENT_IMPORT_COMMITTED = "STUDENT_IMPORT_COMMITTED", "اعتماد استيراد"
    STUDENT_IMPORT_FAILED = "STUDENT_IMPORT_FAILED", "فشل استيراد"
    STUDENT_CREATED = "STUDENT_CREATED", "إنشاء طالب"
    STUDENT_UPDATED = "STUDENT_UPDATED", "تحديث طالب"
    STUDENT_STATUS_CHANGED = "STUDENT_STATUS_CHANGED", "تغيير حالة طالب"
    STUDENT_ENROLLMENT_CREATED = "STUDENT_ENROLLMENT_CREATED", "إنشاء قيد"
    STUDENT_ENROLLMENT_ENDED = "STUDENT_ENROLLMENT_ENDED", "إنهاء قيد"
    GRADE_CREATED = "GRADE_CREATED", "إنشاء صف"
    SECTION_CREATED = "SECTION_CREATED", "إنشاء فصل"
    # المرحلة 4.1 — دورة الحياة والحذف النهائي (بلا PII في metadata)
    # المرحلة 6 — الحضور وQR
    ATTENDANCE_STARTED = "ATTENDANCE_STARTED", "بدء تحضير"
    ATTENDANCE_SUBMITTED = "ATTENDANCE_SUBMITTED", "اعتماد تحضير"
    ATTENDANCE_EDITED = "ATTENDANCE_EDITED", "تعديل تحضير"
    SECTION_QR_ROTATED = "SECTION_QR_ROTATED", "تجديد QR فصل"
    # المرحلة 11 — الإنذارات (لا Audit لحساب الاستحقاق: ضجيج ممنوع)
    WARNING_RULES_UPDATED = "WARNING_RULES_UPDATED", "تعديل قواعد الإنذارات"
    STUDENT_WARNING_ISSUED = "STUDENT_WARNING_ISSUED", "إصدار إنذار طالب"
    STUDENT_WARNING_VOIDED = "STUDENT_WARNING_VOIDED", "إلغاء إنذار طالب"
    # المرحلة 8.5 — أجهزة الحضور والصباحي (لا Audit لكل بصمة — DeviceEvent هو السجل)
    BRIDGE_CREATED = "BRIDGE_CREATED", "إنشاء جسر أجهزة"
    BRIDGE_CREDENTIAL_ROTATED = "BRIDGE_CREDENTIAL_ROTATED", "تدوير اعتماد جسر"
    DEVICE_CREATED = "DEVICE_CREATED", "إضافة جهاز حضور"
    DEVICE_UPDATED = "DEVICE_UPDATED", "تعديل جهاز حضور"
    DEVICE_DISABLED = "DEVICE_DISABLED", "إيقاف جهاز حضور"
    DEVICE_CONNECTION_TESTED = "DEVICE_CONNECTION_TESTED", "اختبار اتصال جهاز"
    DEVICE_USER_MAPPED = "DEVICE_USER_MAPPED", "مطابقة مستخدم جهاز"
    DEVICE_USER_UNMAPPED = "DEVICE_USER_UNMAPPED", "إلغاء مطابقة مستخدم جهاز"
    MORNING_ARRIVAL_MANUAL_CREATED = "MORNING_ARRIVAL_MANUAL_CREATED", "وصول يدوي"
    MORNING_ARRIVAL_CORRECTED = "MORNING_ARRIVAL_CORRECTED", "تصحيح وصول"
    STUDENT_PERMANENTLY_PURGED = "STUDENT_PERMANENTLY_PURGED", "حذف نهائي لطالب"
    STUDENT_BULK_PURGE_STARTED = "STUDENT_BULK_PURGE_STARTED", "بدء حذف جماعي"
    STUDENT_BULK_PURGE_COMPLETED = "STUDENT_BULK_PURGE_COMPLETED", "اكتمال حذف جماعي"
    # المرحلة 10 — أعذار الغياب (لا PII صحية في metadata — أعداد ومعرفات فقط)
    EXCUSE_CREATED = "EXCUSE_CREATED", "تسجيل عذر غياب"
    EXCUSE_UPDATED = "EXCUSE_UPDATED", "تحديث عذر غياب"
    EXCUSE_APPROVED = "EXCUSE_APPROVED", "اعتماد عذر غياب"
    EXCUSE_REJECTED = "EXCUSE_REJECTED", "رفض عذر غياب"
    EXCUSE_CANCELLED = "EXCUSE_CANCELLED", "إلغاء عذر غياب"
    EXCUSE_ATTACHMENT_UPLOADED = "EXCUSE_ATTACHMENT_UPLOADED", "رفع مرفق عذر"
    EXCUSE_ATTACHMENT_REMOVED = "EXCUSE_ATTACHMENT_REMOVED", "حذف مرفق عذر"
    # المرحلة 12 — الإجراءات والمستندات (بلا محتوى PDF ولا snapshot كامل: البند 94)
    STUDENT_ACTION_CREATED = "STUDENT_ACTION_CREATED", "تسجيل إجراء طلابي"
    STUDENT_ACTION_CANCELLED = "STUDENT_ACTION_CANCELLED", "إلغاء إجراء طلابي"
    DOCUMENT_GENERATION_REQUESTED = "DOCUMENT_GENERATION_REQUESTED", "طلب إنشاء مستند"
    DOCUMENT_GENERATED = "DOCUMENT_GENERATED", "إنشاء مستند"
    DOCUMENT_GENERATION_FAILED = "DOCUMENT_GENERATION_FAILED", "فشل إنشاء مستند"
    DOCUMENT_VOIDED = "DOCUMENT_VOIDED", "إلغاء مستند"
    DOCUMENT_DOWNLOADED = "DOCUMENT_DOWNLOADED", "تنزيل مستند"
    # المرحلة 5 — الموظفون والدعوات
    STAFF_IMPORT_UPLOADED = "STAFF_IMPORT_UPLOADED", "رفع ملف موظفين"
    STAFF_IMPORT_VALIDATED = "STAFF_IMPORT_VALIDATED", "تحقق ملف موظفين"
    STAFF_IMPORT_COMMITTED = "STAFF_IMPORT_COMMITTED", "اعتماد استيراد موظفين"
    STAFF_IMPORT_FAILED = "STAFF_IMPORT_FAILED", "فشل استيراد موظفين"
    STAFF_PROFILE_CREATED = "STAFF_PROFILE_CREATED", "إنشاء ملف موظف"
    STAFF_PROFILE_UPDATED = "STAFF_PROFILE_UPDATED", "تحديث ملف موظف"
    SCHOOL_MEMBERSHIP_INVITED = "SCHOOL_MEMBERSHIP_INVITED", "دعوة عضوية"
    SCHOOL_MEMBERSHIP_ACCEPTED = "SCHOOL_MEMBERSHIP_ACCEPTED", "قبول دعوة"
    SCHOOL_MEMBERSHIP_DECLINED = "SCHOOL_MEMBERSHIP_DECLINED", "رفض دعوة"
    STAFF_ROLE_ADDED = "STAFF_ROLE_ADDED", "إضافة دور"
    STAFF_ROLE_REMOVED = "STAFF_ROLE_REMOVED", "إزالة دور"
    STAFF_SUSPENDED = "STAFF_SUSPENDED", "إيقاف موظف"
    STAFF_REACTIVATED = "STAFF_REACTIVATED", "إعادة تفعيل موظف"
    INITIAL_PASSWORD_CHANGED = "INITIAL_PASSWORD_CHANGED", "تغيير كلمة المرور الأولية"


class AuditLog(models.Model):
    """سجل تدقيق append-only — لا حذف ولا تعديل (ADR-010).

    ممنوع في metadata: كلمات المرور، أرقام الهوية/الجوال الكاملة، أي محتوى حساس.
    """

    school = models.ForeignKey(
        "schools.School",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=50, db_index=True)
    target_type = models.CharField(max_length=50, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "حدث تدقيق"
        verbose_name_plural = "سجل التدقيق"
        indexes = [
            models.Index(fields=["school", "created_at"], name="audit_school_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} by {self.actor_id} @ {self.created_at:%Y-%m-%d %H:%M}"
