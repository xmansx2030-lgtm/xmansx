"""قراءات الإحالات — النطاق حسب الدور ومسؤولية الوكيل هو خط الدفاع الأول.

- المدير: كل إحالات المدرسة.
- الوكيل: الإحالات الموجهة إليه حسب نطاقه فقط، إضافة إلى مشاركاته.
- المرشد: المحولة إليه فقط — لا يرى ما يزال لدى الوكيل ولا حالات زميله.
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
    "school",
    "student",
    "created_by_membership__user",
    "created_by_membership__staff_profile",
    "assigned_vice_membership__user",
    "assigned_vice_membership__staff_profile",
    "assigned_counselor_membership__user",
    "assigned_counselor_membership__staff_profile",
)


def base_queryset(school):
    return (
        StudentReferral.objects.filter(school=school)
        .select_related(*_LIST_RELATIONS)
        .prefetch_related(
            "student__enrollments__grade",
            "student__enrollments__section",
            "cases",
        )
    )


def _participation_filter(membership) -> Q:
    """ما أنشأه المستخدم أو ساهم فيه — يُضاف دائمًا لا يُستبدل به.

    الجمع مهم: مرشد يحمل دور معلم أيضًا يبقى يرى إحالته التي أنشأها حتى بعد
    تعيينها لزميل (وإلا ظهرت في «إحالاتي» وفتحها يعطي 404).
    """
    return Q(created_by_membership=membership) | Q(contributions__created_by_membership=membership)


def visible_referrals(*, school, membership, roles):
    """الاستعلام المسموح لهذا المستخدم — يُطبق قبل أي فلتر من العميل."""
    role_set = set(roles or [])
    queryset = base_queryset(school)
    if SchoolRole.SCHOOL_MANAGER in role_set:
        return queryset

    scope = Q(pk__in=[])  # لا شيء افتراضيًا — الأدوار تضيف إليه
    if SchoolRole.VICE_PRINCIPAL in role_set:
        scope |= Q(assigned_vice_membership=membership) | _participation_filter(membership)
    if SchoolRole.COUNSELOR in role_set:
        scope |= Q(assigned_counselor_membership=membership)
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
    if SchoolRole.SCHOOL_MANAGER in role_set:
        return True
    # الأدوار تتجمع: المشاركة تمنح الرؤية مهما كان الدور الآخر
    if _participated(referral, membership):
        return True
    if SchoolRole.VICE_PRINCIPAL in role_set:
        return referral.assigned_vice_membership_id == membership.id
    if SchoolRole.COUNSELOR in role_set:
        return referral.assigned_counselor_membership_id == membership.id
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

        raise ApiError("VALIDATION_ERROR", "قيمة الحالة غير صحيحة.", details={"field": "status"})
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
            queryset = queryset.filter(assigned_counselor_membership_id=_int_or_zero(value))
    if params.get("vice_principal"):
        value = params["vice_principal"]
        if value == "UNASSIGNED":
            queryset = queryset.filter(assigned_vice_membership__isnull=True)
        else:
            queryset = queryset.filter(assigned_vice_membership_id=_int_or_zero(value))
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
        pending_vice_count=Count("id", filter=Q(status=ReferralStatus.PENDING_VICE)),
        under_vice_review_count=Count(
            "id", filter=Q(status=ReferralStatus.UNDER_VICE_REVIEW)
        ),
        referred_count=Count("id", filter=Q(status=ReferralStatus.REFERRED)),
        acknowledged_count=Count("id", filter=Q(status=ReferralStatus.ACKNOWLEDGED)),
        unassigned_vice_count=Count(
            "id",
            filter=Q(assigned_vice_membership__isnull=True)
            & Q(status=ReferralStatus.PENDING_VICE),
        ),
    )
    return {
        "pending_vice_count": counts["pending_vice_count"] or 0,
        "under_vice_review_count": counts["under_vice_review_count"] or 0,
        "referred_count": counts["referred_count"] or 0,
        "acknowledged_count": counts["acknowledged_count"] or 0,
        "unassigned_vice_count": counts["unassigned_vice_count"] or 0,
    }


def _int_or_zero(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
