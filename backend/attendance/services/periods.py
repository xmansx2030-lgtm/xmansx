"""تحديد الحصة الحالية — لا جدول معلمين: الحصة من الوقت والجدول المعين لليوم.

يقرأ: timezone المدرسة → يوم الأسبوع (SchoolWeekDay) → الجدول المعين لليوم →
BellPeriod التي يقع الوقت داخلها و is_attendance_period=True.
الفسحة أو خارج الدوام أو يوم غير دراسي → لا حصة حالية.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.utils import timezone as dj_timezone

from academics.models import BellPeriod, SchoolWeekDay
from schools.services.settings import get_or_create_settings

# الأحد=0 حسب Weekday choices (Python: Monday=0 → التحويل أدناه)
_PY_TO_SCHOOL_WEEKDAY = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6}


def school_now(school) -> datetime:
    """الوقت المحلي للمدرسة — timezone-aware دائمًا."""
    settings_obj = get_or_create_settings(school=school)
    return dj_timezone.now().astimezone(ZoneInfo(settings_obj.timezone))


def get_current_attendance_period(school, at: datetime | None = None):
    """يعيد (BellPeriod, local_date) للحصة الحالية أو (None, local_date)."""
    local_now = at if at is not None else school_now(school)
    local_date = local_now.date()
    school_weekday = _PY_TO_SCHOOL_WEEKDAY[local_now.weekday()]

    week_day = (
        SchoolWeekDay.objects.filter(school=school, weekday=school_weekday)
        .select_related("bell_schedule")
        .first()
    )
    if week_day is None or not week_day.is_school_day or week_day.bell_schedule_id is None:
        return None, local_date

    current_time: time = local_now.time()
    period = (
        BellPeriod.objects.filter(
            bell_schedule=week_day.bell_schedule,
            is_attendance_period=True,
            start_time__lte=current_time,
            end_time__gt=current_time,
        )
        .select_related("bell_schedule")
        .first()
    )
    return period, local_date


def build_period_snapshot(period: BellPeriod, attendance_date: date, tz_name: str) -> dict:
    """Snapshot كامل — المرجع التاريخي الوحيد (تعديل الجدول لاحقًا لا يمس الجلسات)."""
    return {
        "sequence": period.sequence,
        "name": period.name,
        "start_time": period.start_time.strftime("%H:%M"),
        "end_time": period.end_time.strftime("%H:%M"),
        "bell_schedule_id": period.bell_schedule_id,
        "bell_schedule_name": period.bell_schedule.name,
        "attendance_date": attendance_date.isoformat(),
        "timezone": tz_name,
    }
