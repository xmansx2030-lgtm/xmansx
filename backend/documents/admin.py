from django.contrib import admin

from documents.models import GeneratedDocument


@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(admin.ModelAdmin):
    list_display = ["student", "document_type", "status", "generated_at", "school"]
    list_filter = ["school", "document_type", "status"]
    search_fields = ["student__full_name"]
    autocomplete_fields = ["student"]
    # اللقطة والملف والبصمة سجل تاريخي — لا تحرر من الإدارة
    readonly_fields = [
        "snapshot_data", "file", "checksum", "size_bytes", "created_at", "updated_at",
    ]
