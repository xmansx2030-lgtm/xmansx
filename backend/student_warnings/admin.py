from django.contrib import admin

from student_warnings.models import StudentWarning, WarningRule


@admin.register(WarningRule)
class WarningRuleAdmin(admin.ModelAdmin):
    list_display = ["school", "rule_type", "level", "threshold", "is_enabled"]
    list_filter = ["rule_type", "level", "is_enabled", "school"]


@admin.register(StudentWarning)
class StudentWarningAdmin(admin.ModelAdmin):
    """سجل تاريخي — قراءة فقط: الخطأ يعالج بالإلغاء عبر الواجهة لا بالتحرير."""

    list_display = [
        "student", "warning_type", "level", "status",
        "metric_value_at_issue", "threshold_at_issue", "issued_at", "school",
    ]
    list_filter = ["warning_type", "level", "status", "school"]
    readonly_fields = [f.name for f in StudentWarning._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
