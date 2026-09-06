"""اختبارات API لوحة الإدارة (م15): الصلاحيات، العزل، الكاش، الفلاتر، الأخطاء.

أهم اختبار هنا **عزل الكاش**: مدرستان بنفس الفلاتر تمامًا يجب ألا تتبادلا رقمًا
واحدًا، وتبديل المدرسة يجب ألا يُظهر أثرًا من المدرسة السابقة (بنود 91/92/156).
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

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
from students.models import Grade, Section
from tests.attendance_helpers import make_students

BASE = "/api/v1/dashboard/"
TZ = ZoneInfo("Asia/Riyadh")
DAY = date(2026, 8, 16)
PERIOD_COUNT = 7


def build_school(school, make_user, make_membership, *, prefix, mobile, absent_students=1):
    """مدرسة كاملة بيومٍ مكتمل وعدد محدد من الغياب الكامل بدون عذر."""
    year = AcademicYear.objects.create(
        school=school, name="2026/2027", start_date=date(2026, 8, 1),
        end_date=date(2027, 6, 25), status=AcademicYearStatus.ACTIVE,
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
    teacher = make_membership(make_user(mobile), school, ["TEACHER"])

    for seq in range(1, PERIOD_COUNT + 1):
        session = AttendanceSession.objects.create(
            school=school, academic_year=year, section=section,
            attendance_date=DAY, period_sequence=seq,
            bell_period_snapshot={
                "sequence": seq, "name": f"الحصة {seq}",
                "start_time": f"{6 + seq:02d}:00", "end_time": f"{6 + seq:02d}:45",
                "attendance_date": DAY.isoformat(), "timezone": "Asia/Riyadh",
            },
            status="SUBMITTED", roster_fingerprint="fp",
            unprepared_alert_minutes_snapshot=25,
            started_by_membership=teacher, submitted_by_membership=teacher,
            submitted_at=datetime(2026, 8, 16, 6 + seq, 10, tzinfo=TZ),
        )
        for student in students[:absent_students]:
            AttendanceMark.objects.create(
                school=school, session=session, student=student, status="ABSENT"
            )
    recalculate_daily_attendance_for_section(
        school=school, section=section, attendance_date=DAY
    )
    return {"year": year, "grade": grade, "section": section, "students": students}


def range_query(**extra) -> str:
    params = {"from_date": DAY.isoformat(), "to_date": DAY.isoformat(), **extra}
    return "?" + "&".join(f"{key}={value}" for key, value in params.items())


@pytest.fixture
def api_env(role_client, make_user, make_membership):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    data = build_school(
        school, make_user, make_membership, prefix="91100", mobile="0551510001"
    )
    return {"client": client, "school": school, **data}


# ---------- الصلاحيات (بنود 82-85) ----------


@pytest.mark.django_db
def test_manager_and_vice_can_read(api_env, role_client):
    assert api_env["client"].get(f"{BASE}overview/{range_query()}").status_code == 200
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=api_env["school"])
    assert vice.get(f"{BASE}overview/{range_query()}").status_code == 200


@pytest.mark.django_db
def test_teacher_and_counselor_denied(api_env, role_client):
    """المعلم لا لوحة تنفيذية له، والمرشد لديه لوحته الخاصة (م14)."""
    teacher, _, _ = role_client(["TEACHER"], school=api_env["school"])
    counselor, _, _ = role_client(["COUNSELOR"], school=api_env["school"])
    for endpoint in ("overview/", "today/", "attendance-trend/", "sections/", "attention/"):
        assert teacher.get(f"{BASE}{endpoint}{range_query()}").status_code == 403
        assert counselor.get(f"{BASE}{endpoint}{range_query()}").status_code == 403


# ---------- صحة الأرقام ----------


@pytest.mark.django_db
def test_overview_shape_and_numbers(api_env):
    response = api_env["client"].get(f"{BASE}overview/{range_query()}")
    assert response.status_code == 200
    body = response.json()

    assert body["context"]["range"]["days"] == 1
    assert body["context"]["previous_range"]["days"] == 1   # فترتان متساويتان
    assert body["context"]["timezone"] == "Asia/Riyadh"
    assert body["attendance"]["unexcused_full_absence_days"] == 1
    assert body["attendance"]["unit"] == "STUDENT_DAYS"
    assert body["attendance"]["undetermined_days"] == 0
    # الإرشاد مدمج (م14) — أعداد حقيقية لا قيمة مختلقة
    assert body["counseling"]["available"] is True
    assert body["counseling"]["open_cases"] == 0
    # لا نصوص حساسة في اللوحة التنفيذية (بند 45/87)
    serialized = str(body)
    for forbidden in ("description", "notes", "national_id", "guardian"):
        assert forbidden not in serialized


@pytest.mark.django_db
def test_comparison_present_and_safe(api_env):
    body = api_env["client"].get(f"{BASE}overview/{range_query()}").json()
    comparison = body["comparison"]["unexcused_full_absence_days"]
    assert comparison["current"] == 1
    assert comparison["previous"] == 0
    assert comparison["change_pct"] is None   # لا قسمة على صفر
    assert comparison["is_new"] is True


@pytest.mark.django_db
def test_trend_sections_and_attention(api_env):
    trend = api_env["client"].get(f"{BASE}attendance-trend/{range_query()}").json()
    assert trend["granularity"] == "DAY"
    assert trend["points"][0]["unexcused_full_absence"] == 1

    sections = api_env["client"].get(f"{BASE}sections/{range_query()}").json()
    assert sections["sections"][0]["unexcused_full_absence_days"] == 1

    attention = api_env["client"].get(f"{BASE}attention/").json()
    assert "items" in attention and "counts" in attention

    today = api_env["client"].get(f"{BASE}today/").json()
    assert "has_active_period" in today
    assert "submission_completion_pct" in today
    assert today["operational_state"] in {
        "IDLE",
        "ACTION_REQUIRED",
        "ON_TRACK",
        "IN_PROGRESS",
    }
    assert today["headline"]
    assert today["updated_at"] == today["school_time"]


# ---------- الفلاتر والأخطاء ----------


@pytest.mark.django_db
def test_scope_filter_applies(api_env):
    scoped = api_env["client"].get(
        f"{BASE}overview/{range_query(section=api_env['section'].id)}"
    ).json()
    assert scoped["attendance"]["unexcused_full_absence_days"] == 1
    assert scoped["context"]["scope"]["section_id"] == api_env["section"].id


@pytest.mark.django_db
def test_invalid_inputs_return_400_not_500(api_env):
    client = api_env["client"]
    bad_date = client.get(f"{BASE}overview/?from_date=abc&to_date=2026-08-16")
    assert bad_date.status_code == 400
    assert bad_date.json()["code"] == "DASHBOARD_INVALID_DATE_RANGE"

    reversed_range = client.get(f"{BASE}overview/?from_date=2026-08-20&to_date=2026-08-01")
    assert reversed_range.status_code == 400

    too_large = client.get(f"{BASE}overview/?from_date=2020-01-01&to_date=2026-08-01")
    assert too_large.status_code == 400
    assert too_large.json()["code"] == "DASHBOARD_RANGE_TOO_LARGE"

    bad_preset = client.get(f"{BASE}overview/?preset=NOPE")
    assert bad_preset.status_code == 400

    bad_grade = client.get(f"{BASE}overview/{range_query(grade='abc')}")
    assert bad_grade.status_code == 400
    assert bad_grade.json()["code"] == "DASHBOARD_INVALID_GRADE"


@pytest.mark.django_db
def test_foreign_filter_ids_rejected(api_env, role_client, make_user, make_membership):
    """فلتر بمعرف من مدرسة أخرى: 404 لا تجاهل صامت (بند 90)."""
    _, other_school, _ = role_client(["SCHOOL_MANAGER"])
    other = build_school(
        other_school, make_user, make_membership, prefix="91200", mobile="0551510002"
    )
    response = api_env["client"].get(
        f"{BASE}overview/{range_query(section=other['section'].id)}"
    )
    assert response.status_code == 404
    assert response.json()["code"] == "DASHBOARD_INVALID_SECTION"

    grade_response = api_env["client"].get(
        f"{BASE}overview/{range_query(grade=other['grade'].id)}"
    )
    assert grade_response.status_code == 404


# ---------- العزل بين المدارس والكاش (الأهم) ----------


@pytest.mark.django_db
def test_tenant_and_cache_isolation(api_env, role_client, make_user, make_membership):
    """مدرستان بنفس الفلاتر حرفيًا — لا يتسرب رقم واحد بينهما عبر الكاش."""
    other_client, other_school, _ = role_client(["SCHOOL_MANAGER"])
    build_school(
        other_school, make_user, make_membership,
        prefix="91300", mobile="0551510003", absent_students=3,
    )

    first = api_env["client"].get(f"{BASE}overview/{range_query()}").json()
    second = other_client.get(f"{BASE}overview/{range_query()}").json()

    assert first["attendance"]["unexcused_full_absence_days"] == 1
    assert second["attendance"]["unexcused_full_absence_days"] == 3

    # وإعادة الطلب لكل منهما (من الكاش هذه المرة) تبقي الرقمين منفصلين
    first_again = api_env["client"].get(f"{BASE}overview/{range_query()}").json()
    second_again = other_client.get(f"{BASE}overview/{range_query()}").json()
    assert first_again["attendance"]["unexcused_full_absence_days"] == 1
    assert second_again["attendance"]["unexcused_full_absence_days"] == 3


@pytest.mark.django_db
def test_school_switch_shows_no_previous_school_numbers(
    api_env, make_school, make_membership, make_user
):
    """نفس المستخدم يبدل المدرسة: لا أثر من الأولى بعد التبديل (بند 156)."""
    client = api_env["client"]
    first = client.get(f"{BASE}overview/{range_query()}").json()
    assert first["attendance"]["unexcused_full_absence_days"] == 1

    school_b = make_school()
    manager_user = api_env["client"].session.get("_auth_user_id")
    from accounts.models import User

    user = User.objects.get(id=manager_user)
    make_membership(user, school_b, ["SCHOOL_MANAGER"])
    build_school(
        school_b, make_user, make_membership,
        prefix="91400", mobile="0551510004", absent_students=2,
    )

    switched = client.post(
        "/api/v1/session/active-school/", {"school_id": school_b.id},
        content_type="application/json",
    )
    assert switched.status_code == 200

    after = client.get(f"{BASE}overview/{range_query()}").json()
    assert after["attendance"]["unexcused_full_absence_days"] == 2
    assert after["context"]["academic_year"]["id"] != first["context"]["academic_year"]["id"]


@pytest.mark.django_db
def test_cache_key_includes_school(api_env):
    """المفتاح يبدأ بمعرف المدرسة — شرط بنيوي لا يعتمد على انضباط المستدعي."""
    from school_dashboard.cache import build_key

    key_a = build_key(school_id=1, section="overview", parts={"x": 1})
    key_b = build_key(school_id=2, section="overview", parts={"x": 1})
    assert key_a.startswith("dash:1:overview:")
    assert key_b.startswith("dash:2:overview:")
    assert key_a != key_b


@pytest.mark.django_db
def test_dashboard_cache_is_invalidated_per_school(api_env):
    """تغيير التحضير يبدل نسخة كاش المدرسة بلا التأثير على مدرسة أخرى."""
    from school_dashboard.cache import build_key, invalidate_school

    before = build_key(school_id=api_env["school"].id, section="today", parts={})
    other_before = build_key(school_id=999999, section="today", parts={})

    invalidate_school(api_env["school"].id)

    after = build_key(school_id=api_env["school"].id, section="today", parts={})
    other_after = build_key(school_id=999999, section="today", parts={})
    assert after != before
    assert other_after == other_before
