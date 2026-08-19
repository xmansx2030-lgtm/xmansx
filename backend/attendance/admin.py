from django.contrib import admin

from attendance.models import AttendanceChange, AttendanceMark, AttendanceSession


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = [
        "section", "attendance_date", "period_sequence", "status",
        "submitted_by_membership", "school",
    ]
    list_filter = ["status", "school", "attendance_date"]
    readonly_fields = [f.name for f in AttendanceSession._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(AttendanceMark)
class AttendanceMarkAdmin(admin.ModelAdmin):
    list_display = ["session", "student", "status", "late_minutes", "school"]
    list_filter = ["status", "school"]
    readonly_fields = [f.name for f in AttendanceMark._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(AttendanceChange)
class AttendanceChangeAdmin(admin.ModelAdmin):
    """سجل تاريخي — قراءة فقط حتى في Admin."""

    list_display = [
        "session", "student", "previous_status", "new_status", "changed_at", "school",
    ]
    list_filter = ["school"]
    readonly_fields = [f.name for f in AttendanceChange._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
