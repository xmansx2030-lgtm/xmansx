from django.contrib import admin

from memberships.models import (
    SchoolMembership,
    SchoolMembershipCapability,
    SchoolMembershipRole,
)


class SchoolMembershipRoleInline(admin.TabularInline):
    model = SchoolMembershipRole
    extra = 1


class SchoolMembershipCapabilityInline(admin.TabularInline):
    model = SchoolMembershipCapability
    extra = 0


@admin.register(SchoolMembership)
class SchoolMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "school", "status", "joined_at"]
    list_filter = ["status", "school"]
    search_fields = ["user__mobile", "user__first_name", "user__last_name", "school__name"]
    autocomplete_fields = ["user", "school"]
    readonly_fields = ["joined_at", "created_at", "updated_at"]
    inlines = [SchoolMembershipRoleInline, SchoolMembershipCapabilityInline]


@admin.register(SchoolMembershipRole)
class SchoolMembershipRoleAdmin(admin.ModelAdmin):
    list_display = ["membership", "role", "created_at"]
    list_filter = ["role"]
    search_fields = ["membership__user__mobile", "membership__school__name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(SchoolMembershipCapability)
class SchoolMembershipCapabilityAdmin(admin.ModelAdmin):
    list_display = ["membership", "capability", "granted_by", "created_at"]
    list_filter = ["capability"]
    search_fields = ["membership__user__mobile", "membership__school__name"]
    readonly_fields = ["created_at", "updated_at"]
