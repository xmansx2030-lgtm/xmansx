from django.contrib import admin

from student_actions.models import StudentAction


@admin.register(StudentAction)
class StudentActionAdmin(admin.ModelAdmin):
    list_display = ["student", "action_type", "status", "performed_at", "school"]
    list_filter = ["school", "action_type", "status"]
    search_fields = ["student__full_name"]
    autocomplete_fields = ["student"]
    readonly_fields = ["created_at", "updated_at"]
