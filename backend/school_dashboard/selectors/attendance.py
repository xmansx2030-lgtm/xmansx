"""مؤشرات الحضور والمواظبة للوحة الإدارة — قراءة من الملخصات القائمة.

**لا مصدر حقيقة جديد** (بند 6): كل رقم هنا مشتق من `DailyAttendanceSummary`
و`SchoolArrival` عبر نفس التعريفات المعتمدة في المراحل 8 و10 و11:

- `UNEXCUSED_FULL_DAY_FILTER` من `excuses.selectors` هو التعريف الوحيد لليوم
  «كامل بدون عذر» — لا يُعاد كتابته هنا.
- `UNDETERMINED` ليس غيابًا ولا حضورًا (بند 22) — عداد مستقل دائمًا.
- التأخر الصباحي من `SchoolArrival` فقط، وتأخر الحصص من `DailyAttendanceSummary`،
  ولا يُجمعان في رقم واحد أبدًا (بند 25/26/95).
"""

from datetime import date as date_cls
from datetime import timedelta

from django.db.models import Count, Q, Sum

from attendance.models import (
    AttendanceSession,
    AttendanceSessionStatus,
    DailyAbsenceStatus,
    DailyAttendanceSummary,
)
from devices.models import ArrivalStatus, SchoolArrival
from excuses.selectors import UNEXCUSED_FULL_DAY_FILTER

#: أقصى عدد نقاط في مخطط الاتجاه — نطاق أطول يُجمّع أسبوعيًا
MAX_TREND_POINTS = 62

#: يوم كامل «بعذر»: FULL بلا أي حصة غياب بدون عذر
_EXCUSED_FULL_DAY = Q(
    absence_status=DailyAbsenceStatus.FULL,
    unexcused_absent_periods=0,
    excused_absent_periods__gt=0,
)
#: يوم كامل مختلط: بعضه بعذر وبعضه بدونه — لا يُحسب في أي من الطرفين (بند 24)
_MIXED_FULL_DAY = Q(
    absence_status=DailyAbsenceStatus.FULL,
    unexcused_absent_periods__gt=0,
    excused_absent_periods__gt=0,
)


def summaries_queryset(*, school, date_range, scope=None):
    """صفوف ملخص اليوم داخل النطاق مع فلاتر الصف/الفصل.

    الفلترة على `section` الخاص بصف الملخص = **الفصل التاريخي لذلك اليوم**
    (م8 تخزنه في الصف نفسه)، فنقل الطالب لاحقًا لا يعيد تصنيف الماضي (بند 61).
    """
    rows = DailyAttendanceSummary.objects.filter(
        school=school,
        attendance_date__gte=date_range.from_date,
        attendance_date__lte=date_range.to_date,
    )
    scope = scope or {}
    if scope.get("section_id"):
        rows = rows.filter(section_id=scope["section_id"])
    elif scope.get("grade_id"):
        rows = rows.filter(section__grade_id=scope["grade_id"])
    return rows


def arrivals_queryset(*, school, date_range, scope=None):
    """وصول الطلاب الصباحي داخل النطاق.

    ‏SchoolArrival لا يحمل الفصل، فالفلترة تمر عبر ملخص اليوم لنفس (الطالب،
    التاريخ) — أي الفصل التاريخي نفسه، لا القيد الحالي.
    """
    arrivals = SchoolArrival.objects.filter(
        school=school,
        attendance_date__gte=date_range.from_date,
        attendance_date__lte=date_range.to_date,
    )
    scope = scope or {}
    if scope.get("section_id") or scope.get("grade_id"):
        scoped = summaries_queryset(school=school, date_range=date_range, scope=scope)
        pairs = scoped.values_list("student_id", "attendance_date")
        student_ids = {student_id for student_id, _ in pairs}
        arrivals = arrivals.filter(student_id__in=student_ids)
    return arrivals


def attendance_kpis(*, school, date_range, scope=None) -> dict:
    """مؤشرات المواظبة للنطاق — أعداد **أيام-طالب** لا طلاب متفردين.

    التسمية صريحة في الاستجابة (`unit`) حتى لا يُقرأ الرقم على أنه عدد طلاب.
    """
    rows = summaries_queryset(school=school, date_range=date_range, scope=scope)
    totals = rows.aggregate(
        student_days=Count("id"),
        full_absence=Count("id", filter=Q(absence_status=DailyAbsenceStatus.FULL)),
        partial_absence=Count("id", filter=Q(absence_status=DailyAbsenceStatus.PARTIAL)),
        no_absence=Count("id", filter=Q(absence_status=DailyAbsenceStatus.NONE)),
        undetermined=Count(
            "id", filter=Q(absence_status=DailyAbsenceStatus.UNDETERMINED)
        ),
        unexcused_full=Count("id", filter=UNEXCUSED_FULL_DAY_FILTER),
        excused_full=Count("id", filter=_EXCUSED_FULL_DAY),
        mixed_full=Count("id", filter=_MIXED_FULL_DAY),
        absent_periods=Sum("absent_periods"),
        unexcused_absent_periods=Sum("unexcused_absent_periods"),
        excused_absent_periods=Sum("excused_absent_periods"),
        period_late_occurrences=Sum("late_periods"),
        period_late_minutes=Sum("total_late_minutes"),
        complete_days=Count(
            "id", filter=~Q(absence_status=DailyAbsenceStatus.UNDETERMINED)
        ),
    )
    arrivals = arrivals_queryset(
        school=school, date_range=date_range, scope=scope
    ).aggregate(
        morning_late_occurrences=Count("id", filter=Q(status=ArrivalStatus.LATE)),
        morning_late_minutes=Sum(
            "counted_late_minutes", filter=Q(status=ArrivalStatus.LATE)
        ),
        morning_arrivals=Count("id"),
    )

    student_days = totals["student_days"] or 0
    return {
        "unit": "STUDENT_DAYS",
        "student_days": student_days,
        "distinct_students": rows.values("student_id").distinct().count(),
        "full_absence_days": totals["full_absence"] or 0,
        "partial_absence_days": totals["partial_absence"] or 0,
        "no_absence_days": totals["no_absence"] or 0,
        # UNDETERMINED عداد مستقل: ليس غيابًا ولا حضورًا (بند 22)
        "undetermined_days": totals["undetermined"] or 0,
        "unexcused_full_absence_days": totals["unexcused_full"] or 0,
        "excused_full_absence_days": totals["excused_full"] or 0,
        "mixed_full_absence_days": totals["mixed_full"] or 0,
        "absent_periods": totals["absent_periods"] or 0,
        "unexcused_absent_periods": totals["unexcused_absent_periods"] or 0,
        "excused_absent_periods": totals["excused_absent_periods"] or 0,
        "period_late_occurrences": totals["period_late_occurrences"] or 0,
        "period_late_minutes": totals["period_late_minutes"] or 0,
        "morning_late_occurrences": arrivals["morning_late_occurrences"] or 0,
        "morning_late_minutes": arrivals["morning_late_minutes"] or 0,
        "morning_arrivals": arrivals["morning_arrivals"] or 0,
        "completeness": _completeness(
            complete=totals["complete_days"] or 0, total=student_days
        ),
    }


def _completeness(*, complete: int, total: int) -> dict:
    """نسبة اكتمال بيانات الفترة — تحذير صريح بدل تفسير الأرقام كحقيقة نهائية."""
    incomplete = max(total - complete, 0)
    pct = round((incomplete / total) * 100, 1) if total else 0.0
    return {
        "complete_student_days": complete,
        "incomplete_student_days": incomplete,
        "incomplete_pct": pct,
        # عتبة عرض التحذير في الواجهة — وصفية لا تحجب الأرقام
        "is_significant": pct >= 20.0,
    }


def attendance_trend(*, school, date_range, scope=None) -> dict:
    """سلسلة يومية (أو أسبوعية للنطاقات الطويلة) لأهم مؤشرات الغياب.

    القيم **أعداد** لا نسب — ولا يخلط المحور بين الاثنين (بند 28).
    """
    rows = summaries_queryset(school=school, date_range=date_range, scope=scope)
    daily = (
        rows.values("attendance_date")
        .annotate(
            full_absence=Count("id", filter=Q(absence_status=DailyAbsenceStatus.FULL)),
            partial_absence=Count(
                "id", filter=Q(absence_status=DailyAbsenceStatus.PARTIAL)
            ),
            unexcused_full=Count("id", filter=UNEXCUSED_FULL_DAY_FILTER),
            undetermined=Count(
                "id", filter=Q(absence_status=DailyAbsenceStatus.UNDETERMINED)
            ),
        )
        .order_by("attendance_date")
    )
    late_by_day = dict(
        arrivals_queryset(school=school, date_range=date_range, scope=scope)
        .filter(status=ArrivalStatus.LATE)
        .values("attendance_date")
        .annotate(total=Count("id"))
        .values_list("attendance_date", "total")
    )

    points = [
        {
            "date": row["attendance_date"].isoformat(),
            "full_absence": row["full_absence"],
            "partial_absence": row["partial_absence"],
            "unexcused_full_absence": row["unexcused_full"],
            "undetermined": row["undetermined"],
            "morning_late": late_by_day.get(row["attendance_date"], 0),
        }
        for row in daily
    ]
    granularity = "DAY"
    if len(points) > MAX_TREND_POINTS:
        points = _weekly(points)
        granularity = "WEEK"
    return {
        "unit": "STUDENT_DAYS",
        "granularity": granularity,
        "points": points,
    }


def _weekly(points: list[dict]) -> list[dict]:
    """تجميع أسبوعي يبدأ من الأحد — للنطاقات الأطول من شهرين."""
    buckets: dict[str, dict] = {}
    for point in points:
        day = date_cls.fromisoformat(point["date"])
        start = day - timedelta(days=(day.weekday() - 6) % 7)
        key = start.isoformat()
        bucket = buckets.setdefault(
            key,
            {
                "date": key,
                "full_absence": 0,
                "partial_absence": 0,
                "unexcused_full_absence": 0,
                "undetermined": 0,
                "morning_late": 0,
            },
        )
        for field in (
            "full_absence",
            "partial_absence",
            "unexcused_full_absence",
            "undetermined",
            "morning_late",
        ):
            bucket[field] += point[field]
    return [buckets[key] for key in sorted(buckets)]


def section_breakdown(*, school, date_range, scope=None) -> dict:
    """مقارنة وصفية بين الفصول — «أعلى غياب» لا «الأسوأ» (بند 33)."""
    rows = summaries_queryset(school=school, date_range=date_range, scope=scope)
    grouped = (
        rows.values("section_id", "section__name", "section__grade__name")
        .annotate(
            student_days=Count("id"),
            students=Count("student_id", distinct=True),
            unexcused_full=Count("id", filter=UNEXCUSED_FULL_DAY_FILTER),
            full_absence=Count("id", filter=Q(absence_status=DailyAbsenceStatus.FULL)),
            partial_absence=Count(
                "id", filter=Q(absence_status=DailyAbsenceStatus.PARTIAL)
            ),
            period_late=Sum("late_periods"),
        )
        .order_by("-unexcused_full", "section__grade__name", "section__name")
    )
    late_by_section = _morning_late_by_section(
        school=school, date_range=date_range, scope=scope
    )
    return {
        "unit": "STUDENT_DAYS",
        "sections": [
            {
                "section_id": row["section_id"],
                "section_name": row["section__name"],
                "grade_name": row["section__grade__name"],
                "students": row["students"],
                "student_days": row["student_days"],
                "full_absence_days": row["full_absence"],
                "partial_absence_days": row["partial_absence"],
                "unexcused_full_absence_days": row["unexcused_full"],
                "period_late_occurrences": row["period_late"] or 0,
                "morning_late_occurrences": late_by_section.get(row["section_id"], 0),
            }
            for row in grouped
        ],
    }


def _morning_late_by_section(*, school, date_range, scope=None) -> dict[int, int]:
    """التأخر الصباحي منسوبًا للفصل التاريخي عبر ملخص اليوم لنفس (طالب، تاريخ)."""
    late_pairs = set(
        arrivals_queryset(school=school, date_range=date_range, scope=scope)
        .filter(status=ArrivalStatus.LATE)
        .values_list("student_id", "attendance_date")
    )
    if not late_pairs:
        return {}
    counts: dict[int, int] = {}
    rows = summaries_queryset(school=school, date_range=date_range, scope=scope)
    for student_id, day, section_id in rows.values_list(
        "student_id", "attendance_date", "section_id"
    ):
        if (student_id, day) in late_pairs:
            counts[section_id] = counts.get(section_id, 0) + 1
    return counts


def today_operations(*, school) -> dict:
    """تشغيل اليوم — يعيد استخدام لوحة متابعة م7 كما هي بلا إعادة عد.

    الحصة الحالية تُحسب خادميًا من جدول الأجراس وتوقيت المدرسة (بند 15).
    """
    from attendance.selectors.monitoring import get_current_section_attendance_statuses

    monitoring = get_current_section_attendance_statuses(school=school)
    summary = monitoring.get("summary")
    completion = None
    if summary and summary["total"]:
        completion = round((summary["submitted"] / summary["total"]) * 100, 1)

    period = monitoring["period"]
    if period is None:
        operational_state = "IDLE"
        headline = "لا توجد حصة جارية الآن — لا توجد متابعة تحضير مطلوبة."
    elif summary and summary["overdue_total"] > 0:
        operational_state = "ACTION_REQUIRED"
        headline = (
            f"{period['name']} جارية — {summary['overdue_total']} فصل يحتاج متابعة "
            f"من أصل {summary['total']}."
        )
    elif summary and summary["submitted"] == summary["total"]:
        operational_state = "ON_TRACK"
        headline = f"اكتمل تحضير جميع فصول {period['name']}."
    else:
        operational_state = "IN_PROGRESS"
        submitted = summary["submitted"] if summary else 0
        total = summary["total"] if summary else 0
        headline = f"{period['name']} جارية — اعتُمد تحضير {submitted} من {total} فصلًا."
    return {
        "school_time": monitoring["school_time"],
        "date": monitoring["date"],
        "period": period,
        "alert": monitoring["alert"],
        "summary": summary,
        "submission_completion_pct": completion,
        "operational_state": operational_state,
        "headline": headline,
        "updated_at": monitoring["school_time"],
        # لا حصة جارية: قبل الدوام أو فسحة أو يوم غير دراسي — ليست حالة خطأ
        "has_active_period": period is not None,
    }


def submitted_sessions_count(*, school, date_range, scope=None) -> int:
    """جلسات معتمدة داخل النطاق — مقام أي نسبة حضور مستقبلية (بند 29)."""
    sessions = AttendanceSession.objects.filter(
        school=school,
        attendance_date__gte=date_range.from_date,
        attendance_date__lte=date_range.to_date,
        status=AttendanceSessionStatus.SUBMITTED,
    )
    scope = scope or {}
    if scope.get("section_id"):
        sessions = sessions.filter(section_id=scope["section_id"])
    elif scope.get("grade_id"):
        sessions = sessions.filter(section__grade_id=scope["grade_id"])
    return sessions.count()
