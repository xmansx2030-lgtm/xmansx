"""Explicit, same-day administrative preparation using the frozen school-day schedule."""

from datetime import time

from attendance.models import AttendanceDayContext, AttendanceSession
from attendance.services.day_context import build_day_schedule_snapshot
from attendance.services.periods import school_now
from common.errors import ApiError
from schools.services.settings import get_or_create_settings


def today_schedule(school, now=None):
    now = now or school_now(school)
    context = AttendanceDayContext.objects.filter(
        school=school,
        attendance_date=now.date(),
    ).first()
    frozen = (
        context is not None
        and AttendanceSession.objects.filter(
            school=school,
            attendance_date=now.date(),
        ).exists()
    )
    snapshot = (
        context.schedule_snapshot if frozen else build_day_schedule_snapshot(school, now.date())
    )
    timezone = (
        context.timezone_snapshot if frozen else get_or_create_settings(school=school).timezone
    )
    return now, snapshot, timezone


def resolve_today_period(*, school, attendance_date, period_sequence):
    now, schedule, timezone = today_schedule(school)
    if attendance_date != now.date():
        raise ApiError(
            "ADMIN_ATTENDANCE_TODAY_ONLY",
            "التحضير الإداري متاح لحصص اليوم فقط.",
            status_code=409,
        )
    period = next(
        (
            p
            for p in schedule["periods"]
            if (p["sequence"] == period_sequence and p["is_attendance_period"])
        ),
        None,
    )
    if not schedule["is_school_day"] or period is None:
        raise ApiError("INVALID_PERIOD_SELECTION", "هذه الحصة غير متاحة لتحضير اليوم.")
    if time.fromisoformat(period["start_time"]) > now.time().replace(tzinfo=None):
        raise ApiError(
            "ATTENDANCE_PERIOD_NOT_STARTED",
            "لم يبدأ وقت هذه الحصة بعد.",
            status_code=409,
        )
    return {
        **period,
        "attendance_date": attendance_date.isoformat(),
        "timezone": timezone,
        "bell_schedule_id": schedule.get("bell_schedule_id"),
        "bell_schedule_name": schedule["schedule_name"],
    }
