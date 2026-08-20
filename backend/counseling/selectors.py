"""قراءات الحالات الإرشادية — النطاق حسب الدور خط الدفاع الأول للخصوصية.

- المدير: كل حالات المدرسة (البند 72).
- الوكيل: يرى الحالات وحالتها ومسارها، ولا يعدّل محتوى الإرشاد (البند 73).
- المرشد: حالاته المسندة إليه — لا حالات زملائه (البند 97).
- المعلم: **لا حالات إطلاقًا**، طلباته فقط (البنود 70-71).
"""

from django.db.models import Count, Q
from django.utils import timezone as dj_timezone

from counseling.models import (
    LIVE_CASE_STATUSES,
    ActivityStatus,
    CaseStatus,
    CounselorCase,
    FollowUpActivity,
    FollowUpRequestStatus,
    SessionStatus,
    TeacherFollowUpRequest,
)
from memberships.models import SchoolRole
from referrals.models import ReferralStatus, StudentReferral

VIEW_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL, SchoolRole.COUNSELOR)
MANAGE_VIEW_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)

_LIST_RELATIONS = (
    "student",
    "primary_referral",
    "assigned_counselor_membership__user",
    "assigned_counselor_membership__staff_profile",
)


def base_queryset(school):
    return (
        CounselorCase.objects.filter(school=school)
        .select_related(*_LIST_RELATIONS)
        .prefetch_related("student__enrollments__grade", "student__enrollments__section")
    )


def visible_cases(*, school, membership, roles):
    """يُطبق قبل أي فلتر من العميل — المعلم لا يرى شيئًا هنا."""
    role_set = set(roles or [])
    queryset = base_queryset(school)
    if role_set & set(MANAGE_VIEW_ROLES):
        return queryset
    if SchoolRole.COUNSELOR in role_set:
        return queryset.filter(assigned_counselor_membership=membership)
    return queryset.none()


def can_view_case(*, case, membership, roles) -> bool:
    role_set = set(roles or [])
    if role_set & set(MANAGE_VIEW_ROLES):
        return True
    return (
        SchoolRole.COUNSELOR in role_set
        and case.assigned_counselor_membership_id == membership.id
    )


def filter_cases(queryset, params):
    """فلاتر القائمة (البند 60) — كلها اختيارية وتُطبق فوق نطاق الدور."""
    status = params.get("status")
    if status == "live":
        queryset = queryset.filter(status__in=LIVE_CASE_STATUSES)
    elif status in CaseStatus.values:
        queryset = queryset.filter(status=status)

    priority = params.get("priority")
    if priority:
        queryset = queryset.filter(priority=priority)
    category = params.get("category")
    if category:
        queryset = queryset.filter(primary_referral__category=category)
    counselor = params.get("counselor")
    if counselor:
        queryset = queryset.filter(assigned_counselor_membership_id=counselor)
    grade = params.get("grade")
    if grade:
        queryset = queryset.filter(student__enrollments__grade_id=grade)
    section = params.get("section")
    if section:
        queryset = queryset.filter(student__enrollments__section_id=section)
    if grade or section:
        queryset = queryset.distinct()
    return queryset


#: ترتيبات معروضة للمستخدم (البند 61) — لا ترتيب حر من العميل
SORTS = {
    "recent": ("-last_activity_at", "-id"),
    "oldest_unattended": ("last_activity_at", "id"),
    "opened": ("-opened_at", "-id"),
}


def sort_cases(queryset, key: str):
    return queryset.order_by(*SORTS.get(key, SORTS["recent"]))


def counselor_dashboard_kpis(*, school, membership, roles) -> dict:
    """مؤشرات اللوحة (البند 57) — استعلامان مجمّعان لا صف لكل حالة."""
    cases = visible_cases(school=school, membership=membership, roles=roles)
    month_start = dj_timezone.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    aggregates = cases.aggregate(
        open_cases=Count("id", filter=Q(status__in=LIVE_CASE_STATUSES)),
        under_assessment=Count("id", filter=Q(status=CaseStatus.UNDER_ASSESSMENT)),
        follow_up_active=Count("id", filter=Q(status=CaseStatus.FOLLOW_UP_ACTIVE)),
        resolved=Count("id", filter=Q(status=CaseStatus.RESOLVED)),
        closed_this_month=Count(
            "id", filter=Q(status=CaseStatus.CLOSED, closed_at__gte=month_start)
        ),
    )

    role_set = set(roles or [])
    referrals = StudentReferral.objects.filter(school=school, status=ReferralStatus.NEW)
    if not (role_set & set(MANAGE_VIEW_ROLES)):
        # المرشد: الجديدة المعينة له أو غير المعينة (القابلة للاستلام)
        referrals = referrals.filter(
            Q(assigned_counselor_membership=membership)
            | Q(assigned_counselor_membership__isnull=True)
        )
    waiting_teacher = TeacherFollowUpRequest.objects.filter(
        case__in=cases, status=FollowUpRequestStatus.PENDING
    ).count()
    due_activities = FollowUpActivity.objects.filter(
        plan__case__in=cases,
        status=ActivityStatus.PENDING,
        due_date__lte=dj_timezone.localdate(),
    ).count()

    return {
        "new_referrals": referrals.count(),
        "open_cases": aggregates["open_cases"] or 0,
        "under_assessment": aggregates["under_assessment"] or 0,
        "follow_up_active": aggregates["follow_up_active"] or 0,
        "resolved": aggregates["resolved"] or 0,
        "waiting_teacher_response": waiting_teacher,
        "due_activities": due_activities,
        "closed_this_month": aggregates["closed_this_month"] or 0,
    }


def case_detail_queryset(school):
    return base_queryset(school).select_related(
        "opened_by_membership__user",
        "opened_by_membership__staff_profile",
        "closed_by_membership__user",
        "closed_by_membership__staff_profile",
    )


def case_sessions(case):
    return (
        case.sessions.select_related(
            "created_by_membership__user", "created_by_membership__staff_profile"
        )
        .order_by("-occurred_at", "-id")
    )


def active_sessions(case):
    return case_sessions(case).filter(status=SessionStatus.RECORDED)


def case_plans(case):
    return (
        case.plans.prefetch_related("goals", "activities")
        .select_related("created_by_membership__user", "created_by_membership__staff_profile")
        .order_by("-created_at")
    )


def case_teacher_requests(case):
    return (
        case.teacher_requests.select_related(
            "requested_from_membership__user",
            "requested_from_membership__staff_profile",
            "requested_by_membership__user",
            "requested_by_membership__staff_profile",
            "response__responded_by_membership__user",
            "response__responded_by_membership__staff_profile",
        )
        .order_by("-created_at")
    )


def case_timeline(case):
    return (
        case.events.select_related(
            "actor_membership__user", "actor_membership__staff_profile"
        )
        .order_by("-created_at", "-id")
    )


def teacher_requests_for(*, school, membership):
    """صندوق المعلم: طلباته هو فقط — لا حالة ولا ملاحظات إرشادية."""
    return (
        TeacherFollowUpRequest.objects.filter(
            school=school, requested_from_membership=membership
        )
        .exclude(status=FollowUpRequestStatus.CANCELLED)
        .select_related(
            "case__student",
            "requested_by_membership__user",
            "requested_by_membership__staff_profile",
            "response",
        )
        .order_by("status", "due_date", "-created_at")
    )


def student_counseling_summary(*, school, student, roles) -> dict:
    """ملخص «الإرشاد والمتابعة» في ملف الطالب (البنود 83-85).

    المعلم لا يستدعيه أصلًا (الطبقة الأعلى تحجبه) — والملخص بلا أي نص إرشادي.
    """
    cases = CounselorCase.objects.filter(school=school, student=student).select_related(
        "assigned_counselor_membership__user",
        "assigned_counselor_membership__staff_profile",
    )
    rows = []
    for case in cases.order_by("-opened_at"):
        counselor = case.assigned_counselor_membership
        profile = getattr(counselor, "staff_profile", None) if counselor else None
        rows.append(
            {
                "id": case.id,
                "status": case.status,
                "status_label": CaseStatus(case.status).label,
                "opened_at": case.opened_at.date().isoformat(),
                "closed_at": case.closed_at.date().isoformat() if case.closed_at else None,
                "counselor_name": (
                    profile.display_name
                    if profile
                    else (counselor.user.display_name if counselor else None)
                ),
                "last_activity_at": case.last_activity_at.date().isoformat(),
                "improvement_status": case.improvement_status or None,
            }
        )
    return {
        "open_cases": sum(1 for row in rows if row["status"] != CaseStatus.CLOSED),
        "total_cases": len(rows),
        "cases": rows,
    }
