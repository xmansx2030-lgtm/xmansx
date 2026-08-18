from django.contrib import admin

from students.models import (
    Grade,
    Section,
    Student,
    StudentEnrollment,
    StudentImportJob,
)


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "school", "sequence", "is_active"]
    list_filter = ["is_active", "school"]
    search_fields = ["name", "code", "school__name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ["__str__", "code", "school", "is_active"]
    list_filter = ["is_active", "school"]
    search_fields = ["name", "code", "grade__name", "school__name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    """لا plaintext للهوية في أي عرض — masked فقط، والحقول المشفرة للقراءة."""

    list_display = ["full_name", "national_id_masked", "school", "status"]
    list_filter = ["status", "school"]
    search_fields = ["full_name", "student_number"]  # لا بحث بالهوية من Admin
    readonly_fields = [
        "national_id_encrypted", "national_id_lookup_hash", "national_id_masked",
        "created_at", "updated_at",
    ]


@admin.register(StudentEnrollment)
class StudentEnrollmentAdmin(admin.ModelAdmin):
    list_display = [
        "student", "academic_year", "grade", "section", "status", "enrolled_at", "ended_at",
    ]
    list_filter = ["status", "school", "academic_year"]
    search_fields = ["student__full_name"]
    readonly_fields = ["created_at", "updated_at"]
    autocomplete_fields = ["student", "grade", "section"]


@admin.register(StudentImportJob)
class StudentImportJobAdmin(admin.ModelAdmin):
    list_display = ["id", "school", "status", "total_rows", "invalid_rows", "created_at"]
    list_filter = ["status", "school"]
    readonly_fields = [f.name for f in StudentImportJob._meta.fields]

    def has_add_permission(self, request):
        return False
