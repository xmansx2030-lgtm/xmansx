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
from datetime import datetime as datetime_cls
from datetime import time as time_cls
from datetime import timedelta

from django.db.models import Count, Exists, OuterRef, Q, Sum

from attendance.models import (
    AttendanceMark,
    AttendanceMarkStatus,
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
        scoped = DailyAttendanceSummary.objects.filter(
            school=school,
            student_id=OuterRef("student_id"),
            attendance_date=OuterRef("attendance_date"),
        )
        if scope.get("section_id"):
            scoped = scoped.filter(section_id=scope["section_id"])
        else:
            scoped = scoped.filter(section__grade_id=scope["grade_id"])
        arrivals = arrivals.annotate(_in_historical_scope=Exists(scoped)).filter(
            _in_historical_scope=True
        )
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
    open_overdue = 0
    if summary:
        open_overdue = (
            summary.get("overdue_not_started", 0)
            + summary.get("overdue_in_progress", 0)
        )
    if period is None:
        operational_state = "IDLE"
        headline = "لا توجد حصة جارية الآن — لا توجد متابعة تحضير مطلوبة."
    elif summary and summary["submitted"] == summary["total"]:
        operational_state = "ON_TRACK"
        late_note = (
            f" (اعتمد {summary.get('overdue_submitted', 0)} فصل متأخرًا)."
            if summary.get("overdue_submitted", 0)
            else "."
        )
        headline = f"اكتمل تحضير جميع فصول {period['name']}{late_note}"
    elif summary and open_overdue > 0:
        operational_state = "ACTION_REQUIRED"
        headline = (
            f"{period['name']} جارية — {open_overdue} فصل يحتاج متابعة "
            f"من أصل {summary['total']}."
        )
    else:
        operational_state = "IN_PROGRESS"
        submitted = summary["submitted"] if summary else 0
        total = summary["total"] if summary else 0
        headline = f"{period['name']} جارية — اعتُمد تحضير {submitted} من {total} فصلًا."
    attendance_date = date_cls.fromisoformat(monitoring["date"])
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
        "live_attendance": live_attendance_snapshot(
            school=school,
            attendance_date=attendance_date,
            current_period_sequence=period["sequence"] if period else None,
            current_time=datetime_cls.fromisoformat(monitoring["school_time"]).time(),
        ),
        "daily_attendance": daily_attendance_snapshot(
            school=school, attendance_date=attendance_date
        ),
        # لا حصة جارية: قبل الدوام أو فسحة أو يوم غير دراسي — ليست حالة خطأ
        "has_active_period": period is not None,
    }


def daily_attendance_snapshot(*, school, attendance_date: date_cls) -> dict:
    """إثبات الحضور والغياب المسجل خلال اليوم، مستقل عن الحصة الجارية.

    الحضور لا يساوي مجرد شمول الطالب في جلسة معتمدة: لا يدخل الطالب في
    ``present_students`` إلا إذا ثبت حضوره في حصة (حاضر/متأخر) أو سجل له وصول
    صباحي. أما ``absent_students`` فهو عدد من لديهم غياب مسجل في حصة واحدة على
    الأقل، وقد يتقاطع مع الحضور عند غياب الطالب في حصة وحضوره في أخرى.
    """
    from attendance.selectors.monitoring import expected_sections_queryset
    from attendance.services.sessions import _active_year
    from students.models import EnrollmentStatus
    from students.services.enrollments import enrollments_on_date

    year = _active_year(school)
    section_ids = list(
        expected_sections_queryset(school=school, year=year).values_list("id", flat=True)
    )
    student_ids = set(
        enrollments_on_date(school=school, on_date=attendance_date)
        .filter(
            section_id__in=section_ids,
            status=EnrollmentStatus.ACTIVE,
            student__status="ACTIVE",
        )
        .values_list("student_id", flat=True)
        .distinct()
    )
    if not student_ids:
        return {
            "total_students": 0,
            "present_students": 0,
            "absent_students": 0,
            "unrecorded_students": 0,
        }

    summary_rows = DailyAttendanceSummary.objects.filter(
        school=school,
        attendance_date=attendance_date,
        student_id__in=student_ids,
        submitted_periods__gt=0,
    )
    present_student_ids = set(
        summary_rows.filter(Q(present_periods__gt=0) | Q(late_periods__gt=0))
        .values_list("student_id", flat=True)
        .distinct()
    )
    arrival_student_ids = set(
        SchoolArrival.objects.filter(
            school=school,
            attendance_date=attendance_date,
            student_id__in=student_ids,
        ).values_list("student_id", flat=True)
    )
    present_student_ids.update(arrival_student_ids)
    absent_students = (
        summary_rows.filter(absent_periods__gt=0)
        .values("student_id")
        .distinct()
        .count()
    )
    recorded_student_ids = set(
        summary_rows.values_list("student_id", flat=True).distinct()
    )
    recorded_student_ids.update(arrival_student_ids)
    return {
        "total_students": len(student_ids),
        "present_students": len(present_student_ids),
        "absent_students": absent_students,
        "unrecorded_students": max(len(student_ids) - len(recorded_student_ids), 0),
    }


def live_attendance_snapshot(
    *,
    school,
    attendance_date: date_cls,
    current_period_sequence: int | None,
    current_time: time_cls | None = None,
) -> dict:
    """حالة الحصة الجارية مع مؤشر مستقل للغياب المتتابع اليومي.

    حاضر/غائب/مستأذن/متأخر تصف **الحصة الحالية فقط**؛ لذلك يكفي اعتماد جلسة
    الحصة الحالية للفصل حتى يدخل طلابه في الأرقام. أما ``daily_absent_students``
    فلا يصنّف الطالب غائبًا اليوم حتى تكتمل جلسات فصله من أول حصة إلى الحالية
    ويكون غائبًا في جميعها دون حضور أو تأخر في أي حصة.

    «مستأذن» مشتق من سجل استئذان ساري حان وقت خروجه؛ وهو حالة تشغيلية مستقلة
    لا تحول سجل الحضور الخام إلى عذر غياب ولا تعدله.
    """
    empty = {
        "status": "NO_ACTIVE_PERIOD",
        "total_students": 0,
        "covered_students": 0,
        "pending_students": 0,
        "present_students": 0,
        "absent_students": 0,
        "leave_students": 0,
        "late_students": 0,
        "morning_late_students": 0,
        "daily_absent_students": 0,
        "daily_covered_students": 0,
        "daily_pending_sections": 0,
        "covered_sections": 0,
        "pending_sections": 0,
        "current_period_sequence": None,
    }
    if current_period_sequence is None:
        return empty

    from attendance.selectors.monitoring import expected_sections_queryset
    from attendance.services.day_context import get_or_create_attendance_day_context
    from attendance.services.sessions import _active_year
    from students.models import EnrollmentStatus
    from students.services.enrollments import enrollments_on_date

    year = _active_year(school)
    context = get_or_create_attendance_day_context(
        school=school, attendance_date=attendance_date
    )
    all_periods = sorted(context.attendance_periods, key=lambda item: item["sequence"])
    current_index = next(
        (
            index
            for index, item in enumerate(all_periods)
            if item["sequence"] == current_period_sequence
        ),
        None,
    )
    if current_index is None:
        return empty
    sequences = [item["sequence"] for item in all_periods[: current_index + 1]]
    if not sequences:
        return empty

    sections = list(expected_sections_queryset(school=school, year=year))
    section_ids = [section.id for section in sections]
    enrollments = list(
        enrollments_on_date(school=school, on_date=attendance_date)
        .filter(
            section_id__in=section_ids,
            status=EnrollmentStatus.ACTIVE,
            student__status="ACTIVE",
        )
        .values_list("student_id", "section_id")
        .distinct()
    )
    students_by_section: dict[int, set[int]] = {}
    for student_id, section_id in enrollments:
        students_by_section.setdefault(section_id, set()).add(student_id)
    total_students = len({student_id for student_id, _ in enrollments})
    all_student_ids = {student_id for student_id, _ in enrollments}

    sessions = list(
        AttendanceSession.objects.filter(
            school=school,
            attendance_date=attendance_date,
            section_id__in=section_ids,
            period_sequence__in=sequences,
            status=AttendanceSessionStatus.SUBMITTED,
        ).only("id", "section_id", "period_sequence")
    )
    submitted_by_section: dict[int, set[int]] = {}
    session_id_by_section_period: dict[tuple[int, int], int] = {}
    for session in sessions:
        submitted_by_section.setdefault(session.section_id, set()).add(session.period_sequence)
        session_id_by_section_period[(session.section_id, session.period_sequence)] = session.id

    # أرقام الحصة الجارية لا تعتمد على اكتمال الحصص السابقة.
    covered_section_ids = {
        section_id
        for section_id, submitted_sequences in submitted_by_section.items()
        if current_period_sequence in submitted_sequences
    }
    covered_student_ids = {
        student_id
        for section_id in covered_section_ids
        for student_id in students_by_section.get(section_id, set())
    }
    current_session_ids = [
        session_id_by_section_period[(section_id, current_period_sequence)]
        for section_id in covered_section_ids
    ]
    current_absent_ids = set(
        AttendanceMark.objects.filter(
            session_id__in=current_session_ids,
            student_id__in=covered_student_ids,
            status=AttendanceMarkStatus.ABSENT,
        ).values_list("student_id", flat=True)
    )
    late_ids = set(
        AttendanceMark.objects.filter(
            session_id__in=current_session_ids,
            student_id__in=covered_student_ids,
            status=AttendanceMarkStatus.LATE,
        ).values_list("student_id", flat=True)
    )

    from student_leaves.models import StudentLeavePermission, StudentLeaveStatus

    leave_ids = set(
        StudentLeavePermission.objects.filter(
            school=school,
            leave_date=attendance_date,
            leave_time__lte=current_time or time_cls.max,
            status=StudentLeaveStatus.ACTIVE,
            student_id__in=covered_student_ids,
        ).values_list("student_id", flat=True)
    )
    # الاستئذان حالة تشغيلية آنية تتقدم في العرض على علامة الحصة، من دون تغييرها.
    absent_ids = current_absent_ids - leave_ids
    # القيود تمنع الجمع بين غائب ومتأخر، والاستبعاد دفاعي للبيانات التاريخية.
    late_ids -= current_absent_ids | leave_ids
    present_students = len(
        covered_student_ids - absent_ids - leave_ids - late_ids
    )
    # التأخر الصباحي مصدره الوصول من البوابة فقط، ويظل عدادًا مستقلًا عن
    # «متأخر في الحصة» وعن الاستئذان والغياب بعذر.
    morning_late_students = SchoolArrival.objects.filter(
        school=school,
        attendance_date=attendance_date,
        student_id__in=all_student_ids,
        status=ArrivalStatus.LATE,
    ).values("student_id").distinct().count()

    # الغياب اليومي المتتابع يحتاج اكتمال كل الحصص حتى الحالية، بخلاف أرقام
    # الحصة أعلاه. المتأخر حضر، لذلك لا يمكن أن يكون ضمن هذا العداد.
    required_sequences = set(sequences)
    daily_covered_section_ids = {
        section_id
        for section_id, submitted_sequences in submitted_by_section.items()
        if required_sequences <= submitted_sequences
    }
    daily_covered_student_ids = {
        student_id
        for section_id in daily_covered_section_ids
        for student_id in students_by_section.get(section_id, set())
    }
    daily_session_ids = [
        session_id_by_section_period[(section_id, sequence)]
        for section_id in daily_covered_section_ids
        for sequence in sequences
    ]
    daily_absent_ids = {
        row["student_id"]
        for row in (
            AttendanceMark.objects.filter(
                session_id__in=daily_session_ids,
                student_id__in=daily_covered_student_ids,
                status=AttendanceMarkStatus.ABSENT,
            )
            .values("student_id")
            .annotate(periods=Count("session__period_sequence", distinct=True))
        )
        if row["periods"] == len(sequences)
    }
    covered_students = len(covered_student_ids)
    return {
        "status": "AVAILABLE",
        "total_students": total_students,
        "covered_students": covered_students,
        "pending_students": max(total_students - covered_students, 0),
        "present_students": present_students,
        "absent_students": len(absent_ids),
        "leave_students": len(leave_ids),
        "late_students": len(late_ids),
        "morning_late_students": morning_late_students,
        "daily_absent_students": len(daily_absent_ids),
        "daily_covered_students": len(daily_covered_student_ids),
        "daily_pending_sections": max(
            len(sections) - len(daily_covered_section_ids), 0
        ),
        "covered_sections": len(covered_section_ids),
        "pending_sections": max(len(sections) - len(covered_section_ids), 0),
        "current_period_sequence": current_period_sequence,
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
