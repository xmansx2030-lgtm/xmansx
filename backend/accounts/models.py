from django.contrib.auth.models import AbstractUser
from django.db import models

from accounts.managers import UserManager
from accounts.mobile import validate_mobile
from common.models import TimestampedModel


class User(AbstractUser, TimestampedModel):
    """المستخدم العالمي — حساب واحد عبر كل المدارس، معرفه رقم الجوال المطبّع.

    قواعد ثابتة (ADR-003):
    - لا `school_id` ولا `role` هنا: الانتماء عبر SchoolMembership والأدوار عبر أدوار العضوية.
    - PLATFORM_ADMIN يمثل بـ is_superuser (صلاحية منصة) — لا عضوية مدرسة وهمية.
    """

    username = None  # الجوال هو المعرف
    mobile = models.CharField(
        "رقم الجوال",
        max_length=16,
        unique=True,
        validators=[validate_mobile],
        help_text="بالصيغة الموحدة ‎+9665XXXXXXXX",
        error_messages={"unique": "رقم الجوال مسجل مسبقاً."},
    )

    # الحسابات المنشأة بكلمة مرور مؤقتة تجبر على تغييرها قبل أي استخدام تشغيلي
    must_change_password = models.BooleanField(default=False)

    USERNAME_FIELD = "mobile"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        verbose_name = "مستخدم"
        verbose_name_plural = "المستخدمون"

    def __str__(self) -> str:
        return f"{self.get_full_name() or self.mobile}"

    @property
    def is_platform_admin(self) -> bool:
        """صلاحية إدارة المنصة (SaaS) — Platform-Level وليست عضوية مدرسية."""
        return self.is_superuser

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.mobile
