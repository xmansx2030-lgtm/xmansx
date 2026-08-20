"""قراءات الإحالات — النطاق حسب الدور هو خط الدفاع الأول لخصوصية المعلم.

- المدير/الوكيل: كل إحالات المدرسة.
- المرشد: المعينة له + غير المعينة (ليستلمها) — لا حالات زميله.
- المعلم: ما أنشأه أو ساهم فيه فقط (بند 42/79/110).
"""

from django.db.models import Count, Q

from memberships.models import SchoolRole
from referrals.models import (
    OPEN_STATUSES,
    ReferralStatus,
    StudentReferral,
)

MANAGE_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)

_LIST_RELATIONS = (
    "student",
    "created_by_membership__user",
    "created_by_membership__staff_profile",
    "assigned_counselor_membership__user",
    "assigned_counselor_membership__staff_profile",
)


def base_queryset(school):
    return (
        StudentReferral.objects.filter(school=school)
        .select_related(*_LIST_RELATIONS)
        .prefetch_related("student__enrollments__grade", "student__enrollments__section")
    )


def _participation_filter(membership) -> Q:
    """ما أنشأه المستخدم أو ساهم فيه — يُضاف دائمًا لا يُستبدل به.

    الجمع مهم: مرشد يحمل دور معلم أيضًا يبقى يرى إحالته التي أنشأها حتى بعد
    تعيينها لزميل (وإلا ظهرت في «إحالاتي» وفتحها يعطي 404).
    """
    return Q(created_by_membership=membership) | Q(
        contributions__created_by_membership=membership
    )


def visible_referrals(*, school, membership, roles):
    """الاستعلام المسموح لهذا المستخدم — يُطبق قبل أي فلتر من العميل."""
    role_set = set(roles or [])
    queryset = base_queryset(school)
    if role_set & set(MANAGE_ROLES):
        return queryset

    scope = Q(pk__in=[])  # لا شيء افتراضيًا — الأدوار تضيف إليه
    if SchoolRole.COUNSELOR in role_set:
        scope |= Q(assigned_counselor_membership=membership) | Q(
            assigned_counselor_membership__isnull=True
        )
    if SchoolRole.TEACHER in role_set:
        scope |= _participation_filter(membership)
    if scope == Q(pk__in=[]):
        return queryset.none()
    return queryset.filter(scope).distinct()


def teacher_referrals(*, school, membership):
    """«إحالاتي»: ما أنشأه المستخدم أو أضاف إليه ملاحظة — لأي دور."""
    return base_queryset(school).filter(_participation_filter(membership)).distinct()


def _participated(referral, membership) -> bool:
    if referral.created_by_membership_id == membership.id:
        return True
    return referral.contributions.filter(created_by_membership=membership).exists()


def can_view_referral(*, referral, membership, roles) -> bool:
    role_set = set(roles or [])
    if role_set & set(MANAGE_ROLES):
        return True
    # الأدوار تتجمع: المشاركة تمنح الرؤية مهما كان الدور الآخر
    if _participated(referral, membership):
        return True
    if SchoolRole.COUNSELOR in role_set:
        return referral.assigned_counselor_membership_id in (None, membership.id)
    return False


def apply_filters(queryset, params):
    """فلاتر العميل فوق النطاق المسموح — لا توسّعه أبدًا."""
    status = params.get("status")
    if status in ReferralStatus.values:
        queryset = queryset.filter(status=status)
    elif status == "OPEN":
        queryset = queryset.filter(status__in=OPEN_STATUSES)
    elif status:
        # تجاهل قيمة غير معروفة كان يعيد «الكل» بينما العميل يظنه فلترة
        from common.errors import ApiError

        raise ApiError(
            "VALIDATION_ERROR", "قيمة الحالة غير صحيحة.", details={"field": "status"}
        )
    if params.get("category"):
        queryset = queryset.filter(category=params["category"])
    if params.get("reason_code"):
        queryset = queryset.filter(reason_code=params["reason_code"])
    if params.get("source_type"):
        queryset = queryset.filter(source_type=params["source_type"])
    if params.get("student"):
        queryset = queryset.filter(student_id=_int_or_zero(params["student"]))
    if params.get("counselor"):
        value = params["counselor"]
        if value == "UNASSIGNED":
            queryset = queryset.filter(assigned_counselor_membership__isnull=True)
        else:
            queryset = queryset.filter(
                assigned_counselor_membership_id=_int_or_zero(value)
            )
    if params.get("grade"):
        queryset = queryset.filter(
            student__enrollments__status="ACTIVE",
            student__enrollments__grade_id=_int_or_zero(params["grade"]),
        ).distinct()
    if params.get("section"):
        queryset = queryset.filter(
            student__enrollments__status="ACTIVE",
            student__enrollments__section_id=_int_or_zero(params["section"]),
        ).distinct()
    return queryset


def referral_kpis(*, school, membership, roles) -> dict:
    """مؤشرات صندوق الوارد — محسوبة على النطاق المسموح لا على المدرسة كلها."""
    scoped = visible_referrals(school=school, membership=membership, roles=roles)
    counts = scoped.aggregate(
        new_count=Count("id", filter=Q(status=ReferralStatus.NEW)),
        acknowledged_count=Count("id", filter=Q(status=ReferralStatus.ACKNOWLEDGED)),
        unassigned_count=Count(
            "id",
            filter=Q(assigned_counselor_membership__isnull=True)
            & Q(status__in=OPEN_STATUSES),
        ),
    )
    return {
        "new_count": counts["new_count"] or 0,
        "acknowledged_count": counts["acknowledged_count"] or 0,
        "unassigned_count": counts["unassigned_count"] or 0,
    }


def _int_or_zero(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
