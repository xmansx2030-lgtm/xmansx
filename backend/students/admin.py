from django import forms
from django.contrib import admin
from django.db import transaction

from common.errors import ApiError
from parents.contact_security import (
    contact_changed,
    contact_write_context,
    require_contact_verification,
)
from students.models import (
    Grade,
    Section,
    Student,
    StudentEnrollment,
    StudentImportJob,
)


class StudentAdminForm(forms.ModelForm):
    contact_change_reason = forms.CharField(
        label="سبب تغيير التواصل",
        max_length=300,
        required=False,
    )
    contact_identity_verified = forms.BooleanField(
        label="تحققت المدرسة من صفة صاحب الطلب",
        required=False,
    )
    contact_verification_note = forms.CharField(
        label="توثيق التحقق من الصفة",
        max_length=600,
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    class Meta:
        model = Student
        fields = (
            "school",
            "national_id_encrypted",
            "national_id_lookup_hash",
            "national_id_masked",
            "student_number",
            "full_name",
            "guardian_name",
            "guardian_mobile",
            "merged_into",
            "status",
            "status_changed_at",
            "status_changed_by",
            "exit_date",
            "exit_reason",
        )

    def clean(self):
        data = super().clean()
        if self.instance.pk:
            previous = Student.objects.get(pk=self.instance.pk)
            try:
                require_contact_verification(previous, data)
            except ApiError as error:
                raise forms.ValidationError(str(error.detail)) from error
        return data


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
    form = StudentAdminForm
    list_filter = ["status", "school"]
    search_fields = ["full_name", "student_number"]  # لا بحث بالهوية من Admin
    readonly_fields = [
        "national_id_encrypted",
        "national_id_lookup_hash",
        "national_id_masked",
        "created_at",
        "updated_at",
        "guardian_contact_revision",
    ]

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        from parents.access import lock_parent_school

        lock_parent_school(obj.school_id)
        data = form.cleaned_data if form is not None else {}
        previous = (
            Student.objects.select_for_update().filter(pk=obj.pk).first() if change else None
        )
        effective_change = previous and contact_changed(
            previous,
            {
                "guardian_mobile": obj.guardian_mobile,
                "guardian_name": obj.guardian_name,
            },
        )
        if effective_change:
            require_contact_verification(
                previous,
                {
                    **data,
                    "guardian_mobile": obj.guardian_mobile,
                    "guardian_name": obj.guardian_name,
                },
            )
            from memberships.models import MembershipStatus, SchoolMembership
            from parents.models import GuardianStudentRelation

            protected = GuardianStudentRelation.objects.filter(
                student=previous,
                contact_bound=True,
                status__in=["ACTIVE", "SUSPENDED_CONTACT_REVIEW", "PENDING"],
            ).exists()
            if (
                protected
                and not request.user.is_superuser
                and not SchoolMembership.objects.filter(
                    user=request.user,
                    school=obj.school,
                    status=MembershipStatus.ACTIVE,
                    roles__role__in=["SCHOOL_MANAGER", "VICE_PRINCIPAL"],
                ).exists()
            ):
                raise forms.ValidationError("تعديل التواصل يتطلب مدير المدرسة أو الوكيل المخول.")
        with contact_write_context(
            source="DJANGO_ADMIN",
            actor=request.user,
            reason=data.get("contact_change_reason", ""),
            previous_mobile=previous.guardian_mobile if previous else None,
            current_mobile=obj.guardian_mobile,
        ):
            super().save_model(request, obj, form, change)
        if effective_change:
            obj.refresh_from_db(fields=["guardian_contact_revision"])
            from parents.models import GuardianContactReview

            GuardianContactReview.objects.filter(
                student=obj,
                current_revision=obj.guardian_contact_revision,
            ).update(verification_note=data.get("contact_verification_note", ""))


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
