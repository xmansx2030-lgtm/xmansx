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
