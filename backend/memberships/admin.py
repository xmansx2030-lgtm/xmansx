from django.contrib import admin

from memberships.models import SchoolMembership, SchoolMembershipRole


class SchoolMembershipRoleInline(admin.TabularInline):
    model = SchoolMembershipRole
    extra = 1


@admin.register(SchoolMembership)
class SchoolMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "school", "status", "joined_at"]
    list_filter = ["status", "school"]
    search_fields = ["user__mobile", "user__first_name", "user__last_name", "school__name"]
    autocomplete_fields = ["user", "school"]
    readonly_fields = ["joined_at", "created_at", "updated_at"]
    inlines = [SchoolMembershipRoleInline]


@admin.register(SchoolMembershipRole)
class SchoolMembershipRoleAdmin(admin.ModelAdmin):
    list_display = ["membership", "role", "created_at"]
    list_filter = ["role"]
    search_fields = ["membership__user__mobile", "membership__school__name"]
    readonly_fields = ["created_at", "updated_at"]
