"""الإحالات في Admin — قراءة فقط: كل انتقال يمر بالخدمات (خط زمني + Audit)."""

from django.contrib import admin

from referrals.models import (
    StudentReferral,
    StudentReferralContribution,
    StudentReferralEvent,
)


class _ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StudentReferral)
class StudentReferralAdmin(_ReadOnlyAdmin):
    list_display = ["id", "school", "student", "category", "reason_code", "status"]
    list_filter = ["status", "category", "source_type"]
    readonly_fields = [f.name for f in StudentReferral._meta.fields]


@admin.register(StudentReferralContribution)
class StudentReferralContributionAdmin(_ReadOnlyAdmin):
    list_display = ["id", "referral", "observation_type", "created_at"]
    readonly_fields = [f.name for f in StudentReferralContribution._meta.fields]


@admin.register(StudentReferralEvent)
class StudentReferralEventAdmin(_ReadOnlyAdmin):
    list_display = ["id", "referral", "event_type", "created_at"]
    list_filter = ["event_type"]
    readonly_fields = [f.name for f in StudentReferralEvent._meta.fields]
