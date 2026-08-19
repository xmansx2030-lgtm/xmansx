"""تحليلات الغياب (م8): حصة محددة، عدة حصص (ALL/ANY)، وملخص اليوم.

قواعد صلبة:
- غياب الجلسة ≠ حضور ولا غياب: الفصل غير المكتمل للحصص المحددة يستبعد طلابه من
  النتيجة كليًا ويعلن ضمن incomplete_sections بسببه — لا استنتاج جماعي أبدًا.
- الهوية التاريخية للحصة: period_sequence (snapshot وقت الفتح) + AttendanceDayContext
  — لا BellPeriod حي.
- ‏Data minimization: لا رقم هوية ولا جوال ولي أمر في أي استجابة تحليلات.
- استعلامات شبه ثابتة العدد مهما بلغ عدد الطلاب (لا N+1).
"""

from datetime import date as date_cls

from django.db.models import Count, Q, Sum

from attendance.models import (
    AttendanceMark,
    AttendanceMarkStatus,
    AttendanceSession,
    AttendanceSessionStatus,
    DailyAbsenceStatus,
    DailyAttendanceSummary,
    DailyCompleteness,
)
from attendance.selectors.monitoring import expected_sections_queryset
from attendance.services.day_context import get_or_create_attendance_day_context
from attendance.services.sessions import _active_year
from common.errors import ApiError
from students.models import Student
from students.services.enrollments import enrollments_on_date

MATCH_ALL = "ALL_ABSENT"
MATCH_ANY = "ANY_ABSENT"
MAX_SELECTED_PERIODS = 20
PAGE_SIZES = (25, 50, 100)


def _validate_sequences(sequences: list[int], context) -> list[int]:
    if not sequences:
        raise ApiError("INVALID_PERIOD_SELECTION", "اختر حصة واحدة على الأقل.")
    normalized = sorted(set(sequences))
    if len(normalized) > MAX_SELECTED_PERIODS:
        raise ApiError("INVALID_PERIOD_SELECTION", "عدد الحصص المحددة أكبر من المسموح.")
    valid = {p["sequence"] for p in context.attendance_periods}
    unknown = [s for s in normalized if s not in valid]
    if unknown:
        raise ApiError(
            "INVALID_PERIOD_SELECTION",
            "بعض الحصص المحددة غير موجودة في جدول ذلك اليوم.",
            details={"unknown_sequences": unknown},
        )
    return normalized


def _morning_arrivals(school, attendance_date, student_ids) -> dict[int, str]:
    """أوقات دخول المدرسة (م8.5) بمنطقة المدرسة — None يعرض «لا توجد بصمة دخول»."""
    from zoneinfo import ZoneInfo

    from devices.models import SchoolArrival
    from schools.services.settings import get_or_create_settings

    if not student_ids:
        return {}
    tz = ZoneInfo(get_or_create_settings(school=school).timezone)
    return {
        a.student_id: a.first_arrival_at.astimezone(tz).strftime("%H:%M")
        for a in SchoolArrival.objects.filter(
            school=school, attendance_date=attendance_date, student_id__in=student_ids
        )
    }


def _paginate(items: list, page: int, page_size: int) -> tuple[list, int]:
    page = max(page, 1)
    if page_size not in PAGE_SIZES:
        page_size = PAGE_SIZES[0]
    start = (page - 1) * page_size
    return items[start : start + page_size], page_size


def get_multi_period_report(
    *,
    school,
    attendance_date: date_cls,
    sequences: list[int],
    match: str = MATCH_ALL,
    grade_id: int | None = None,
    section_id: int | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """تقرير الغائبين لحصص محددة — ALL_ABSENT (غائب في جميعها) أو ANY_ABSENT."""
    year = _active_year(school)
    context = get_or_create_attendance_day_context(
        school=school, attendance_date=attendance_date
    )
    sequences = _validate_sequences(sequences, context)
    periods_info = [
        {"sequence": p["sequence"], "name": p["name"]}
        for p in context.attendance_periods
        if p["sequence"] in sequences
    ]

    sections_qs = expected_sections_queryset(school=school, year=year)
    if grade_id:
        sections_qs = sections_qs.filter(grade_id=grade_id)
    if section_id:
        sections_qs = sections_qs.filter(id=section_id)
    sections = list(sections_qs)
    section_ids = [s.id for s in sections]

    sessions = list(
        AttendanceSession.objects.filter(
            school=school,
            attendance_date=attendance_date,
            period_sequence__in=sequences,
            section_id__in=section_ids,
        ).only("id", "section_id", "period_sequence", "status")
    )
    submitted_by_section: dict[int, set[int]] = {}
    in_progress_by_section: dict[int, set[int]] = {}
    submitted_session_ids = []
    for s in sessions:
        if s.status == AttendanceSessionStatus.SUBMITTED:
            submitted_by_section.setdefault(s.section_id, set()).add(s.period_sequence)
            submitted_session_ids.append(s.id)
        else:
            in_progress_by_section.setdefault(s.section_id, set()).add(s.period_sequence)

    wanted = set(sequences)
    complete_ids = {
        sid for sid, seqs in submitted_by_section.items() if wanted <= seqs
    }
    incomplete = []
    for section in sections:
        if section.id in complete_ids:
            continue
        missing = sorted(wanted - submitted_by_section.get(section.id, set()))
        reasons = []
        names = {p["sequence"]: p["name"] for p in context.attendance_periods}
        for seq in missing:
            if seq in in_progress_by_section.get(section.id, set()):
                reasons.append(f"{names[seq]}: بدأ التحضير ولم يعتمد")
            else:
                reasons.append(f"{names[seq]}: لم يتم التحضير")
        incomplete.append(
            {
                "section_id": section.id,
                "section_name": section.name,
                "grade_name": section.grade.name,
                "missing_sequences": missing,
                "reason": "، ".join(reasons),
            }
        )

    # جلسات الفصول المكتملة فقط — طلاب الفصل الناقص لا يدخلون النتيجة إطلاقًا
    complete_session_ids = [
        s.id
        for s in sessions
        if s.section_id in complete_ids and s.status == AttendanceSessionStatus.SUBMITTED
    ]
    absent_counts = (
        AttendanceMark.objects.filter(
            session_id__in=complete_session_ids, status=AttendanceMarkStatus.ABSENT
        )
        .values("student_id")
        .annotate(periods=Count("session__period_sequence", distinct=True))
    )
    if match == MATCH_ALL:
        matched_ids = [
            row["student_id"] for row in absent_counts if row["periods"] == len(sequences)
        ]
    else:
        matched_ids = [row["student_id"] for row in absent_counts]

    # علامات الطلاب المطابقين في الحصص المحددة (غياب/تأخر) — لبطاقات الحالة والفصل
    marks = list(
        AttendanceMark.objects.filter(
            session_id__in=complete_session_ids, student_id__in=matched_ids
        )
        .select_related("session__section__grade")
        .only(
            "student_id", "status",
            "session__period_sequence", "session__section__id",
            "session__section__name", "session__section__code",
            "session__section__grade__name", "session__section__grade__sequence",
        )
    )
    statuses_by_student: dict[int, dict[int, str]] = {}
    section_by_student: dict[int, object] = {}
    for mark in marks:
        statuses_by_student.setdefault(mark.student_id, {})[
            mark.session.period_sequence
        ] = mark.status
        section_by_student.setdefault(mark.student_id, mark.session.section)

    names = dict(
        Student.objects.filter(id__in=matched_ids).values_list("id", "full_name")
    )
    # مؤشر البصمة الصباحية (م8.5) — للمراجعة فقط: لا يغير الغياب ولا يعتمد عليه
    arrivals = _morning_arrivals(school, attendance_date, matched_ids)
    students = []
    for student_id in matched_ids:
        section = section_by_student.get(student_id)
        if section is None:
            continue
        statuses = statuses_by_student.get(student_id, {})
        students.append(
            {
                "student_id": student_id,
                "full_name": names.get(student_id, ""),
                "grade_name": section.grade.name,
                "section_name": section.name,
                "_sort": (section.grade.sequence, section.code, names.get(student_id, "")),
                "period_statuses": [
                    {"sequence": seq, "status": statuses.get(seq, "PRESENT")}
                    for seq in sequences
                ],
                "morning_arrival": arrivals.get(student_id),
            }
        )
    students.sort(key=lambda s: s["_sort"])
    for s in students:
        del s["_sort"]

    total = len(students)
    page_items, page_size = _paginate(students, page, page_size)
    return {
        "date": attendance_date.isoformat(),
        "periods": periods_info,
        "match": match,
        "summary": {
            "matching_students": total,
            "complete_sections": len(complete_ids),
            "incomplete_sections": len(incomplete),
        },
        "students": page_items,
        "incomplete_sections": incomplete,
        "day_periods": [
            {"sequence": p["sequence"], "name": p["name"]}
            for p in context.attendance_periods
        ],
        "page": max(page, 1),
        "page_size": page_size,
        "total_students": total,
    }


def get_daily_report(
    *,
    school,
    attendance_date: date_cls,
    status_filter: str | None = None,
    grade_id: int | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """ملخص اليوم من DailyAttendanceSummary — بلا عدادات مخبأة منفصلة."""
    _active_year(school)
    context = get_or_create_attendance_day_context(
        school=school, attendance_date=attendance_date
    )
    rows = DailyAttendanceSummary.objects.filter(
        school=school, attendance_date=attendance_date
    )
    if grade_id:
        rows = rows.filter(section__grade_id=grade_id)
    aggregates = rows.aggregate(
        total_rows=Count("id"),
        complete=Count("id", filter=Q(completeness_status=DailyCompleteness.COMPLETE)),
        full=Count("id", filter=Q(absence_status=DailyAbsenceStatus.FULL)),
        partial=Count("id", filter=Q(absence_status=DailyAbsenceStatus.PARTIAL)),
        none=Count("id", filter=Q(absence_status=DailyAbsenceStatus.NONE)),
        undetermined=Count(
            "id", filter=Q(absence_status=DailyAbsenceStatus.UNDETERMINED)
        ),
        late_students=Count("id", filter=Q(late_periods__gt=0)),
        late_occurrences=Sum("late_periods"),
        late_minutes=Sum("total_late_minutes"),
        # م10 — التصنيف الإداري للغياب (alias مختلف عن اسم العمود لتفادي التظليل)
        excused_periods_total=Sum("excused_absent_periods"),
        unexcused_periods_total=Sum("unexcused_absent_periods"),
    )
    enrollments = enrollments_on_date(school=school, on_date=attendance_date)
    if grade_id:
        enrollments = enrollments.filter(section__grade_id=grade_id)
    total_students = enrollments.values("student_id").distinct().count()
    # «غير مكتمل» يشمل من لا صف ملخص له أصلًا (فصله لم يعتمد أي حصة)
    incomplete_students = total_students - aggregates["complete"]

    students = []
    total_filtered = 0
    if status_filter:
        filtered = (
            rows.filter(absence_status=status_filter)
            .select_related("student", "section__grade")
            .order_by("section__grade__sequence", "section__code", "student__full_name")
        )
        rows_list = [
            {
                "student_id": r.student_id,
                "full_name": r.student.full_name,
                "grade_name": r.section.grade.name,
                "section_name": r.section.name,
                "absent_periods": r.absent_periods,
                "excused_absent_periods": r.excused_absent_periods,
                "unexcused_absent_periods": r.unexcused_absent_periods,
                "late_periods": r.late_periods,
                "total_late_minutes": r.total_late_minutes,
                "submitted_periods": r.submitted_periods,
                "expected_periods": r.expected_periods,
            }
            for r in filtered
        ]
        total_filtered = len(rows_list)
        students, page_size = _paginate(rows_list, page, page_size)

    return {
        "date": attendance_date.isoformat(),
        "is_school_day": context.schedule_snapshot.get("is_school_day", False),
        "expected_periods": len(context.attendance_periods),
        "day_periods": [
            {"sequence": p["sequence"], "name": p["name"]}
            for p in context.attendance_periods
        ],
        "summary": {
            "total_students": total_students,
            "complete_students": aggregates["complete"],
            "incomplete_students": max(incomplete_students, 0),
            "full_absent": aggregates["full"],
            "partial_absent": aggregates["partial"],
            "no_absence": aggregates["none"],
            "undetermined": aggregates["undetermined"],
            "late_students": aggregates["late_students"],
            "late_occurrences": aggregates["late_occurrences"] or 0,
            "late_minutes": aggregates["late_minutes"] or 0,
            "excused_absent_periods": aggregates["excused_periods_total"] or 0,
            "unexcused_absent_periods": aggregates["unexcused_periods_total"] or 0,
        },
        "students": students,
        "page": max(page, 1),
        "page_size": page_size,
        "total_students_filtered": total_filtered,
    }
