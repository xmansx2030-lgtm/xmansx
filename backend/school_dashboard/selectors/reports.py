"""Detailed school reports for managers and vice principals.

The dashboard remains an operational summary.  These selectors expose
paginated, filterable rows without creating another source of truth.
"""

from django.db.models import Count, Prefetch, Q, Sum

from attendance.models import DailyAbsenceStatus, DailyCompleteness
from common.errors import ApiError
from devices.models import ArrivalStatus
from referrals import selectors as referral_selectors
from referrals.api.serializers import serialize_referral_row
from referrals.models import ReferralPriority, ReferralStatus
from school_dashboard.selectors.attendance import arrivals_queryset, summaries_queryset
from students.models import EnrollmentStatus, Student, StudentEnrollment

ABSENCE_TYPES = {"ALL", "FULL", "PARTIAL"}
EXCUSE_TYPES = {"ALL", "EXCUSED", "UNEXCUSED", "MIXED"}
LATENESS_TYPES = {"ALL", "MORNING", "PERIOD"}


def _positive_int(value, *, field: str, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ApiError(
            "REPORT_INVALID_FILTER",
            "قيمة فلتر التقرير غير صحيحة.",
            details={"field": field},
        ) from None
    if parsed < 0:
        raise ApiError(
            "REPORT_INVALID_FILTER",
            "قيمة فلتر التقرير لا يمكن أن تكون سالبة.",
            details={"field": field},
        )
    return parsed


def _choice(value, *, allowed: set[str], field: str, default: str) -> str:
    normalized = (value or default).upper()
    if normalized not in allowed:
        raise ApiError(
            "REPORT_INVALID_FILTER",
            "قيمة فلتر التقرير غير صحيحة.",
            details={"field": field},
        )
    return normalized


def _student_id(*, school, value) -> int | None:
    if value in (None, ""):
        return None
    student_id = _positive_int(value, field="student")
    if not Student.objects.filter(school=school, id=student_id).exists():
        raise ApiError("REPORT_STUDENT_NOT_FOUND", "الطالب غير موجود.", status_code=404)
    return student_id


def _paginate(items: list[dict], params) -> tuple[list[dict], int, int, int]:
    page = max(_positive_int(params.get("page"), field="page", default=1), 1)
    page_size = _positive_int(params.get("page_size"), field="page_size", default=25)
    page_size = min(max(page_size, 1), 100)
    total = len(items)
    start = (page - 1) * page_size
    return items[start : start + page_size], total, page, page_size


def absence_report(*, school, date_range, scope, params) -> dict:
    absence_type = _choice(
        params.get("absence_type"), allowed=ABSENCE_TYPES, field="absence_type", default="ALL"
    )
    excuse_type = _choice(
        params.get("excuse_type"), allowed=EXCUSE_TYPES, field="excuse_type", default="ALL"
    )
    student_id = _student_id(school=school, value=params.get("student"))

    rows = summaries_queryset(school=school, date_range=date_range, scope=scope).filter(
        absence_status__in=[DailyAbsenceStatus.FULL, DailyAbsenceStatus.PARTIAL]
    )
    if student_id:
        rows = rows.filter(student_id=student_id)
    if absence_type != "ALL":
        rows = rows.filter(absence_status=absence_type)
    if excuse_type == "EXCUSED":
        rows = rows.filter(excused_absent_periods__gt=0, unexcused_absent_periods=0)
    elif excuse_type == "UNEXCUSED":
        rows = rows.filter(unexcused_absent_periods__gt=0)
    elif excuse_type == "MIXED":
        rows = rows.filter(
            excused_absent_periods__gt=0,
            unexcused_absent_periods__gt=0,
        )

    totals = rows.aggregate(
        student_days=Count("id"),
        students=Count("student_id", distinct=True),
        full_days=Count("id", filter=Q(absence_status=DailyAbsenceStatus.FULL)),
        partial_days=Count("id", filter=Q(absence_status=DailyAbsenceStatus.PARTIAL)),
        excused_periods=Sum("excused_absent_periods"),
        unexcused_periods=Sum("unexcused_absent_periods"),
        incomplete_days=Count(
            "id", filter=Q(completeness_status=DailyCompleteness.INCOMPLETE)
        ),
    )
    grouped = (
        rows.values(
            "student_id",
            "student__full_name",
            "section_id",
            "section__name",
            "section__grade__name",
        )
        .annotate(
            full_absence_days=Count(
                "id", filter=Q(absence_status=DailyAbsenceStatus.FULL)
            ),
            partial_absence_days=Count(
                "id", filter=Q(absence_status=DailyAbsenceStatus.PARTIAL)
            ),
            absent_periods=Sum("absent_periods"),
            excused_absent_periods=Sum("excused_absent_periods"),
            unexcused_absent_periods=Sum("unexcused_absent_periods"),
            incomplete_days=Count(
                "id", filter=Q(completeness_status=DailyCompleteness.INCOMPLETE)
            ),
        )
        .order_by("-full_absence_days", "-unexcused_absent_periods", "student__full_name")
    )
    items = [
        {
            "student_id": row["student_id"],
            "full_name": row["student__full_name"],
            "grade_name": row["section__grade__name"],
            "section_name": row["section__name"],
            "full_absence_days": row["full_absence_days"],
            "partial_absence_days": row["partial_absence_days"],
            "absent_periods": row["absent_periods"] or 0,
            "excused_absent_periods": row["excused_absent_periods"] or 0,
            "unexcused_absent_periods": row["unexcused_absent_periods"] or 0,
            "incomplete_days": row["incomplete_days"],
        }
        for row in grouped
    ]
    page_items, count, page, page_size = _paginate(items, params)
    return {
        "summary": {
            "students": totals["students"] or 0,
            "student_days": totals["student_days"] or 0,
            "full_absence_days": totals["full_days"] or 0,
            "partial_absence_days": totals["partial_days"] or 0,
            "excused_absent_periods": totals["excused_periods"] or 0,
            "unexcused_absent_periods": totals["unexcused_periods"] or 0,
            "incomplete_days": totals["incomplete_days"] or 0,
        },
        "results": page_items,
        "count": count,
        "page": page,
        "page_size": page_size,
    }


def _student_labels(school, student_ids: set[int]) -> dict[int, dict]:
    enrollments = StudentEnrollment.objects.select_related("grade", "section").order_by(
        "-enrolled_at", "-id"
    )
    students = Student.objects.filter(school=school, id__in=student_ids).prefetch_related(
        Prefetch("enrollments", queryset=enrollments, to_attr="report_enrollments")
    )
    result = {}
    for student in students:
        current = next(
            (
                enrollment
                for enrollment in student.report_enrollments
                if enrollment.status == EnrollmentStatus.ACTIVE
            ),
            student.report_enrollments[0] if student.report_enrollments else None,
        )
        result[student.id] = {
            "student_id": student.id,
            "full_name": student.full_name,
            "grade_name": current.grade.name if current else None,
            "section_name": current.section.name if current else None,
        }
    return result


def lateness_report(*, school, date_range, scope, params) -> dict:
    lateness_type = _choice(
        params.get("lateness_type"),
        allowed=LATENESS_TYPES,
        field="lateness_type",
        default="ALL",
    )
    student_id = _student_id(school=school, value=params.get("student"))
    min_occurrences = _positive_int(
        params.get("min_occurrences"), field="min_occurrences", default=0
    )
    min_minutes = _positive_int(params.get("min_minutes"), field="min_minutes", default=0)

    period_rows = summaries_queryset(school=school, date_range=date_range, scope=scope).filter(
        late_periods__gt=0
    )
    morning_rows = arrivals_queryset(school=school, date_range=date_range, scope=scope).filter(
        status=ArrivalStatus.LATE
    )
    if student_id:
        period_rows = period_rows.filter(student_id=student_id)
        morning_rows = morning_rows.filter(student_id=student_id)

    period = {
        row["student_id"]: row
        for row in period_rows.values("student_id").annotate(
            occurrences=Sum("late_periods"), minutes=Sum("total_late_minutes")
        )
    }
    morning = {
        row["student_id"]: row
        for row in morning_rows.values("student_id").annotate(
            occurrences=Count("id"), minutes=Sum("counted_late_minutes")
        )
    }
    if lateness_type == "MORNING":
        student_ids = set(morning)
    elif lateness_type == "PERIOD":
        student_ids = set(period)
    else:
        student_ids = set(morning) | set(period)

    labels = _student_labels(school, student_ids)
    items = []
    for current_id in student_ids:
        morning_row = morning.get(current_id, {})
        period_row = period.get(current_id, {})
        morning_occurrences = morning_row.get("occurrences", 0) or 0
        period_occurrences = period_row.get("occurrences", 0) or 0
        morning_minutes = morning_row.get("minutes", 0) or 0
        period_minutes = period_row.get("minutes", 0) or 0
        selected_occurrences = (
            morning_occurrences
            if lateness_type == "MORNING"
            else period_occurrences
            if lateness_type == "PERIOD"
            else morning_occurrences + period_occurrences
        )
        selected_minutes = (
            morning_minutes
            if lateness_type == "MORNING"
            else period_minutes
            if lateness_type == "PERIOD"
            else morning_minutes + period_minutes
        )
        if selected_occurrences < min_occurrences or selected_minutes < min_minutes:
            continue
        items.append(
            {
                **labels[current_id],
                "morning_occurrences": morning_occurrences,
                "morning_minutes": morning_minutes,
                "period_occurrences": period_occurrences,
                "period_minutes": period_minutes,
            }
        )
    items.sort(
        key=lambda row: (
            -(row["morning_occurrences"] + row["period_occurrences"]),
            -(row["morning_minutes"] + row["period_minutes"]),
            row["full_name"],
        )
    )
    page_items, count, page, page_size = _paginate(items, params)
    return {
        "summary": {
            "students": count,
            "morning_occurrences": sum(row["morning_occurrences"] for row in items),
            "morning_minutes": sum(row["morning_minutes"] for row in items),
            "period_occurrences": sum(row["period_occurrences"] for row in items),
            "period_minutes": sum(row["period_minutes"] for row in items),
        },
        "results": page_items,
        "count": count,
        "page": page,
        "page_size": page_size,
    }


def referrals_report(*, school, membership, roles, date_range, params) -> dict:
    queryset = referral_selectors.visible_referrals(
        school=school, membership=membership, roles=roles
    )
    queryset = referral_selectors.apply_filters(queryset, params).filter(
        created_at__date__gte=date_range.from_date,
        created_at__date__lte=date_range.to_date,
    )
    priority = (params.get("priority") or "").upper()
    if priority:
        if priority not in ReferralPriority.values:
            raise ApiError(
                "REPORT_INVALID_FILTER",
                "قيمة أولوية الإحالة غير صحيحة.",
                details={"field": "priority"},
            )
        queryset = queryset.filter(priority=priority)
    search = (params.get("search") or "").strip()
    if search:
        queryset = queryset.filter(student__full_name__icontains=search)

    totals = queryset.aggregate(
        total=Count("id"),
        new=Count("id", filter=Q(status=ReferralStatus.NEW)),
        acknowledged=Count("id", filter=Q(status=ReferralStatus.ACKNOWLEDGED)),
        closed=Count("id", filter=Q(status=ReferralStatus.CLOSED)),
        unassigned=Count(
            "id",
            filter=Q(assigned_counselor_membership__isnull=True)
            & Q(status__in=[ReferralStatus.NEW, ReferralStatus.ACKNOWLEDGED]),
        ),
        high_priority=Count("id", filter=Q(priority=ReferralPriority.HIGH)),
    )
    items = [serialize_referral_row(referral) for referral in queryset.order_by("-created_at")]
    page_items, count, page, page_size = _paginate(items, params)
    return {
        "summary": {key: value or 0 for key, value in totals.items()},
        "results": page_items,
        "count": count,
        "page": page,
        "page_size": page_size,
    }
