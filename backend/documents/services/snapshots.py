"""بناء لقطات المستندات (م12) — الخادم مصدر الحقيقة الوحيد (البندان 91-92).

كل دالة هنا تعيد `dict` قابلًا للتخزين JSON يكفي وحده لرسم المستند لاحقًا:
لا استعلام إضافي وقت الرسم، ولا قراءة لبيانات الطالب الحالية عند إعادة المحاولة
(البند 67). مستندات الإنذار **لا تعيد الحساب إطلاقًا** — مصدرها لقطة م11 (البند 30).
"""

from datetime import date, timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone as dj_timezone

from attendance.models import (
    AttendanceMark,
    AttendanceMarkStatus,
    DailyAbsenceStatus,
    DailyAttendanceSummary,
)
from common.errors import ApiError
from devices.models import ArrivalSource, ArrivalStatus, SchoolArrival
from documents.models import DocumentType
from student_actions.models import StudentAction, StudentActionStatus, StudentActionType
from student_warnings.models import (
    StudentWarning,
    WarningLevel,
    WarningRuleType,
    WarningStatus,
)

MAX_REPORT_DAYS = 366
# حارس حجم مضبوط بالقياس: الرسم يكلف ~250ms لكل صفحة A4، و500 صف ≈ 20 صفحة ≈ 5 ثوانٍ.
# ما فوق ذلك يقسم على فترات بدل حجز عامل خادم دقائق (انظر GENERATED_DOCUMENTS.md).
MAX_REPORT_ROWS = 500

DAY_STATUS_LABELS = {
    DailyAbsenceStatus.FULL: "غياب يوم كامل",
    DailyAbsenceStatus.PARTIAL: "غياب جزئي",
    DailyAbsenceStatus.UNDETERMINED: "بيانات التحضير غير مكتملة",
    DailyAbsenceStatus.NONE: "لا يوجد غياب",
}
CLASSIFICATION_LABELS = {
    "EXCUSED": "بعذر",
    "UNEXCUSED": "بدون عذر",
    "MIXED": "مختلط (بعذر وبدون عذر)",
    "UNDETERMINED": "غير محسوم",
    "NONE": "—",
}
ARRIVAL_SOURCE_LABELS = dict(ArrivalSource.choices)
WARNING_TYPE_LABELS = dict(WarningRuleType.choices)
WARNING_LEVEL_LABELS = dict(WarningLevel.choices)
ACTION_TYPE_LABELS = dict(StudentActionType.choices)

WEEKDAY_NAMES = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]


def format_minutes(total: int) -> str:
    """‏137 دقيقة → «ساعتان و17 دقيقة» بصيغة مبسطة تصلح للطباعة."""
    hours, minutes = divmod(int(total or 0), 60)
    if hours and minutes:
        return f"{hours} ساعة و{minutes} دقيقة"
    if hours:
        return f"{hours} ساعة"
    return f"{minutes} دقيقة"


def _membership_name(membership) -> str:
    if membership is None:
        return ""
    profile = getattr(membership, "staff_profile", None)
    return profile.display_name if profile else membership.user.display_name


def school_header(school) -> dict:
    """ترويسة الطباعة من إعدادات المدرسة — لا من المستخدم الحالي (البند 80)."""
    settings_row = getattr(school, "settings", None)
    return {
        "name": school.name,
        "ministry_school_number": getattr(settings_row, "ministry_school_number", "") or "",
        "city": getattr(settings_row, "city", "") or "",
        "principal_name": getattr(settings_row, "official_principal_name", "") or "",
    }


def _current_placement(student) -> dict:
    enrollment = (
        student.enrollments.select_related("grade", "section").order_by("-enrolled_at").first()
    )
    return {
        "id": student.id,
        "name": student.full_name,
        "grade": enrollment.grade.name if enrollment else "",
        "section": enrollment.section.name if enrollment else "",
        "student_number": student.student_number or "",
        # مقنّع فقط — لا رقم هوية صريح في أي مستند (البند 19)
        "national_id_masked": student.national_id_masked,
    }


def validate_range(from_date: date, to_date: date) -> None:
    if from_date > to_date:
        raise ApiError(
            "INVALID_REPORT_DATE_RANGE", "تاريخ البداية بعد تاريخ النهاية.", status_code=400
        )
    if (to_date - from_date).days + 1 > MAX_REPORT_DAYS:
        raise ApiError(
            "INVALID_REPORT_DATE_RANGE",
            "المدة المطلوبة أطول من عام دراسي واحد.",
            status_code=400,
        )


def _now_iso() -> str:
    return dj_timezone.localtime().isoformat(timespec="minutes")


def _base(*, school, student, membership, title: str, extra: dict) -> dict:
    return {
        "title": title,
        "school": school_header(school),
        "student": _current_placement(student),
        "generated_at": _now_iso(),
        "generated_by": _membership_name(membership),
        **extra,
    }


# ---------------------------------------------------------------- الإنذارات


def warning_snapshot(*, school, warning: StudentWarning, membership, title: str) -> dict:
    """من لقطة الإنذار وحدها — ولا استعلام واحد عن مقاييس اليوم (البندان 29-30)."""
    return {
        "title": title,
        "school": school_header(school),
        "student": {
            "id": warning.student_id,
            # الصف/الفصل/الاسم كما كانت لحظة الإصدار لا كما هي اليوم (البنود 106-107)
            "name": warning.student_name_snapshot,
            "grade": warning.grade_name_snapshot,
            "section": warning.section_name_snapshot,
            "national_id_masked": warning.national_id_masked_snapshot,
            "student_number": "",
        },
        "generated_at": _now_iso(),
        "generated_by": _membership_name(membership),
        "warning": {
            "id": warning.id,
            "type": warning.warning_type,
            "type_label": WARNING_TYPE_LABELS.get(warning.warning_type, warning.warning_type),
            "level": warning.level,
            "level_label": WARNING_LEVEL_LABELS.get(warning.level, warning.level),
            "threshold_at_issue": warning.threshold_at_issue,
            "metric_value_at_issue": warning.metric_value_at_issue,
            "unit": "يوم" if warning.warning_type == WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE
            else "مرة",
            "issued_at": warning.issued_at.date().isoformat(),
            "issued_by": _membership_name(warning.issued_by_membership),
            "academic_year": warning.academic_year.name,
            "notes": warning.notes,
            "reference": f"W-{warning.id:06d}",
        },
        # صفوف النوع نفسه فقط، جُمّدت وقت الإصدار في م11.
        "detail_rows": warning.detail_rows_snapshot or [],
        "metrics_at_issue": {
            "full_absence_days": warning.full_absence_days_at_issue,
            "unexcused_full_absence_days": warning.unexcused_full_absence_days_at_issue,
            "excused_full_absence_days": warning.excused_full_absence_days_at_issue,
            "absent_periods": warning.absent_periods_at_issue,
            "unexcused_absent_periods": warning.unexcused_absent_periods_at_issue,
            # عدادان منفصلان — لا يجمعان أبدًا (البند 113)
            "morning_late_occurrences": warning.morning_late_occurrences_at_issue,
            "morning_late_minutes": warning.morning_late_minutes_at_issue,
            "morning_late_duration": format_minutes(warning.morning_late_minutes_at_issue),
            "period_late_occurrences": warning.period_late_occurrences_at_issue,
            "period_late_minutes": warning.period_late_minutes_at_issue,
            "period_late_duration": format_minutes(warning.period_late_minutes_at_issue),
        },
    }


# ---------------------------------------------------------------- التعهد


def commitment_snapshot(*, school, student, membership, from_date: date, to_date: date) -> dict:
    validate_range(from_date, to_date)
    rows = DailyAttendanceSummary.objects.filter(
        school=school, student=student, attendance_date__range=(from_date, to_date)
    )
    full = Q(absence_status=DailyAbsenceStatus.FULL)
    totals = rows.aggregate(
        full_days=Count("id", filter=full),
        unexcused_full_days=Count(
            "id", filter=full & Q(excused_absent_periods=0, unexcused_absent_periods__gt=0)
        ),
        excused_full_days=Count(
            "id", filter=full & Q(unexcused_absent_periods=0, excused_absent_periods__gt=0)
        ),
        absent_periods=Sum("absent_periods"),
        unexcused_periods=Sum("unexcused_absent_periods"),
    )
    return _base(
        school=school,
        student=student,
        membership=membership,
        title="تعهد الالتزام بالحضور والمواظبة",
        extra={
            "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
            "metrics": {
                "full_absence_days": totals["full_days"] or 0,
                "unexcused_full_absence_days": totals["unexcused_full_days"] or 0,
                "excused_full_absence_days": totals["excused_full_days"] or 0,
                "absent_periods": totals["absent_periods"] or 0,
                "unexcused_absent_periods": totals["unexcused_periods"] or 0,
            },
        },
    )


# ---------------------------------------------------------------- كشف الغياب


def _classification(row) -> str:
    if row.absence_status == DailyAbsenceStatus.UNDETERMINED:
        return "UNDETERMINED"
    if row.excused_absent_periods and row.unexcused_absent_periods:
        return "MIXED"
    if row.excused_absent_periods:
        return "EXCUSED"
    if row.unexcused_absent_periods:
        return "UNEXCUSED"
    return "NONE"


def absence_report_snapshot(*, school, student, membership, from_date: date, to_date: date) -> dict:
    validate_range(from_date, to_date)
    queryset = (
        DailyAttendanceSummary.objects.filter(
            school=school, student=student, attendance_date__range=(from_date, to_date)
        )
        .exclude(absence_status=DailyAbsenceStatus.NONE)
        .select_related("section")
        .order_by("attendance_date")[:MAX_REPORT_ROWS]
    )
    rows = []
    totals = {
        "full_absence_days": 0,
        "partial_absence_days": 0,
        "undetermined_days": 0,
        "absent_periods": 0,
        "excused_absent_periods": 0,
        "unexcused_absent_periods": 0,
    }
    for row in queryset:
        classification = _classification(row)
        rows.append(
            {
                "date": row.attendance_date.isoformat(),
                "weekday": WEEKDAY_NAMES[row.attendance_date.weekday()],
                "day_status": row.absence_status,
                "day_status_label": DAY_STATUS_LABELS.get(row.absence_status, row.absence_status),
                "absent_periods": row.absent_periods,
                "excused_absent_periods": row.excused_absent_periods,
                "unexcused_absent_periods": row.unexcused_absent_periods,
                "classification": classification,
                "classification_label": CLASSIFICATION_LABELS[classification],
                "section": row.section.name if row.section_id else "",
            }
        )
        if row.absence_status == DailyAbsenceStatus.FULL:
            totals["full_absence_days"] += 1
        elif row.absence_status == DailyAbsenceStatus.PARTIAL:
            totals["partial_absence_days"] += 1
        elif row.absence_status == DailyAbsenceStatus.UNDETERMINED:
            totals["undetermined_days"] += 1
        totals["absent_periods"] += row.absent_periods
        totals["excused_absent_periods"] += row.excused_absent_periods
        totals["unexcused_absent_periods"] += row.unexcused_absent_periods

    return _base(
        school=school,
        student=student,
        membership=membership,
        title="كشف تفصيلي للغياب",
        extra={
            "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
            "rows": rows,
            "totals": totals,
            "truncated": len(rows) >= MAX_REPORT_ROWS,
        },
    )


# ---------------------------------------------------------------- التأخر الصباحي


def morning_late_snapshot(*, school, student, membership, from_date: date, to_date: date) -> dict:
    """مصدره `SchoolArrival` وحده — تأخر الحصص لا يدخله إطلاقًا (البند 40)."""
    validate_range(from_date, to_date)
    arrivals = SchoolArrival.objects.filter(
        school=school,
        student=student,
        status=ArrivalStatus.LATE,
        attendance_date__range=(from_date, to_date),
    ).order_by("attendance_date")[:MAX_REPORT_ROWS]
    rows = []
    occurrences = 0
    raw_minutes = 0
    counted_minutes = 0
    for arrival in arrivals:
        local_arrival = dj_timezone.localtime(arrival.first_arrival_at)
        rows.append(
            {
                "date": arrival.attendance_date.isoformat(),
                "weekday": WEEKDAY_NAMES[arrival.attendance_date.weekday()],
                "arrival_time": local_arrival.strftime("%H:%M"),
                "raw_late_minutes": arrival.raw_late_minutes,
                "counted_late_minutes": arrival.counted_late_minutes,
                "source": arrival.source,
                "source_label": ARRIVAL_SOURCE_LABELS.get(arrival.source, arrival.source),
            }
        )
        occurrences += 1
        raw_minutes += arrival.raw_late_minutes
        counted_minutes += arrival.counted_late_minutes

    return _base(
        school=school,
        student=student,
        membership=membership,
        title="كشف تفصيلي للتأخر عن الدوام الصباحي",
        extra={
            "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
            "rows": rows,
            "totals": {
                "occurrences": occurrences,
                "raw_late_minutes": raw_minutes,
                "counted_late_minutes": counted_minutes,
                "duration": format_minutes(counted_minutes),
            },
            "truncated": len(rows) >= MAX_REPORT_ROWS,
        },
    )


# ---------------------------------------------------------------- تأخر الحصص


def period_late_snapshot(*, school, student, membership, from_date: date, to_date: date) -> dict:
    """مصدره `AttendanceMark.LATE` — مستقل تمامًا عن التأخر الصباحي (البند 41)."""
    validate_range(from_date, to_date)
    marks = (
        AttendanceMark.objects.filter(
            school=school,
            student=student,
            status=AttendanceMarkStatus.LATE,
            session__attendance_date__range=(from_date, to_date),
        )
        .select_related("session")
        .order_by("session__attendance_date", "session__period_sequence")[:MAX_REPORT_ROWS]
    )
    rows = []
    minutes = 0
    for mark in marks:
        rows.append(
            {
                "date": mark.session.attendance_date.isoformat(),
                "weekday": WEEKDAY_NAMES[mark.session.attendance_date.weekday()],
                "period_sequence": mark.session.period_sequence,
                "period_name": (mark.session.bell_period_snapshot or {}).get("name", ""),
                "arrival_time": mark.arrival_time.strftime("%H:%M") if mark.arrival_time else "",
                "late_minutes": mark.late_minutes or 0,
            }
        )
        minutes += mark.late_minutes or 0

    return _base(
        school=school,
        student=student,
        membership=membership,
        title="كشف تفصيلي لتأخر الحصص",
        extra={
            "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
            "rows": rows,
            "totals": {
                "occurrences": len(rows),
                "late_minutes": minutes,
                "duration": format_minutes(minutes),
            },
            "truncated": len(rows) >= MAX_REPORT_ROWS,
        },
    )


# ---------------------------------------------------------------- تقرير المواظبة


def attendance_report_snapshot(
    *, school, student, membership, from_date: date, to_date: date
) -> dict:
    """يجمع كل المقاييس + الإنذارات + الإجراءات؛ **بلا أي بيانات إرشاد** (البند 45)."""
    validate_range(from_date, to_date)
    from students.services.attendance_profile import get_profile_summary

    summary = get_profile_summary(
        school=school, student=student, from_date=from_date, to_date=to_date
    )
    arrivals = SchoolArrival.objects.filter(
        school=school,
        student=student,
        status=ArrivalStatus.LATE,
        attendance_date__range=(from_date, to_date),
    ).aggregate(occurrences=Count("id"), minutes=Sum("counted_late_minutes"))

    warnings = [
        {
            "level_label": WARNING_LEVEL_LABELS.get(w.level, w.level),
            "type_label": WARNING_TYPE_LABELS.get(w.warning_type, w.warning_type),
            "issued_at": w.issued_at.date().isoformat(),
            "metric_value_at_issue": w.metric_value_at_issue,
            "threshold_at_issue": w.threshold_at_issue,
            "status_label": "صادر" if w.status == WarningStatus.ISSUED else "ملغى",
        }
        for w in StudentWarning.objects.filter(school=school, student=student).order_by("issued_at")
    ]
    actions = [
        {
            "performed_at": a.performed_at.date().isoformat(),
            "type_label": ACTION_TYPE_LABELS.get(a.action_type, a.action_type),
            "performed_by": _membership_name(a.performed_by_membership),
            "notes": a.notes,
            "status_label": "منفذ" if a.status == StudentActionStatus.COMPLETED else "ملغى",
        }
        for a in StudentAction.objects.filter(school=school, student=student)
        .select_related("performed_by_membership__staff_profile", "performed_by_membership__user")
        .order_by("performed_at")
    ]

    return _base(
        school=school,
        student=student,
        membership=membership,
        title="تقرير مواظبة الطالب",
        extra={
            "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
            "summary": {
                **summary,
                # الصباحي منفصل عن تأخر الحصص في العرض والحساب معًا
                "morning_late_occurrences": arrivals["occurrences"] or 0,
                "morning_late_minutes": arrivals["minutes"] or 0,
                "morning_late_duration": format_minutes(arrivals["minutes"] or 0),
                "period_late_duration": format_minutes(summary["period_late_minutes"]),
            },
            "warnings": warnings,
            "actions": actions,
        },
    )


def default_range(school) -> tuple[date, date]:
    """العام الدراسي النشط، أو آخر 90 يومًا إن لم يوجد — يوثق في المستند دائمًا."""
    from student_warnings.selectors.eligibility import active_year

    try:
        year = active_year(school)
    except ApiError:
        today = date.today()
        return today - timedelta(days=90), today
    return year.start_date, min(year.end_date, date.today())


BUILDERS = {
    DocumentType.ATTENDANCE_COMMITMENT: commitment_snapshot,
    DocumentType.ABSENCE_DETAIL_REPORT: absence_report_snapshot,
    DocumentType.MORNING_LATE_DETAIL_REPORT: morning_late_snapshot,
    DocumentType.PERIOD_LATE_DETAIL_REPORT: period_late_snapshot,
    DocumentType.STUDENT_ATTENDANCE_REPORT: attendance_report_snapshot,
}
