from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    LOGIN_SUCCESS = "LOGIN_SUCCESS", "تسجيل دخول ناجح"
    LOGIN_FAILED = "LOGIN_FAILED", "محاولة دخول فاشلة"
    LOGOUT = "LOGOUT", "تسجيل خروج"
    SWITCH_SCHOOL = "SWITCH_SCHOOL", "تبديل المدرسة"


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
