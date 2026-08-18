from django.contrib import admin

from staff.models import StaffImportJob, StaffProfile


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ["display_name", "school", "employee_number", "source", "is_active"]
    list_filter = ["source", "is_active", "school"]
    search_fields = ["display_name", "employee_number"]
    readonly_fields = ["created_at", "updated_at"]
    autocomplete_fields = ["membership"]


@admin.register(StaffImportJob)
class StaffImportJobAdmin(admin.ModelAdmin):
    list_display = ["id", "school", "status", "total_rows", "invalid_rows", "created_at"]
    list_filter = ["status", "school"]
    readonly_fields = [f.name for f in StaffImportJob._meta.fields]

    def has_add_permission(self, request):
        return False
