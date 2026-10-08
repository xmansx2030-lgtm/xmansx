from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import PermissionDenied
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters

from accounts.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """إدارة المستخدم بالجوال — hash كلمة المرور غير قابل للتعديل المباشر
    (نموذج تغيير كلمة المرور القياسي فقط)."""

    ordering = ["mobile"]
    list_display = ["mobile", "first_name", "last_name", "is_active", "is_staff", "last_login"]
    list_filter = ["is_active", "is_staff", "is_superuser"]
    search_fields = ["mobile", "first_name", "last_name", "email"]
    readonly_fields = ["last_login", "date_joined", "created_at", "updated_at"]

    fieldsets = (
        (None, {"fields": ("mobile", "password")}),
        ("المعلومات الشخصية", {"fields": ("first_name", "last_name", "email")}),
        ("الصلاحيات", {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
        ("تواريخ", {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("mobile", "password1", "password2")}),
    )

    def _has_guardian_relations(self, obj):
        from common.tenant_rls import tenant_context
        from parents.models import GuardianStudentRelation

        if obj is None:
            return False
        with tenant_context(user_id=obj.pk):
            return GuardianStudentRelation.objects.filter(user=obj).exists()

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if self._has_guardian_relations(obj):
            fields.append("mobile")
        return fields

    @method_decorator(sensitive_post_parameters())
    def user_change_password(self, request, id, form_url=""):
        account = self.get_object(request, unquote(id))
        if not self.has_change_permission(request, account):
            raise PermissionDenied
        if self._has_guardian_relations(account):
            raise PermissionDenied(
                "استعادة حساب ولي الأمر تتطلب تحققاً عالمياً مستقلاً من ملكية الحساب."
            )
        return super().user_change_password(request, id, form_url)

    def save_model(self, request, obj, form, change):
        if change:
            stored_password = (
                User.objects.filter(pk=obj.pk).values_list("password", flat=True).first()
            )
            if stored_password != obj.password and self._has_guardian_relations(obj):
                raise PermissionDenied(
                    "استعادة حساب ولي الأمر تتطلب تحققاً عالمياً مستقلاً من ملكية الحساب."
                )
        super().save_model(request, obj, form, change)
