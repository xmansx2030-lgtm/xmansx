from django.contrib import admin

from audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """سجل التدقيق للقراءة فقط — append-only حتى داخل Admin."""

    list_display = ["action", "actor", "school", "ip_address", "created_at"]
    list_filter = ["action"]
    search_fields = ["actor__mobile", "school__name", "action"]
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
