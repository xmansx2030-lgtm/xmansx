"""الأعذار في Admin — قراءة فقط: كل الإجراءات تمر عبر الخدمات (Audit + Coverage)."""

from django.contrib import admin

from excuses.models import (
    AbsenceExcuse,
    AbsenceExcuseAttachment,
    AbsenceExcuseCoverage,
    AbsenceExcuseTarget,
)


class _ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AbsenceExcuse)
class AbsenceExcuseAdmin(_ReadOnlyAdmin):
    list_display = ["id", "school", "student", "status", "reason_type", "recorded_at"]
    list_filter = ["status", "reason_type"]
    readonly_fields = [f.name for f in AbsenceExcuse._meta.fields]


@admin.register(AbsenceExcuseTarget)
class AbsenceExcuseTargetAdmin(_ReadOnlyAdmin):
    list_display = ["id", "excuse", "attendance_date", "period_sequence"]
    readonly_fields = [f.name for f in AbsenceExcuseTarget._meta.fields]


@admin.register(AbsenceExcuseCoverage)
class AbsenceExcuseCoverageAdmin(_ReadOnlyAdmin):
    list_display = [
        "id", "excuse", "student", "attendance_date",
        "period_sequence_snapshot", "status",
    ]
    list_filter = ["status"]
    readonly_fields = [f.name for f in AbsenceExcuseCoverage._meta.fields]


@admin.register(AbsenceExcuseAttachment)
class AbsenceExcuseAttachmentAdmin(_ReadOnlyAdmin):
    list_display = ["id", "excuse", "original_filename", "mime_type", "size_bytes"]
    readonly_fields = [f.name for f in AbsenceExcuseAttachment._meta.fields]
