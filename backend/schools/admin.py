from django.contrib import admin

from schools.models import School, SchoolSettings


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "school_type", "status", "created_at"]
    list_filter = ["school_type", "status"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ["name"]}
    readonly_fields = ["created_at", "updated_at"]


@admin.register(SchoolSettings)
class SchoolSettingsAdmin(admin.ModelAdmin):
    list_display = ["school", "education_stage", "city", "timezone"]
    list_filter = ["education_stage"]
    search_fields = ["school__name", "ministry_school_number"]
    readonly_fields = ["created_at", "updated_at"]
