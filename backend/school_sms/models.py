from django.conf import settings
from django.db import models

from common.models import TimestampedModel


class SmsProvider(models.TextChoices):
    DREAMS = "DREAMS", "دريمز"
    MSEGAT = "MSEGAT", "مسجات"


class SchoolSmsIntegration(TimestampedModel):
    school = models.OneToOneField(
        "schools.School", on_delete=models.CASCADE, related_name="sms_integration"
    )
    provider = models.CharField(max_length=12, choices=SmsProvider.choices)
    username = models.CharField(max_length=150)
    secret_encrypted = models.TextField()
    sender_name = models.CharField(max_length=30)
    is_active = models.BooleanField(default=False)

    class Meta:
        verbose_name = "ربط الرسائل النصية للمدرسة"
        verbose_name_plural = "روابط الرسائل النصية للمدارس"


class AbsenceSmsStatus(models.TextChoices):
    QUEUED = "QUEUED", "بانتظار الإرسال"
    SENDING = "SENDING", "جارٍ الإرسال"
    ACCEPTED = "ACCEPTED", "قبله المزود"
    FAILED = "FAILED", "تعذر الإرسال"
    UNKNOWN = "UNKNOWN", "تحتاج مراجعة حالة الإرسال"


class AbsenceSmsNotice(TimestampedModel):
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="absence_sms_notices"
    )
    student = models.ForeignKey(
        "students.Student", on_delete=models.PROTECT, related_name="absence_sms_notices"
    )
    attendance_date = models.DateField()
    absence_status = models.CharField(max_length=14)
    provider = models.CharField(max_length=12, choices=SmsProvider.choices)
    recipient_masked = models.CharField(max_length=20)
    recipient_hash = models.CharField(max_length=64)
    status = models.CharField(
        max_length=12, choices=AbsenceSmsStatus.choices, default=AbsenceSmsStatus.QUEUED
    )
    provider_reference = models.CharField(max_length=100, blank=True, default="")
    failure_code = models.CharField(max_length=40, blank=True, default="")
    attempts = models.PositiveSmallIntegerField(default=1)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "إشعار غياب نصي"
        verbose_name_plural = "إشعارات الغياب النصية"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "student", "attendance_date"],
                name="uniq_absence_sms_student_day",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "attendance_date"], name="sms_notice_school_date_idx"),
        ]
