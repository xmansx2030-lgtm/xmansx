"""All of today's preparation periods, with fixed query count and no empty sessions."""

from datetime import time
from zoneinfo import ZoneInfo

from attendance.models import AttendanceSession
from attendance.selectors.monitoring import _membership_name, expected_sections_queryset
from attendance.services.admin_preparation import today_schedule
from attendance.services.sessions import _active_year
from attendance.services.timing import alert_at_for, overdue_minutes, session_alert_at
from schools.services.settings import get_or_create_settings


def get_today_preparation(*, school, now=None):
    year = _active_year(school)
    now, schedule, timezone = today_schedule(school, now)
    settings_obj = get_or_create_settings(school=school)
    sections = list(expected_sections_queryset(school=school, year=year))
    sessions = {
        (s.period_sequence, s.section_id): s
        for s in AttendanceSession.objects.filter(
            school=school, attendance_date=now.date()
        ).select_related(
            "started_by_membership__user",
            "started_by_membership__staff_profile",
            "submitted_by_membership__user",
            "submitted_by_membership__staff_profile",
        )
    }
    periods = []
    for period in schedule["periods"]:
        if not period["is_attendance_period"]:
            continue
        started = time.fromisoformat(period["start_time"]) <= now.time().replace(tzinfo=None)
        current = started and now.time().replace(tzinfo=None) < time.fromisoformat(
            period["end_time"]
        )
        rows = []
        for section in sections if started else []:
            session = sessions.get((period["sequence"], section.id))
            status = session.status if session else "NOT_STARTED"
            deadline = (
                session_alert_at(session)
                if session
                else alert_at_for(
                    day=now.date(),
                    start_time=time.fromisoformat(period["start_time"]),
                    alert_minutes=settings_obj.unprepared_period_alert_minutes,
                    tz_name=timezone,
                )
            )
            delay = overdue_minutes(
                deadline,
                session.submitted_at if status == "SUBMITTED" else now,
            )
            actor = None
            if session:
                actor = (
                    session.submitted_by_membership
                    if status == "SUBMITTED"
                    else (session.started_by_membership)
                )
            rows.append(
                {
                    "section_id": section.id,
                    "section_name": section.name,
                    "grade_id": section.grade_id,
                    "grade_name": section.grade.name,
                    "department": section.department,
                    "students_count": section.active_students,
                    "attendance_status": status,
                    "timeliness_status": "OVERDUE" if delay is not None else "ON_TIME",
                    "minutes_overdue": delay,
                    "teacher_name": _membership_name(actor),
                    "started_at": session.started_at.astimezone(ZoneInfo(timezone)).strftime(
                        "%H:%M"
                    )
                    if session
                    else None,
                    "submitted_at": session.submitted_at.astimezone(ZoneInfo(timezone)).strftime(
                        "%H:%M"
                    )
                    if session and session.submitted_at
                    else None,
                    "session_id": session.id if session else None,
                }
            )
        rows.sort(
            key=lambda r: (
                r["attendance_status"] == "SUBMITTED",
                r["timeliness_status"] != "OVERDUE",
                r["grade_name"],
                r["section_name"],
                r["department"],
            )
        )
        submitted = sum(r["attendance_status"] == "SUBMITTED" for r in rows)
        periods.append(
            {
                **period,
                "timezone": timezone,
                "state": "CURRENT" if current else "ENDED" if started else "UPCOMING",
                "summary": {
                    "total": len(sections),
                    "submitted": submitted,
                    "in_progress": sum(r["attendance_status"] == "IN_PROGRESS" for r in rows),
                    "not_started": sum(r["attendance_status"] == "NOT_STARTED" for r in rows),
                    "incomplete": len(rows) - submitted,
                    "overdue": sum(
                        r["attendance_status"] != "SUBMITTED"
                        and r["timeliness_status"] == "OVERDUE"
                        for r in rows
                    ),
                }
                if started
                else None,
                "sections": rows,
            }
        )
    return {
        "date": now.date().isoformat(),
        "school_time": now.isoformat(),
        "is_school_day": schedule["is_school_day"],
        "periods": periods,
    }
