"""أدوات بناء بيئة حضور للاختبارات — جدول أجراس حول «الآن» المحلي للمدرسة."""

from datetime import date, datetime, timedelta

from academics.models import (
    AcademicYear,
    AcademicYearStatus,
    BellPeriod,
    BellSchedule,
    SchoolWeekDay,
)
from attendance.services.periods import _PY_TO_SCHOOL_WEEKDAY, school_now
from common.security.identifiers import (
    encrypt_national_id,
    mask_national_id,
    national_id_lookup_hash,
)
from students.models import Grade, Section, Student, StudentEnrollment


def make_students(school, section, year, count: int, prefix: str = "10660") -> list[Student]:
    students = []
    grade = section.grade
    for i in range(count):
        nid = f"1{prefix}{i:04d}"
        student = Student.objects.create(
            school=school,
            national_id_encrypted=encrypt_national_id(nid),
            national_id_lookup_hash=national_id_lookup_hash(nid),
            national_id_masked=mask_national_id(nid),
            full_name=f"طالب حضور {prefix}-{i:02d}",  # البادئة تمنع تطابق الأسماء بين الفصول
        )
        StudentEnrollment.objects.create(
            school=school,
            student=student,
            academic_year=year,
            grade=grade,
            section=section,
            # تاريخ ماضٍ دائمًا — enrollments_on_date(اليوم الفعلي أو 2026-08-23) يجدهم
            enrolled_at=date(2026, 8, 1),
        )
        students.append(student)
    return students


def setup_attendance_env(school, *, students_count: int = 5, period_started_minutes_ago: int = 10):
    """عام نشط + صف/فصل + طلاب + جدول بحصة تغطي «الآن» + يوم الأسبوع الحالي."""
    year, _ = AcademicYear.objects.get_or_create(
        school=school,
        name="عام الحضور",
        defaults={
            "start_date": date(2026, 8, 23),
            "end_date": date(2027, 6, 25),
            "status": AcademicYearStatus.ACTIVE,
        },
    )
    if year.status != AcademicYearStatus.ACTIVE:
        year.status = AcademicYearStatus.ACTIVE
        year.save(update_fields=["status"])

    grade, _ = Grade.objects.get_or_create(
        school=school, code="SEC_1", defaults={"name": "الأول الثانوي", "sequence": 10}
    )
    section, _ = Section.objects.get_or_create(
        school=school, grade=grade, code="1", defaults={"name": "1"}
    )
    students = make_students(school, section, year, students_count)

    local_now = school_now(school)
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = local_now.replace(hour=23, minute=59, second=59, microsecond=999999)
    latest_safe_start = local_now.replace(hour=23, minute=30, second=0, microsecond=0)
    # BellPeriod is a same-day time range. Clamp fixtures at midnight so a test
    # run around 00:00/24:00 cannot create an invalid cross-day period.
    start = min(
        max(local_now - timedelta(minutes=period_started_minutes_ago), day_start),
        latest_safe_start,
    ).time()
    end = min(local_now + timedelta(minutes=45), day_end).time()

    schedule = BellSchedule.objects.create(school=school, name="جدول الاختبار")
    period = BellPeriod.objects.create(
        school=school,
        bell_schedule=schedule,
        sequence=3,
        name="الحصة الثالثة",
        start_time=start,
        end_time=end,
    )
    weekday = _PY_TO_SCHOOL_WEEKDAY[local_now.weekday()]
    SchoolWeekDay.objects.update_or_create(
        school=school,
        weekday=weekday,
        defaults={"is_school_day": True, "bell_schedule": schedule},
    )
    return {
        "year": year,
        "grade": grade,
        "section": section,
        "students": students,
        "schedule": schedule,
        "period": period,
        "local_now": local_now,
    }


def aware(school, year_, month, day, hour, minute) -> datetime:
    from zoneinfo import ZoneInfo

    from schools.services.settings import get_or_create_settings

    tz = ZoneInfo(get_or_create_settings(school=school).timezone)
    return datetime(year_, month, day, hour, minute, tzinfo=tz)
