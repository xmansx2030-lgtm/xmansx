from django.db import models

from platform_team.models import (
    PlatformStaffMembership,
    PlatformStaffRole,
    PlatformStaffStatus,
)


class PlatformCapability(models.TextChoices):
    DASHBOARD_VIEW = "DASHBOARD_VIEW", "عرض لوحة المؤشرات"
    SCHOOLS_VIEW = "SCHOOLS_VIEW", "عرض المدارس"
    SCHOOLS_MANAGE = "SCHOOLS_MANAGE", "إدارة المدارس"
    SCHOOL_ACCOUNTS_MANAGE = "SCHOOL_ACCOUNTS_MANAGE", "إدارة حسابات المدارس"
    SUBSCRIPTIONS_MANAGE = "SUBSCRIPTIONS_MANAGE", "إدارة الاشتراكات"
    PLANS_VIEW = "PLANS_VIEW", "عرض الباقات"
    PLANS_MANAGE = "PLANS_MANAGE", "إدارة الباقات"
    TEAM_VIEW = "TEAM_VIEW", "عرض فريق المنصة"
    TEAM_MANAGE = "TEAM_MANAGE", "إدارة فريق المنصة"


ALL_CAPABILITIES = frozenset(PlatformCapability.values)

ROLE_CAPABILITIES = {
    PlatformStaffRole.OPERATIONS_MANAGER: frozenset(
        {
            PlatformCapability.DASHBOARD_VIEW,
            PlatformCapability.SCHOOLS_VIEW,
            PlatformCapability.SCHOOLS_MANAGE,
            PlatformCapability.SCHOOL_ACCOUNTS_MANAGE,
            PlatformCapability.SUBSCRIPTIONS_MANAGE,
            PlatformCapability.PLANS_VIEW,
            PlatformCapability.TEAM_VIEW,
            PlatformCapability.TEAM_MANAGE,
        }
    ),
    PlatformStaffRole.SUPPORT: frozenset(
        {
            PlatformCapability.DASHBOARD_VIEW,
            PlatformCapability.SCHOOLS_VIEW,
            PlatformCapability.SCHOOL_ACCOUNTS_MANAGE,
            PlatformCapability.TEAM_VIEW,
        }
    ),
    PlatformStaffRole.BILLING: frozenset(
        {
            PlatformCapability.DASHBOARD_VIEW,
            PlatformCapability.SCHOOLS_VIEW,
            PlatformCapability.SUBSCRIPTIONS_MANAGE,
            PlatformCapability.PLANS_VIEW,
            PlatformCapability.PLANS_MANAGE,
        }
    ),
    PlatformStaffRole.AUDITOR: frozenset(
        {
            PlatformCapability.DASHBOARD_VIEW,
            PlatformCapability.SCHOOLS_VIEW,
            PlatformCapability.PLANS_VIEW,
            PlatformCapability.TEAM_VIEW,
        }
    ),
}


def get_platform_access(user) -> dict:
    if not user or not getattr(user, "is_authenticated", False):
        return {
            "is_platform_user": False,
            "is_owner": False,
            "role": None,
            "role_label": "",
            "capabilities": [],
        }
    if user.is_superuser:
        return {
            "is_platform_user": True,
            "is_owner": True,
            "role": "OWNER",
            "role_label": "مالك المنصة",
            "capabilities": sorted(ALL_CAPABILITIES),
        }
    try:
        membership = user.platform_staff_membership
    except PlatformStaffMembership.DoesNotExist:
        membership = None
    if membership is None or membership.status != PlatformStaffStatus.ACTIVE:
        return {
            "is_platform_user": False,
            "is_owner": False,
            "role": None,
            "role_label": "",
            "capabilities": [],
        }
    return {
        "is_platform_user": True,
        "is_owner": False,
        "role": membership.role,
        "role_label": membership.get_role_display(),
        "capabilities": sorted(ROLE_CAPABILITIES.get(membership.role, frozenset())),
    }


def has_platform_capability(user, capability: str | None) -> bool:
    access = get_platform_access(user)
    return access["is_platform_user"] and (
        capability is None or capability in access["capabilities"]
    )
