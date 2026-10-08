"""Bounded family projections of existing attendance facts, never staff profiles."""

from collections import defaultdict
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db.models import Prefetch
from django.utils import timezone

from academics.models import AcademicYear, AcademicYearStatus
from attendance.models import (
    AttendanceDayContext,
    AttendanceMark,
    AttendanceSession,
    DailyAttendanceSummary,
)
from attendance.services.day_context import build_day_schedule_snapshot
from devices.models import SchoolArrival
from schools.models import SchoolSettings
from students.models import StudentEnrollment
from students.services.enrollments import enrollments_on_date

LABELS = {
    "NOT_STARTED": "لم تبدأ",
    "NOT_RECORDED": "لم يكتمل التسجيل",
    "IN_PROGRESS": "بانتظار اعتماد التحضير",
    "PRESENT": "حاضر",
    "ABSENT": "غائب",
}


def school_today(school):
    tz = SchoolSettings.objects.filter(school=school).values_list("timezone", flat=True).first()
    return timezone.now().astimezone(ZoneInfo(tz or "Asia/Riyadh")).date()


def child_header(relation, *, today=None):
    today = today or school_today(relation.school)
    enrollment = (
        enrollments_on_date(school=relation.school, on_date=today)
        .filter(
            student=relation.student,
            status="ACTIVE",
            academic_year__status=AcademicYearStatus.ACTIVE,
        )
        .select_related("grade", "section")
        .order_by("-enrolled_at", "-id")
        .first()
    )
    return {
        "relation_id": relation.id,
        "school": {"id": relation.school_id, "name": relation.school.name},
        "status": relation.status,
        "student": {
            "id": relation.student_id,
            "full_name": relation.student.full_name,
            "grade_name": enrollment.grade.name if enrollment else "",
            "section_name": enrollment.section.name if enrollment else "",
            "department": enrollment.section.department if enrollment else "",
        },
    }


def _school_years(school):
    return list(
        AcademicYear.objects.filter(school=school)
        .only("id", "start_date", "end_date", "status")
        .order_by("-start_date", "-id")
    )


def _year_on(day, *, today, years, summary=None, context=None, recorded_years=()):
    """Saved attendance owns its year; preparation never changes the current roster."""
    if summary is not None:
        return summary.academic_year_id
    if context is not None and context.academic_year_id is not None:
        return context.academic_year_id
    if day == today:
        active = next((year for year in years if year.status == AcademicYearStatus.ACTIVE), None)
        if active is not None:
            return active.id
    # A past transition day can still belong to the old recorded roster when
    # calendar activation was blocked. A prepared year must not hide those facts.
    if day < today and len(recorded_years) == 1:
        return next(iter(recorded_years))
    return next((year.id for year in years if year.start_date <= day <= year.end_date), None)


def morning_payload(arrival):
    if not arrival:
        return {
            "status": "NOT_RECORDED",
            "status_label": "لا يوجد سجل وصول",
            "arrival_time": None,
            "counted_late_minutes": 0,
            "updated_at": None,
        }
    return {
        "status": arrival.status,
        "status_label": arrival.get_status_display(),
        "arrival_time": arrival.first_arrival_at.isoformat(),
        "counted_late_minutes": arrival.counted_late_minutes,
        "updated_at": arrival.updated_at.isoformat(),
    }


def summary_payload(
    summary,
    day,
    *,
    expected=0,
    submitted=0,
    present=0,
    absent=0,
    excused=0,
    updated_at=None,
    expected_known=True,
):
    if summary:
        expected, submitted = summary.expected_periods, summary.submitted_periods
        present, absent = summary.present_periods, summary.absent_periods
        excused = summary.excused_absent_periods
        status, complete = summary.absence_status, summary.completeness_status
        updated_at = summary.calculated_at
    else:
        status = (
            "UNDETERMINED"
            if not submitted
            else "NONE"
            if not absent
            else "FULL"
            if absent == submitted
            else "PARTIAL"
        )
        complete = (
            "COMPLETE"
            if expected_known and expected > 0 and submitted >= expected
            else "INCOMPLETE"
        )
    label = {
        "UNDETERMINED": "لم يعتمد تحضير",
        "NONE": "حاضر",
        "PARTIAL": "غياب جزئي",
        "FULL": "غياب يوم كامل",
    }[status]
    if complete != "COMPLETE":
        label = "اليوم غير مكتمل" if not absent else "غياب مسجل — اليوم غير مكتمل"
    return {
        "date": day.isoformat(),
        "absence_status": status,
        "absence_status_label": label,
        "completeness_status": complete,
        "expected_periods": expected,
        "submitted_periods": submitted,
        "present_periods": present,
        "absent_periods": absent,
        "excused_absent_periods": excused,
        "unexcused_absent_periods": absent - excused,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


def child_day(relation, day=None):
    school, student = relation.school, relation.student
    today = school_today(school)
    day = day or today
    summary = DailyAttendanceSummary.objects.filter(
        school=school, student=student, attendance_date=day
    ).first()
    context = AttendanceDayContext.objects.filter(school=school, attendance_date=day).first()
    snapshot = (
        context.schedule_snapshot
        if context
        else (build_day_schedule_snapshot(school, day) if day == today else {"periods": []})
    )
    scheduled_count = sum(p.get("is_attendance_period", True) for p in snapshot.get("periods", []))
    periods = {
        p["sequence"]: p for p in snapshot.get("periods", []) if p.get("is_attendance_period", True)
    }
    enrollments = list(
        enrollments_on_date(school=school, on_date=day)
        .filter(student=student)
        .order_by("-enrolled_at", "-id")
    )
    own_pairs = {(enrollment.academic_year_id, enrollment.section_id) for enrollment in enrollments}
    if summary is not None:
        own_pairs.add((summary.academic_year_id, summary.section_id))
    candidates = (
        list(
            AttendanceSession.objects.filter(
                school=school,
                section_id__in={section_id for _, section_id in own_pairs},
                attendance_date=day,
            ).prefetch_related(
                Prefetch("marks", queryset=AttendanceMark.objects.filter(student=student))
            )
        )
        if own_pairs
        else []
    )
    candidates = [
        session
        for session in candidates
        if (session.academic_year_id, session.section_id) in own_pairs
    ]
    year_id = _year_on(
        day,
        today=today,
        years=_school_years(school),
        summary=summary,
        context=context,
        recorded_years={session.academic_year_id for session in candidates},
    )
    enrollment = next((item for item in enrollments if item.academic_year_id == year_id), None)
    section_id = summary.section_id if summary else enrollment.section_id if enrollment else None
    sessions = [
        session
        for session in candidates
        if session.academic_year_id == year_id and session.section_id == section_id
    ]
    sessions_by_period = {s.period_sequence: s for s in sessions}
    for session in sessions:
        periods.setdefault(session.period_sequence, session.bell_period_snapshot)
    tz_name = (
        context.timezone_snapshot
        if context
        else (
            SchoolSettings.objects.filter(school=school).values_list("timezone", flat=True).first()
            or "Asia/Riyadh"
        )
    )
    now = timezone.now().astimezone(ZoneInfo(tz_name))
    from excuses.selectors import excused_session_ids

    excused_ids = excused_session_ids(school=school, student=student, attendance_date=day)
    rows = []
    for sequence, period in sorted(periods.items()):
        session = sessions_by_period.get(sequence)
        source = session.bell_period_snapshot if session else period
        start = source.get("start_time", source.get("start"))
        end = source.get("end_time", source.get("end"))
        if session and session.status == "SUBMITTED":
            status = (
                "ABSENT"
                if any(mark.student_id == student.id for mark in session.marks.all())
                else "PRESENT"
            )
        elif session:
            status = "IN_PROGRESS"
        elif day > today or (day == today and start and now.strftime("%H:%M") < start[:5]):
            status = "NOT_STARTED"
        else:
            status = "NOT_RECORDED"
        rows.append(
            {
                "sequence": sequence,
                "period_sequence": sequence,
                "name": source.get("name", period.get("name", f"الحصة {sequence}")),
                "start_time": start,
                "end_time": end,
                "status": status,
                "status_label": LABELS[status],
                "attendance_date": day.isoformat(),
                "session_id": session.id if session else None,
                "updated_at": session.updated_at.isoformat() if session else None,
                "excused": bool(session and status == "ABSENT" and session.id in excused_ids),
            }
        )
    submitted = sum(r["status"] in {"PRESENT", "ABSENT"} for r in rows)
    absent = sum(r["status"] == "ABSENT" for r in rows)
    excused = sum(r["excused"] for r in rows)
    # Live detail derives submitted facts; history relies existing stored summaries.
    daily = summary_payload(
        None,
        day,
        expected=max(scheduled_count, summary.expected_periods if summary else 0, len(periods)),
        expected_known=bool(scheduled_count or (summary and summary.expected_periods)),
        submitted=submitted,
        present=submitted - absent,
        absent=absent,
        excused=excused,
        updated_at=max((s.updated_at for s in sessions), default=None),
    )
    return {
        "child": child_header(relation, today=today),
        "today": daily,
        "periods": rows,
        "morning": morning_payload(
            SchoolArrival.objects.filter(
                school=school, student=student, attendance_date=day
            ).first()
        ),
    }


def child_history(relation, *, from_date=None, to_date=None):
    today = school_today(relation.school)
    to_date = to_date or today
    from_date = from_date or to_date - timedelta(days=29)
    from students.services.attendance_profile import validate_profile_range

    try:
        validate_profile_range(from_date, to_date)
    except ValueError as exc:
        from common.errors import ApiError

        raise ApiError(str(exc), "الفترة غير صالحة؛ الحد الأقصى 366 يوماً.") from exc
    summaries = list(
        DailyAttendanceSummary.objects.filter(
            school=relation.school,
            student=relation.student,
            attendance_date__range=(from_date, to_date),
        )
    )
    arrivals = {
        a.attendance_date: a
        for a in SchoolArrival.objects.filter(
            school=relation.school,
            student=relation.student,
            attendance_date__range=(from_date, to_date),
        )
    }
    by_date = {s.attendance_date: s for s in summaries}
    years = _school_years(relation.school)
    enrollments = list(
        StudentEnrollment.objects.filter(
            school=relation.school,
            student=relation.student,
            enrolled_at__lte=to_date,
        ).order_by("-enrolled_at", "-id")
    )

    all_contexts = {
        c.attendance_date: c
        for c in AttendanceDayContext.objects.filter(
            school=relation.school,
            attendance_date__range=(from_date, to_date),
        )
    }

    # One batch covers the student's retained sections. Year/section/date matching
    # prevents another roster's implicit PRESENT rows from becoming this student's facts.
    candidates = list(
        AttendanceSession.objects.filter(
            school=relation.school,
            section_id__in={e.section_id for e in enrollments} | {s.section_id for s in summaries},
            attendance_date__range=(from_date, to_date),
        ).prefetch_related(
            Prefetch("marks", queryset=AttendanceMark.objects.filter(student=relation.student))
        )
    )
    recorded_years = defaultdict(set)
    for session in candidates:
        summary = by_date.get(session.attendance_date)
        saved_pair = (summary.academic_year_id, summary.section_id) if summary else None
        pair = (session.academic_year_id, session.section_id)
        if pair == saved_pair or any(
            (e.academic_year_id, e.section_id) == pair
            and e.enrolled_at <= session.attendance_date
            and (e.ended_at is None or e.ended_at > session.attendance_date)
            for e in enrollments
        ):
            recorded_years[session.attendance_date].add(session.academic_year_id)

    def year_on(day):
        return _year_on(
            day,
            today=today,
            years=years,
            summary=by_date.get(day),
            context=all_contexts.get(day),
            recorded_years=recorded_years[day],
        )

    def section_on(day):
        if day in by_date:
            return by_date[day].section_id
        year_id = year_on(day)
        return next(
            (
                e.section_id
                for e in enrollments
                if e.academic_year_id == year_id
                and e.enrolled_at <= day
                and (e.ended_at is None or e.ended_at > day)
            ),
            None,
        )

    contexts = {
        day: context for day, context in all_contexts.items() if section_on(day) is not None
    }
    # Missing cached summaries must not hide submitted facts or unfinished days.
    # Batch the student's dated sections and own marks; history performs no writes.
    sessions_by_date = defaultdict(list)
    for session in candidates:
        if session.section_id == section_on(
            session.attendance_date
        ) and session.academic_year_id == year_on(session.attendance_date):
            sessions_by_date[session.attendance_date].append(session)
    dates = sorted(
        set(by_date) | set(arrivals) | set(contexts) | set(sessions_by_date), reverse=True
    )
    rows = []
    from excuses.models import AbsenceExcuseCoverage, ExcuseCoverageStatus

    covered_ids = set(
        AbsenceExcuseCoverage.objects.filter(
            school=relation.school,
            student=relation.student,
            attendance_date__range=(from_date, to_date),
            status=ExcuseCoverageStatus.ACTIVE,
        ).values_list("attendance_session_id", flat=True)
    )
    for day in dates:
        summary = by_date.get(day)
        if summary:
            daily = summary_payload(summary, day)
        else:
            sessions = sessions_by_date.get(day, [])
            submitted_sessions = [s for s in sessions if s.status == "SUBMITTED"]
            absent_sessions = [s for s in submitted_sessions if list(s.marks.all())]
            context = contexts.get(day)
            expected = (
                sum(
                    p.get("is_attendance_period", True)
                    for p in context.schedule_snapshot.get("periods", [])
                )
                if context
                else 0
            )
            daily = summary_payload(
                None,
                day,
                expected=max(expected, len(sessions)),
                expected_known=bool(expected),
                submitted=len(submitted_sessions),
                absent=len(absent_sessions),
                present=len(submitted_sessions) - len(absent_sessions),
                excused=sum(s.id in covered_ids for s in absent_sessions),
                updated_at=max((s.updated_at for s in sessions), default=None),
            )
        rows.append({**daily, "morning": morning_payload(arrivals.get(day))})
    total = {
        "full_absence_days": sum(
            r["absence_status"] == "FULL" and r["completeness_status"] == "COMPLETE" for r in rows
        ),
        "partial_absence_days": sum(r["absence_status"] == "PARTIAL" for r in rows),
        "incomplete_days": sum(r["completeness_status"] != "COMPLETE" for r in rows),
        "present_periods": sum(r["present_periods"] for r in rows),
        "absent_periods": sum(r["absent_periods"] for r in rows),
        "excused_absent_periods": sum(r["excused_absent_periods"] for r in rows),
        "unexcused_absent_periods": sum(r["unexcused_absent_periods"] for r in rows),
        "morning_late_days": sum(a.counted_late_minutes > 0 for a in arrivals.values()),
        "counted_late_minutes": sum(a.counted_late_minutes for a in arrivals.values()),
    }
    return {
        "results": rows,
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "summary": total,
    }
