"""اختبارات تحديد الحصة الحالية — كل الحالات الزمنية (البند 58)."""

from datetime import time

import pytest

from academics.models import BellPeriod, BellSchedule, SchoolWeekDay, Weekday
from attendance.services.periods import get_current_attendance_period
from tests.attendance_helpers import aware


@pytest.fixture
def school_with_schedule(make_school):
    """جدول عادي (الأحد-الأربعاء) + جدول خميس مختلف + فسحة."""
    school = make_school()
    normal = BellSchedule.objects.create(school=school, name="العادي")
    BellPeriod.objects.create(
        school=school, bell_schedule=normal, sequence=1, name="الأولى",
        start_time=time(7, 0), end_time=time(7, 45),
    )
    BellPeriod.objects.create(
        school=school, bell_schedule=normal, sequence=2, name="الفسحة",
        start_time=time(7, 45), end_time=time(8, 5), is_attendance_period=False,
    )
    BellPeriod.objects.create(
        school=school, bell_schedule=normal, sequence=3, name="الثانية",
        start_time=time(8, 5), end_time=time(8, 50),
    )
    thursday = BellSchedule.objects.create(school=school, name="الخميس")
    BellPeriod.objects.create(
        school=school, bell_schedule=thursday, sequence=1, name="أولى الخميس",
        start_time=time(8, 0), end_time=time(9, 0),
    )
    for weekday in (Weekday.SUNDAY, Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY):
        SchoolWeekDay.objects.create(
            school=school, weekday=weekday, is_school_day=True, bell_schedule=normal
        )
    SchoolWeekDay.objects.create(
        school=school, weekday=Weekday.THURSDAY, is_school_day=True, bell_schedule=thursday
    )
    SchoolWeekDay.objects.create(school=school, weekday=Weekday.FRIDAY, is_school_day=False)
    return school


# 2026-08-23 أحد، 2026-08-27 خميس، 2026-08-28 جمعة


@pytest.mark.django_db
def test_inside_period(school_with_schedule):
    period, _ = get_current_attendance_period(
        school_with_schedule, aware(school_with_schedule, 2026, 8, 23, 7, 20)
    )
    assert period is not None and period.name == "الأولى"


@pytest.mark.django_db
def test_before_first_period(school_with_schedule):
    period, _ = get_current_attendance_period(
        school_with_schedule, aware(school_with_schedule, 2026, 8, 23, 6, 30)
    )
    assert period is None


@pytest.mark.django_db
def test_after_last_period(school_with_schedule):
    period, _ = get_current_attendance_period(
        school_with_schedule, aware(school_with_schedule, 2026, 8, 23, 13, 0)
    )
    assert period is None


@pytest.mark.django_db
def test_break_has_no_attendance_period(school_with_schedule):
    """الفسحة is_attendance_period=False → لا حصة حالية."""
    period, _ = get_current_attendance_period(
        school_with_schedule, aware(school_with_schedule, 2026, 8, 23, 7, 50)
    )
    assert period is None


@pytest.mark.django_db
def test_non_school_day(school_with_schedule):
    period, _ = get_current_attendance_period(
        school_with_schedule, aware(school_with_schedule, 2026, 8, 28, 7, 20)  # جمعة
    )
    assert period is None


@pytest.mark.django_db
def test_thursday_uses_different_schedule(school_with_schedule):
    """الخميس بجدوله: 7:20 خارج جدوله (يبدأ 8:00) و8:30 داخله."""
    early, _ = get_current_attendance_period(
        school_with_schedule, aware(school_with_schedule, 2026, 8, 27, 7, 20)
    )
    assert early is None
    inside, _ = get_current_attendance_period(
        school_with_schedule, aware(school_with_schedule, 2026, 8, 27, 8, 30)
    )
    assert inside is not None and inside.name == "أولى الخميس"


@pytest.mark.django_db
def test_alternate_schedule_swap(school_with_schedule):
    """تبديل جدول اليوم (رمضان مثلاً) يغير النتيجة فورًا للجلسات الجديدة."""
    ramadan = BellSchedule.objects.create(school=school_with_schedule, name="رمضان")
    BellPeriod.objects.create(
        school=school_with_schedule, bell_schedule=ramadan, sequence=1,
        name="أولى رمضان", start_time=time(10, 0), end_time=time(10, 40),
    )
    SchoolWeekDay.objects.filter(
        school=school_with_schedule, weekday=Weekday.SUNDAY
    ).update(bell_schedule=ramadan)
    period, _ = get_current_attendance_period(
        school_with_schedule, aware(school_with_schedule, 2026, 8, 23, 10, 15)
    )
    assert period is not None and period.name == "أولى رمضان"


@pytest.mark.django_db
def test_timezone_respected(school_with_schedule):
    """مدرسة بمنطقة زمنية مختلفة: نفس اللحظة العالمية = حصة مختلفة."""
    from schools.services.settings import get_or_create_settings

    settings_obj = get_or_create_settings(school=school_with_schedule)
    settings_obj.timezone = "Asia/Dubai"  # +1 عن الرياض
    settings_obj.save(update_fields=["timezone"])

    # 07:20 بتوقيت الرياض = 08:20 بتوقيت دبي → داخل «الثانية» (8:05-8:50)
    from datetime import datetime
    from zoneinfo import ZoneInfo

    riyadh_time = datetime(2026, 8, 23, 7, 20, tzinfo=ZoneInfo("Asia/Riyadh"))
    dubai_time = riyadh_time.astimezone(ZoneInfo("Asia/Dubai"))
    period, _ = get_current_attendance_period(school_with_schedule, dubai_time)
    assert period is not None and period.name == "الثانية"
