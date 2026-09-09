from django.contrib import admin

from student_leaves.models import StudentGateRelease, StudentLeavePermission


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


@admin.register(StudentGateRelease)
class StudentGateReleaseAdmin(admin.ModelAdmin):
    list_display = [
        "leave_permission",
        "released_at",
        "released_by_membership",
        "school",
    ]
    list_filter = ["school", "released_at"]
    search_fields = [
        "leave_permission__student__full_name",
        "leave_permission__student__student_number",
    ]
    readonly_fields = ["created_at", "updated_at", "released_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
