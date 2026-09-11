from django.contrib import admin

from attendance.models import (
    AttendanceChange,
    AttendanceDayContext,
    AttendanceMark,
    AttendanceSession,
    DailyAttendanceSummary,
)


@admin.register(AttendanceDayContext)
class AttendanceDayContextAdmin(admin.ModelAdmin):
    """‏snapshot تاريخي — قراءة فقط: تعديله يزور تحليلات الماضي."""

    list_display = ["school", "attendance_date", "timezone_snapshot"]
    list_filter = ["school"]
    readonly_fields = [f.name for f in AttendanceDayContext._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DailyAttendanceSummary)
class DailyAttendanceSummaryAdmin(admin.ModelAdmin):
    """مشتق — يعاد بناؤه بالأمر rebuild_daily_attendance_summaries لا بالتحرير."""

    list_display = [
        "student", "attendance_date", "absence_status", "completeness_status",
        "absent_periods", "school",
    ]
    list_filter = ["absence_status", "completeness_status", "school", "attendance_date"]
    readonly_fields = [f.name for f in DailyAttendanceSummary._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


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
    list_display = ["session", "student", "status", "school"]
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
