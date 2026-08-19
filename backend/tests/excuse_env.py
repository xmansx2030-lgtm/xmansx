"""بناء بيئة اختبار مشتركة (حضور + أعذار) — يستخدمها اختبارا م10 وم11.

مستخرج من fixture المرحلة 10 كما هو (بلا تغيير سلوك) ليتجنب استيراد fixtures بين
ملفات الاختبار (نمط tests/attendance_helpers.py القائم).
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from academics.models import (
    AcademicYear,
    AcademicYearStatus,
    BellPeriod,
    BellSchedule,
    SchoolWeekDay,
    Weekday,
)
from attendance.models import AttendanceMark, AttendanceSession
from attendance.services.daily_summary import recalculate_daily_attendance_for_section
from excuses.services.coverage import approve_excuse, resolve_coverage_plan
from excuses.services.excuses import create_excuse
from students.models import Grade, Section
from tests.attendance_helpers import make_students

TZ = ZoneInfo("Asia/Riyadh")
DAY = datetime(2026, 8, 16).date()  # أحد ماضٍ (اليوم المرجعي 2026-08-19)
DAY2 = datetime(2026, 8, 17).date()  # اثنين
PERIOD_COUNT = 7


def build_env(*, school, teacher_membership, vice_membership, prefix="30100"):
    year = AcademicYear.objects.create(
        school=school, name="2026/2027", start_date=datetime(2026, 8, 1).date(),
        end_date=datetime(2027, 6, 25).date(), status=AcademicYearStatus.ACTIVE,
    )
    schedule = BellSchedule.objects.create(school=school, name="سبع حصص")
    for i in range(PERIOD_COUNT):
        BellPeriod.objects.create(
            school=school, bell_schedule=schedule, sequence=i + 1,
            name=f"الحصة {i + 1}",
            start_time=time(7 + i, 0), end_time=time(7 + i, 45),
        )
    for weekday in (Weekday.SUNDAY, Weekday.MONDAY):
        SchoolWeekDay.objects.create(
            school=school, weekday=weekday, is_school_day=True, bell_schedule=schedule
        )
    grade = Grade.objects.create(school=school, name="الأول الثانوي", code="G1", sequence=1)
    section = Section.objects.create(school=school, grade=grade, code="1", name="1")
    students = make_students(school, section, year, 3, prefix=prefix)
    return {
        "school": school, "year": year, "grade": grade, "section": section,
        "students": students, "teacher": teacher_membership, "vice": vice_membership,
        "schedule": schedule,
    }


def make_session(env, seq, *, day=DAY, status="SUBMITTED", section=None):
    section = section or env["section"]
    return AttendanceSession.objects.create(
        school=env["school"], academic_year=env["year"], section=section,
        attendance_date=day, period_sequence=seq,
        bell_period_snapshot={
            "sequence": seq, "name": f"الحصة {seq}",
            "start_time": f"{6 + seq:02d}:00", "end_time": f"{6 + seq:02d}:45",
            "attendance_date": day.isoformat(), "timezone": "Asia/Riyadh",
        },
        status=status, roster_fingerprint="fp",
        unprepared_alert_minutes_snapshot=25,
        started_by_membership=env["teacher"],
        submitted_by_membership=env["teacher"] if status == "SUBMITTED" else None,
        submitted_at=datetime(2026, 8, 16, 6 + seq, 10, tzinfo=TZ)
        if status == "SUBMITTED" else None,
    )


def mark(env, session, student, status, minutes=None):
    return AttendanceMark.objects.create(
        school=env["school"], session=session, student=student, status=status,
        late_minutes=minutes, arrival_time=time(8, 30) if status == "LATE" else None,
    )


def recalc(env, *, day=DAY, section=None):
    recalculate_daily_attendance_for_section(
        school=env["school"], section=section or env["section"], attendance_date=day
    )


def full_day_absent(env, student, *, day=DAY, periods=PERIOD_COUNT):
    sessions = []
    for seq in range(1, periods + 1):
        session = make_session(env, seq, day=day)
        mark(env, session, student, "ABSENT")
        sessions.append(session)
    recalc(env, day=day)
    return sessions


def excuse_for(env, student, targets, *, reason="MEDICAL_REPORT"):
    return create_excuse(
        school=env["school"], membership=env["vice"], student=student,
        reason_type=reason, notes="", targets=targets,
    )


def approve(env, excuse):
    plan = resolve_coverage_plan(excuse)
    return approve_excuse(
        excuse_id=excuse.id, school=env["school"], membership=env["vice"],
        preview_hash=plan["preview_hash"],
    )
