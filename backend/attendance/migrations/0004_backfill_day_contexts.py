# توليد يدوي (م8): سياقات أيام للجلسات القائمة (بيئة تطوير/اختبار فقط — لا إنتاج بعد).
# يبنى snapshot من جدول اليوم الحالي لكل (مدرسة، تاريخ) — أفضل تقريب متاح، إذ لا
# يملك النظام snapshot يوم كامل قبل م8 (جلسات م6 تحمل snapshot حصتها فقط).
# الافتراض موثق في docs/ATTENDANCE_ANALYTICS.md.

from django.db import migrations

_PY_TO_SCHOOL_WEEKDAY = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6}


def _build_snapshot(apps, school_id, attendance_date):
    SchoolWeekDay = apps.get_model("academics", "SchoolWeekDay")
    BellPeriod = apps.get_model("academics", "BellPeriod")
    week_day = (
        SchoolWeekDay.objects.filter(
            school_id=school_id,
            weekday=_PY_TO_SCHOOL_WEEKDAY[attendance_date.weekday()],
        )
        .select_related("bell_schedule")
        .first()
    )
    if week_day is None or not week_day.is_school_day or week_day.bell_schedule_id is None:
        return {"schedule_name": None, "is_school_day": False, "periods": []}
    periods = BellPeriod.objects.filter(bell_schedule_id=week_day.bell_schedule_id).order_by(
        "sequence"
    )
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


def backfill(apps, schema_editor):
    AttendanceSession = apps.get_model("attendance", "AttendanceSession")
    AttendanceDayContext = apps.get_model("attendance", "AttendanceDayContext")
    SchoolSettings = apps.get_model("schools", "SchoolSettings")
    AcademicYear = apps.get_model("academics", "AcademicYear")

    tz_by_school = dict(SchoolSettings.objects.values_list("school_id", "timezone"))
    year_by_school = dict(
        AcademicYear.objects.filter(status="ACTIVE").values_list("school_id", "id")
    )
    pairs = (
        AttendanceSession.objects.values_list("school_id", "attendance_date")
        .distinct()
        .order_by()
    )
    existing = set(
        AttendanceDayContext.objects.values_list("school_id", "attendance_date")
    )
    for school_id, attendance_date in pairs:
        if (school_id, attendance_date) in existing:
            continue
        AttendanceDayContext.objects.create(
            school_id=school_id,
            academic_year_id=year_by_school.get(school_id),
            attendance_date=attendance_date,
            schedule_snapshot=_build_snapshot(apps, school_id, attendance_date),
            timezone_snapshot=tz_by_school.get(school_id, "Asia/Riyadh"),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0003_analytics_models"),
        ("academics", "0001_initial"),
        ("schools", "0002_schoolsettings"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
