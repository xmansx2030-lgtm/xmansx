"""سياق يوم الحضور (م8) — تجميد جدول اليوم لتحليل تاريخي لا يتأثر بتعديل الجدول.

ينشأ lazy عند أول نشاط حضور. ويمكن مواءمة اللقطة مع الجدول الحي قبل إنشاء أول
جلسة تحضير فقط؛ بعد وجود أي جلسة تصبح اللقطة تاريخية غير قابلة للتغيير.
"""

from datetime import date

from django.db import IntegrityError

from academics.models import (
    AcademicYear,
    AcademicYearStatus,
    BellPeriod,
    SchoolWeekDay,
)
from attendance.models import AttendanceDayContext
from attendance.services.periods import _PY_TO_SCHOOL_WEEKDAY
from schools.services.settings import get_or_create_settings


def build_day_schedule_snapshot(school, attendance_date: date) -> dict:
    """‏snapshot جدول اليوم من الجدول الحي — يستدعى مرة واحدة وقت الإنشاء فقط."""
    school_weekday = _PY_TO_SCHOOL_WEEKDAY[attendance_date.weekday()]
    week_day = (
        SchoolWeekDay.objects.filter(school=school, weekday=school_weekday)
        .select_related("bell_schedule")
        .first()
    )
    if week_day is None or not week_day.is_school_day or week_day.bell_schedule_id is None:
        return {"schedule_name": None, "is_school_day": False, "periods": []}

    periods = BellPeriod.objects.filter(bell_schedule=week_day.bell_schedule).order_by("sequence")
    return {
        "schedule_name": week_day.bell_schedule.name,
        "is_school_day": True,
        "periods": [
            {
                "sequence": p.sequence,
                "name": p.name,
                "start_time": p.start_time.strftime("%H:%M"),
                "end_time": p.end_time.strftime("%H:%M"),
                "is_attendance_period": p.is_attendance_period,
            }
            for p in periods
        ],
    }


def get_or_create_attendance_day_context(*, school, attendance_date: date) -> AttendanceDayContext:
    existing = AttendanceDayContext.objects.filter(
        school=school, attendance_date=attendance_date
    ).first()
    if existing is not None:
        return existing

    settings_obj = get_or_create_settings(school=school)
    year = AcademicYear.objects.filter(school=school, status=AcademicYearStatus.ACTIVE).first()
    try:
        return AttendanceDayContext.objects.create(
            school=school,
            academic_year=year,
            attendance_date=attendance_date,
            schedule_snapshot=build_day_schedule_snapshot(school, attendance_date),
            timezone_snapshot=settings_obj.timezone,
        )
    except IntegrityError:
        # سباق إنشاء متزامن — القيد الفريد حكم، والصف الفائز هو المرجع
        return AttendanceDayContext.objects.get(school=school, attendance_date=attendance_date)


def get_or_refresh_pristine_day_context(*, school, attendance_date: date) -> AttendanceDayContext:
    """حدّث سياقًا سبق أن أنشأته شاشة قراءة، ما دام التحضير لم يبدأ بعد."""
    context = get_or_create_attendance_day_context(school=school, attendance_date=attendance_date)
    from attendance.models import AttendanceSession

    if AttendanceSession.objects.filter(school=school, attendance_date=attendance_date).exists():
        return context

    current_snapshot = build_day_schedule_snapshot(school, attendance_date)
    if context.schedule_snapshot != current_snapshot:
        context.schedule_snapshot = current_snapshot
        context.save(update_fields=["schedule_snapshot", "updated_at"])
    return context
