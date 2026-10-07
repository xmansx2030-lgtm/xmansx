"""Official source snapshots and explicit school calendar scope; no invented dates."""

from django.db import models

from common.models import TimestampedModel


class MinistryCalendarSnapshot(TimestampedModel):
    fingerprint = models.CharField(max_length=64, unique=True)
    documents = models.JSONField(default=list)
    calendars = models.JSONField(default=list)

    class Meta:
        ordering = ["-created_at"]


class MinistryCalendarSync(TimestampedModel):
    # One source for the national public-school calendar, never regional exceptions.
    key = models.CharField(max_length=30, primary_key=True, default="NATIONAL")
    snapshot = models.ForeignKey(
        MinistryCalendarSnapshot, null=True, on_delete=models.PROTECT, related_name="+"
    )
    checked_at = models.DateTimeField(null=True)
    succeeded_at = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=80, blank=True, default="")


class CalendarProfile(models.TextChoices):
    UNCONFIRMED = "UNCONFIRMED", "لم يُحدد نطاق التقويم"
    NATIONAL = "NATIONAL", "التقويم الوطني للمدارس الحكومية"
    EXCEPTION = "EXCEPTION", "تقويم خاص أو محلي معتمد"


class SchoolCalendarPolicy(TimestampedModel):
    school = models.OneToOneField("schools.School", on_delete=models.CASCADE)
    profile = models.CharField(
        max_length=20, choices=CalendarProfile.choices, default=CalendarProfile.UNCONFIRMED
    )
    scope_note = models.CharField(max_length=500, blank=True, default="")
    checked_at = models.DateTimeField(null=True)
    outcome = models.CharField(max_length=80, blank=True, default="")

    class Meta:
        verbose_name = "نطاق تقويم المدرسة"
        verbose_name_plural = "نطاقات تقويم المدارس"
