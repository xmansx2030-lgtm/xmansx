from django.contrib import admin

from student_leaves.models import StudentLeavePermission


@admin.register(StudentLeavePermission)
class StudentLeavePermissionAdmin(admin.ModelAdmin):
    list_display = [
        "student",
        "leave_date",
        "leave_time",
        "status",
        "recorded_by_membership",
        "school",
    ]
    list_filter = ["school", "status", "leave_date"]
    search_fields = ["student__full_name", "student__student_number"]
    autocomplete_fields = ["student"]
    readonly_fields = ["created_at", "updated_at"]
