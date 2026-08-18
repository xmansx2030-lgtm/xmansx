"""قراءات العضويات — الاستعلامات المركزية (منع N+1 والتكرار)."""

from memberships.models import MembershipStatus, SchoolMembership


def active_memberships_for_user(user):
    """عضويات المستخدم الفعالة مع المدرسة والأدوار — استعلامان فقط مهما تعددت المدارس."""
    return (
        SchoolMembership.objects.filter(user=user, status=MembershipStatus.ACTIVE)
        .select_related("school")
        .prefetch_related("roles")
        .order_by("school__name")
    )


def get_membership(user, school_id) -> SchoolMembership | None:
    """عضوية المستخدم في مدرسة (أي حالة) — للتحقق التفصيلي عند التبديل."""
    return (
        SchoolMembership.objects.filter(user=user, school_id=school_id)
        .select_related("school")
        .prefetch_related("roles")
        .first()
    )
