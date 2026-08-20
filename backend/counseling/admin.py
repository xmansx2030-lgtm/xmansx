from django.contrib import admin

from counseling.models import (
    CounselorCase,
    CounselorFollowUpPlan,
    CounselorSession,
    TeacherFollowUpRequest,
)


@admin.register(CounselorCase)
class CounselorCaseAdmin(admin.ModelAdmin):
    list_display = ["student", "status", "priority", "opened_at", "school"]
    list_filter = ["school", "status", "priority"]
    autocomplete_fields = ["student"]
    # اللقطة سجل تاريخي — لا تحرر من الإدارة
    readonly_fields = ["snapshot_data", "created_at", "updated_at"]


@admin.register(CounselorSession)
class CounselorSessionAdmin(admin.ModelAdmin):
    list_display = ["case", "session_type", "occurred_at", "status"]
    list_filter = ["school", "session_type", "status"]


@admin.register(CounselorFollowUpPlan)
class CounselorFollowUpPlanAdmin(admin.ModelAdmin):
    list_display = ["title", "case", "status", "start_date"]
    list_filter = ["school", "status"]


@admin.register(TeacherFollowUpRequest)
class TeacherFollowUpRequestAdmin(admin.ModelAdmin):
    list_display = ["case", "request_type", "status", "due_date"]
    list_filter = ["school", "request_type", "status"]
