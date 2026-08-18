from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

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
