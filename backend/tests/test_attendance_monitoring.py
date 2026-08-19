"""اختبارات لوحة متابعة التحضير (المرحلة 7) — حدود المهلة، الاشتقاق، snapshot، الأدوار."""

from datetime import datetime, time
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
from attendance.models import AttendanceSession, AttendanceSessionStatus
from attendance.selectors.monitoring import get_current_section_attendance_statuses
from attendance.services.periods import build_period_snapshot
from attendance.services.timing import (
    alert_at_for,
    overdue_minutes,
    session_submission_delay_minutes,
)
from common.errors import ApiError
from schools.services.settings import get_or_create_settings
from students.models import Grade, Section
from tests.attendance_helpers import make_students

TZ = ZoneInfo("Asia/Riyadh")
# 2026-08-23 أحد
DAY = datetime(2026, 8, 23).date()


def at(hour, minute, second=0):
    return datetime(2026, 8, 23, hour, minute, second, tzinfo=TZ)


# ---------- timing: الحدود والتقريب (البنود 10 و14 و76) ----------


def test_alert_boundary_and_floor():
    alert = alert_at_for(day=DAY, start_time=time(8, 30), alert_minutes=25, tz_name="Asia/Riyadh")
    assert alert == at(8, 55)
    assert overdue_minutes(alert, at(8, 54, 59)) is None  # في الوقت
    assert overdue_minutes(alert, at(8, 55, 0)) == 0  # متأخر — الحد الدقيق
    assert overdue_minutes(alert, at(8, 55, 59)) == 0  # floor
    assert overdue_minutes(alert, at(9, 2, 0)) == 7  # مثال البند 12


# ---------- بيئة المراقبة ----------


@pytest.fixture
def env(make_school, make_user, make_membership):
    school = make_school()
    year = AcademicYear.objects.create(
        school=school, name="2026/2027",
        start_date=DAY, end_date=datetime(2027, 6, 25).date(),
        status=AcademicYearStatus.ACTIVE,
    )
    schedule = BellSchedule.objects.create(school=school, name="العادي")
    period = BellPeriod.objects.create(
        school=school, bell_schedule=schedule, sequence=3, name="الحصة الثالثة",
        start_time=time(8, 30), end_time=time(9, 15),
    )
    for weekday in (Weekday.SUNDAY, Weekday.MONDAY):
        SchoolWeekDay.objects.create(
            school=school, weekday=weekday, is_school_day=True, bell_schedule=schedule
        )
    SchoolWeekDay.objects.create(school=school, weekday=Weekday.FRIDAY, is_school_day=False)

    grade = Grade.objects.create(school=school, name="الأول الثانوي", sequence=1)
    sections = {}
    for code in ("1", "2", "3"):
        section = Section.objects.create(school=school, grade=grade, code=code, name=code)
        make_students(school, section, year, 3, prefix=f"17{code}0")
        sections[code] = section
    # فصل فارغ + فصل غير فعال بطلاب — كلاهما خارج المتوقع
    sections["empty"] = Section.objects.create(school=school, grade=grade, code="9", name="9")
    inactive = Section.objects.create(
        school=school, grade=grade, code="8", name="8", is_active=False
    )
    make_students(school, inactive, year, 2, prefix="1780")
    sections["inactive"] = inactive

    teacher = make_user("0550000700", first_name="بدر", last_name="المعلم")
    membership = make_membership(teacher, school, ["TEACHER"])
    return {
        "school": school, "year": year, "period": period, "schedule": schedule,
        "grade": grade, "sections": sections, "membership": membership,
    }


def make_session(env, section, *, status, snapshot_minutes=25, submitted_at=None):
    session = AttendanceSession.objects.create(
        school=env["school"], academic_year=env["year"], section=section,
        attendance_date=DAY, bell_period=env["period"],
        period_sequence=env["period"].sequence,
        bell_period_snapshot=build_period_snapshot(env["period"], DAY, "Asia/Riyadh"),
        status=status, roster_fingerprint="fp",
        unprepared_alert_minutes_snapshot=snapshot_minutes,
        started_by_membership=env["membership"],
        submitted_by_membership=env["membership"] if submitted_at else None,
        submitted_at=submitted_at,
    )
    return session


def monitor(env, when):
    return get_current_section_attendance_statuses(school=env["school"], now=when)


def row(payload, section):
    return next(r for r in payload["sections"] if r["section_id"] == section.id)


# ---------- الاشتقاق والملخص ----------


@pytest.mark.django_db
def test_mixed_statuses_before_threshold(env):
    make_session(env, env["sections"]["1"], status="SUBMITTED", submitted_at=at(8, 40))
    make_session(env, env["sections"]["2"], status="IN_PROGRESS")

    payload = monitor(env, at(8, 50))
    assert payload["period"]["name"] == "الحصة الثالثة"
    assert payload["alert"] == {"minutes": 25, "alert_at": "08:55"}
    assert payload["summary"] == {
        "total": 3, "submitted": 1, "in_progress": 1, "not_started": 1,
        "overdue_total": 0, "overdue_submitted": 0,
        "overdue_in_progress": 0, "overdue_not_started": 0,
    }
    submitted = row(payload, env["sections"]["1"])
    assert submitted["attendance_status"] == "SUBMITTED"
    assert submitted["timeliness_status"] == "ON_TIME"
    assert submitted["submitted_at"] == "08:40"
    assert submitted["teacher_name"] == "بدر المعلم"
    not_started = row(payload, env["sections"]["3"])
    assert not_started["attendance_status"] == "NOT_STARTED"
    assert not_started["teacher_name"] is None  # لا جدول معلمين — قرار مقصود
    # الترتيب: قيد التحضير ثم لم يبدأ ثم المعتمد (الكل في الوقت)
    statuses = [r["attendance_status"] for r in payload["sections"]]
    assert statuses == ["IN_PROGRESS", "NOT_STARTED", "SUBMITTED"]


@pytest.mark.django_db
def test_overdue_after_threshold(env):
    make_session(env, env["sections"]["1"], status="SUBMITTED", submitted_at=at(8, 40))
    make_session(env, env["sections"]["2"], status="IN_PROGRESS")

    payload = monitor(env, at(9, 0))
    assert payload["summary"]["overdue_total"] == 2
    assert payload["summary"]["overdue_in_progress"] == 1
    assert payload["summary"]["overdue_not_started"] == 1
    assert payload["summary"]["overdue_submitted"] == 0
    assert row(payload, env["sections"]["2"])["minutes_overdue"] == 5
    assert row(payload, env["sections"]["3"])["minutes_overdue"] == 5
    # المعتمد في الوقت يبقى في الوقت — لا يقاس بالوقت الحالي
    assert row(payload, env["sections"]["1"])["timeliness_status"] == "ON_TIME"
    # المتأخرون أولًا: لم يبدأ ثم قيد التحضير ثم المعتمد في الوقت
    statuses = [r["attendance_status"] for r in payload["sections"]]
    assert statuses == ["NOT_STARTED", "IN_PROGRESS", "SUBMITTED"]


@pytest.mark.django_db
def test_submitted_late_uses_submitted_at_not_now(env):
    """‏submitted_at هو المعيار (البند 12) — لا الوقت الحالي ولا started_at."""
    make_session(env, env["sections"]["1"], status="SUBMITTED", submitted_at=at(9, 2))
    payload = monitor(env, at(9, 10))
    submitted = row(payload, env["sections"]["1"])
    assert submitted["timeliness_status"] == "OVERDUE"
    assert submitted["minutes_overdue"] == 7  # 09:02 - 08:55
    assert payload["summary"]["overdue_submitted"] == 1


@pytest.mark.django_db
def test_submitted_exact_boundary(env):
    """‏08:54:59 في الوقت، 08:55:00 متأخر (البند 79)."""
    make_session(env, env["sections"]["1"], status="SUBMITTED",
                 submitted_at=at(8, 54, 59))
    make_session(env, env["sections"]["2"], status="SUBMITTED",
                 submitted_at=at(8, 55, 0))
    payload = monitor(env, at(9, 0))
    assert row(payload, env["sections"]["1"])["timeliness_status"] == "ON_TIME"
    boundary = row(payload, env["sections"]["2"])
    assert boundary["timeliness_status"] == "OVERDUE"
    assert boundary["minutes_overdue"] == 0


@pytest.mark.django_db
def test_not_started_is_derived_no_rows_created(env):
    """‏NOT_STARTED طرح لا إنشاء — اللوحة قراءة صرفة (البند 4)."""
    assert AttendanceSession.objects.count() == 0
    payload = monitor(env, at(9, 0))
    assert payload["summary"]["not_started"] == 3
    assert AttendanceSession.objects.count() == 0  # لا صف أنشئ


@pytest.mark.django_db
def test_empty_and_inactive_sections_excluded(env):
    payload = monitor(env, at(8, 50))
    ids = {r["section_id"] for r in payload["sections"]}
    assert env["sections"]["empty"].id not in ids  # بلا طلاب — خارج المتوقع
    assert env["sections"]["inactive"].id not in ids
    assert payload["summary"]["total"] == 3


@pytest.mark.django_db
def test_no_active_year_errors(env):
    AcademicYear.objects.filter(school=env["school"]).update(
        status=AcademicYearStatus.ARCHIVED
    )
    with pytest.raises(ApiError) as exc:
        monitor(env, at(8, 50))
    assert exc.value.code == "ACTIVE_ACADEMIC_YEAR_REQUIRED"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "when",
    [
        datetime(2026, 8, 28, 8, 50, tzinfo=TZ),  # جمعة — يوم غير دراسي
        at(7, 0),  # قبل الدوام
        at(12, 0),  # بعد آخر حصة
    ],
)
def test_no_period_no_alerts(env, when):
    """لا حصة → لوحة فارغة واضحة، لا فصول متأخرة ولا خطأ (البنود 8 و84 و85)."""
    payload = get_current_section_attendance_statuses(school=env["school"], now=when)
    assert payload["period"] is None
    assert payload["summary"] is None
    assert payload["sections"] == []


@pytest.mark.django_db
def test_break_period_no_monitoring(env):
    BellPeriod.objects.create(
        school=env["school"], bell_schedule=env["schedule"], sequence=4,
        name="الفسحة", start_time=time(9, 15), end_time=time(9, 40),
        is_attendance_period=False,
    )
    payload = monitor(env, at(9, 20))
    assert payload["period"] is None
    assert payload["sections"] == []


@pytest.mark.django_db
def test_thursday_alternate_schedule(env):
    """الخميس بجدوله الخاص — البداية والتنبيه منه (البنود 82 و83)."""
    thursday = BellSchedule.objects.create(school=env["school"], name="الخميس")
    BellPeriod.objects.create(
        school=env["school"], bell_schedule=thursday, sequence=1, name="أولى الخميس",
        start_time=time(9, 0), end_time=time(10, 0),
    )
    SchoolWeekDay.objects.create(
        school=env["school"], weekday=Weekday.THURSDAY,
        is_school_day=True, bell_schedule=thursday,
    )
    # 2026-08-27 خميس 09:30 → alert 09:25 → متأخر 5 دقائق
    when = datetime(2026, 8, 27, 9, 30, tzinfo=TZ)
    payload = get_current_section_attendance_statuses(school=env["school"], now=when)
    assert payload["period"]["name"] == "أولى الخميس"
    assert payload["alert"]["alert_at"] == "09:25"
    assert row(payload, env["sections"]["1"])["minutes_overdue"] == 5


# ---------- Threshold Snapshot (البنود 33-36 و73-75) ----------


@pytest.mark.django_db
def test_threshold_change_does_not_rewrite_history(env):
    """جلسة فتحت والمهلة 25 واعتمدت دقيقة 20 — تبقى في الوقت بعد تغيير الإعداد إلى 15."""
    session = make_session(
        env, env["sections"]["1"], status="SUBMITTED",
        snapshot_minutes=25, submitted_at=at(8, 50),
    )
    settings_obj = get_or_create_settings(school=env["school"])
    settings_obj.unprepared_period_alert_minutes = 15
    settings_obj.save(update_fields=["unprepared_period_alert_minutes"])

    payload = monitor(env, at(9, 0))
    assert row(payload, env["sections"]["1"])["timeliness_status"] == "ON_TIME"
    assert session_submission_delay_minutes(session) is None
    # ‏NOT_STARTED بلا جلسة → الإعداد الحالي 15 (alert 08:45) → متأخر 15 دقيقة
    not_started = row(payload, env["sections"]["3"])
    assert payload["alert"]["minutes"] == 15
    assert not_started["minutes_overdue"] == 15


@pytest.mark.django_db
def test_start_session_captures_current_threshold(make_school, make_user, make_membership):
    """الجلسة الجديدة تلتقط قيمة الإعداد لحظة الفتح (البند 75)."""
    from attendance.services.sessions import start_session
    from tests.attendance_helpers import setup_attendance_env

    school = make_school()
    settings_obj = get_or_create_settings(school=school)
    settings_obj.unprepared_period_alert_minutes = 33
    settings_obj.save(update_fields=["unprepared_period_alert_minutes"])
    env2 = setup_attendance_env(school, students_count=2)
    teacher = make_user("0550000701")
    membership = make_membership(teacher, school, ["TEACHER"])
    session, _, _ = start_session(
        school=school, membership=membership, section=env2["section"]
    )
    assert session.unprepared_alert_minutes_snapshot == 33


@pytest.mark.django_db
def test_submitted_at_and_started_at_immutable_after_edit(
    make_school, make_user, make_membership
):
    """أول اعتماد هو المرجع — التعديل والاستئناف لا يغيران الأوقات (71-72، 80-81)."""
    from attendance.services.sessions import edit_session, start_session, submit_session
    from tests.attendance_helpers import setup_attendance_env

    school = make_school()
    env2 = setup_attendance_env(school, students_count=3)
    teacher = make_user("0550000702")
    membership = make_membership(teacher, school, ["TEACHER"])
    session, _, _ = start_session(school=school, membership=membership, section=env2["section"])
    original_started = session.started_at

    # استئناف لا يغير started_at
    resumed, _, was_resumed = start_session(
        school=school, membership=membership, section=env2["section"]
    )
    assert was_resumed and resumed.started_at == original_started

    submit_session(session_id=session.id, school=school, membership=membership,
                   marks=[{"student_id": env2["students"][0].id, "status": "ABSENT"}])
    session.refresh_from_db()
    original_submitted = session.submitted_at
    delay_before = session_submission_delay_minutes(session)

    edit_session(
        session_id=session.id, school=school, membership=membership,
        roles=["TEACHER"], marks=[], reason="تصحيح",
    )
    session.refresh_from_db()
    assert session.submitted_at == original_submitted  # ثابت بالبايت
    assert session.started_at == original_started
    assert session_submission_delay_minutes(session) == delay_before


@pytest.mark.django_db
def test_suspended_teacher_name_still_displayed(env):
    """إيقاف العضوية بعد الاعتماد لا يفقد الاسم التاريخي (البند 53)."""
    make_session(env, env["sections"]["1"], status="SUBMITTED", submitted_at=at(8, 40))
    env["membership"].status = "SUSPENDED"
    env["membership"].save(update_fields=["status"])
    payload = monitor(env, at(8, 50))
    assert row(payload, env["sections"]["1"])["teacher_name"] == "بدر المعلم"


# ---------- API: الأدوار والعزل (البنود 87-90) ----------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("roles", "expected"),
    [
        (["SCHOOL_MANAGER"], 200),
        (["VICE_PRINCIPAL"], 200),
        (["TEACHER"], 403),
        (["COUNSELOR"], 403),
        (["TEACHER", "VICE_PRINCIPAL"], 200),  # دور الوكيل يفتح
        (["TEACHER", "COUNSELOR"], 403),
    ],
)
def test_monitoring_roles(role_client, roles, expected):
    client, school, _ = role_client(roles)
    AcademicYear.objects.create(
        school=school, name="ع", start_date=DAY,
        end_date=datetime(2027, 6, 25).date(), status=AcademicYearStatus.ACTIVE,
    )
    response = client.get("/api/v1/attendance/monitoring/current/")
    assert response.status_code == expected
    if expected == 403:
        assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_multi_school_role_scope(make_user, make_school, make_membership, login_client):
    """وكيل في A ومعلم في B: اللوحة تعمل في A وترفض في B (البند 89)."""
    user = make_user("0550000710")
    a, b = make_school("أ"), make_school("ب")
    make_membership(user, a, ["VICE_PRINCIPAL"])
    make_membership(user, b, ["TEACHER"])
    for school in (a, b):
        AcademicYear.objects.create(
            school=school, name="ع", start_date=DAY,
            end_date=datetime(2027, 6, 25).date(), status=AcademicYearStatus.ACTIVE,
        )
    client, _ = login_client("0550000710")

    client.post("/api/v1/session/active-school/", {"school_id": a.id},
                content_type="application/json")
    assert client.get("/api/v1/attendance/monitoring/current/").status_code == 200

    client.post("/api/v1/session/active-school/", {"school_id": b.id},
                content_type="application/json")
    response = client.get("/api/v1/attendance/monitoring/current/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_tenant_isolation_foreign_sections_and_sessions(env, make_school, make_user,
                                                        make_membership):
    """فصول وجلسات مدرسة أخرى لا تظهر — حتى بنفس التاريخ والتسلسل (البنود 49-50)."""
    other = make_school("أخرى")
    other_year = AcademicYear.objects.create(
        school=other, name="ع", start_date=DAY,
        end_date=datetime(2027, 6, 25).date(), status=AcademicYearStatus.ACTIVE,
    )
    other_grade = Grade.objects.create(school=other, name="صف", sequence=1)
    other_section = Section.objects.create(school=other, grade=other_grade, code="1", name="1")
    make_students(other, other_section, other_year, 2, prefix="1790")
    other_teacher = make_user("0550000711")
    other_membership = make_membership(other_teacher, other, ["TEACHER"])
    schedule = BellSchedule.objects.create(school=other, name="ع")
    other_period = BellPeriod.objects.create(
        school=other, bell_schedule=schedule, sequence=3, name="ثالثة",
        start_time=time(8, 30), end_time=time(9, 15),
    )
    AttendanceSession.objects.create(
        school=other, academic_year=other_year, section=other_section,
        attendance_date=DAY, bell_period=other_period, period_sequence=3,
        bell_period_snapshot=build_period_snapshot(other_period, DAY, "Asia/Riyadh"),
        status=AttendanceSessionStatus.SUBMITTED, roster_fingerprint="fp",
        unprepared_alert_minutes_snapshot=25,
        started_by_membership=other_membership,
        submitted_by_membership=other_membership, submitted_at=at(8, 40),
    )

    payload = monitor(env, at(8, 50))
    ids = {r["section_id"] for r in payload["sections"]}
    assert other_section.id not in ids
    assert payload["summary"]["total"] == 3
    assert payload["summary"]["submitted"] == 0  # جلسة المدرسة الأخرى لم تنضم


@pytest.mark.django_db
def test_query_count_constant(env, django_assert_max_num_queries):
    """لا استعلام لكل فصل — العدد ثابت مهما كبر العدد (البنود 55-56 و100)."""
    year = env["year"]
    grade = env["grade"]
    for i in range(30):
        section = Section.objects.create(
            school=env["school"], grade=grade, code=f"q{i}", name=f"q{i}"
        )
        make_students(env["school"], section, year, 2, prefix=f"18{i:02d}")
    make_session(env, env["sections"]["1"], status="SUBMITTED", submitted_at=at(8, 40))

    monitor(env, at(9, 0))  # تهيئة: أول نداء ينشئ سياق اليوم (م8) — نقيس الحالة المستقرة
    with django_assert_max_num_queries(10):
        payload = monitor(env, at(9, 0))
    assert payload["summary"]["total"] == 33
