"""اختبارات تحليلات الغياب (المرحلة 8) — حصة/عدة حصص/يوم كامل + التاريخية والعزل."""

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
from attendance.models import (
    AttendanceDayContext,
    AttendanceMark,
    AttendanceSession,
    DailyAttendanceSummary,
)
from attendance.selectors.analytics import get_daily_report, get_multi_period_report
from attendance.services.daily_summary import recalculate_daily_attendance_for_section
from common.errors import ApiError
from students.models import Grade, Section
from tests.attendance_helpers import make_students

TZ = ZoneInfo("Asia/Riyadh")
DAY = datetime(2026, 8, 23).date()  # أحد
PERIOD_COUNT = 7


@pytest.fixture
def env(make_school, make_user, make_membership):
    school = make_school()
    year = AcademicYear.objects.create(
        school=school,
        name="2026/2027",
        start_date=DAY,
        end_date=datetime(2027, 6, 25).date(),
        status=AcademicYearStatus.ACTIVE,
    )
    schedule = BellSchedule.objects.create(school=school, name="سبع حصص")
    for i in range(PERIOD_COUNT):
        BellPeriod.objects.create(
            school=school,
            bell_schedule=schedule,
            sequence=i + 1,
            name=f"الحصة {i + 1}",
            start_time=time(7 + i, 0),
            end_time=time(7 + i, 45),
        )
    BellPeriod.objects.create(  # فسحة — ليست حصة تحضير: خارج expected
        school=school,
        bell_schedule=schedule,
        sequence=90,
        name="الفسحة",
        start_time=time(9, 45),
        end_time=time(10, 0),
        is_attendance_period=False,
    )
    SchoolWeekDay.objects.create(
        school=school, weekday=Weekday.SUNDAY, is_school_day=True, bell_schedule=schedule
    )

    grade = Grade.objects.create(school=school, name="الأول الثانوي", code="G1", sequence=1)
    grade2 = Grade.objects.create(school=school, name="الثاني الثانوي", code="G2", sequence=2)
    section_a = Section.objects.create(school=school, grade=grade, code="1", name="1")
    section_b = Section.objects.create(school=school, grade=grade, code="2", name="2")
    section_c = Section.objects.create(school=school, grade=grade2, code="1", name="1")
    students_a = make_students(school, section_a, year, 3, prefix="20100")
    students_b = make_students(school, section_b, year, 2, prefix="20200")
    students_c = make_students(school, section_c, year, 2, prefix="20300")

    teacher = make_user("0550000800")
    membership = make_membership(teacher, school, ["TEACHER"])
    return {
        "school": school,
        "year": year,
        "schedule": schedule,
        "grade": grade,
        "grade2": grade2,
        "a": section_a,
        "b": section_b,
        "c": section_c,
        "sa": students_a,
        "sb": students_b,
        "sc": students_c,
        "membership": membership,
    }


def make_session(env, section, seq, *, status="SUBMITTED"):
    return AttendanceSession.objects.create(
        school=env["school"],
        academic_year=env["year"],
        section=section,
        attendance_date=DAY,
        period_sequence=seq,
        bell_period_snapshot={
            "sequence": seq,
            "name": f"الحصة {seq}",
            "start_time": f"{6 + seq:02d}:00",
            "end_time": f"{6 + seq:02d}:45",
            "attendance_date": DAY.isoformat(),
            "timezone": "Asia/Riyadh",
        },
        status=status,
        roster_fingerprint="fp",
        unprepared_alert_minutes_snapshot=25,
        started_by_membership=env["membership"],
        submitted_by_membership=env["membership"] if status == "SUBMITTED" else None,
        submitted_at=datetime(2026, 8, 23, 6 + seq, 10, tzinfo=TZ)
        if status == "SUBMITTED"
        else None,
    )


def mark(env, session, student, status, minutes=None):
    return AttendanceMark.objects.create(
        school=env["school"],
        session=session,
        student=student,
        status=status,
        late_minutes=minutes,
        arrival_time=time(8, 30) if status == "LATE" else None,
    )


def multi(env, sequences, match="ALL_ABSENT", **kwargs):
    return get_multi_period_report(
        school=env["school"],
        attendance_date=DAY,
        sequences=sequences,
        match=match,
        **kwargs,
    )


def names(report):
    return [s["full_name"] for s in report["students"]]


# ---------- تحليل حصة واحدة (البنود 16-19، 111) ----------


@pytest.mark.django_db
def test_period_absentees_and_incomplete_sections(env):
    s1 = make_session(env, env["a"], 1)
    mark(env, s1, env["sa"][0], "ABSENT")
    mark(env, s1, env["sa"][1], "LATE", minutes=10)
    s2 = make_session(env, env["b"], 1)
    mark(env, s2, env["sb"][0], "ABSENT")
    # ‏c: لا جلسة إطلاقًا

    report = multi(env, [1])
    assert report["summary"]["matching_students"] == 2  # المتأخر ليس غائبًا
    assert sorted(names(report)) == sorted([env["sa"][0].full_name, env["sb"][0].full_name])
    assert report["summary"]["complete_sections"] == 2
    assert report["summary"]["incomplete_sections"] == 1
    incomplete = report["incomplete_sections"][0]
    assert incomplete["section_id"] == env["c"].id
    assert "لم يتم التحضير" in incomplete["reason"]
    # طلاب c ليسوا في الغائبين ولا يحسبون حاضرين — غياب الجلسة ليس حضورًا (البند 27)
    c_names = {s.full_name for s in env["sc"]}
    assert not c_names & set(names(report))


@pytest.mark.django_db
def test_in_progress_not_official_and_reason_shown(env):
    """‏IN_PROGRESS ليست بيانات رسمية (البند 6) وسببها يعرض (البند 74)."""
    session = make_session(env, env["a"], 1, status="IN_PROGRESS")
    mark(env, session, env["sa"][0], "ABSENT")  # مسودة — لا تدخل التحليل
    report = multi(env, [1])
    assert env["sa"][0].full_name not in names(report)
    reason = next(
        s["reason"] for s in report["incomplete_sections"] if s["section_id"] == env["a"].id
    )
    assert "بدأ التحضير ولم يعتمد" in reason


# ---------- عدة حصص: ALL/ANY (البنود 21-29، 112-114) ----------


@pytest.fixture
def multi_env(env):
    """‏a: حصتان معتمدتان — محمد (A,A)، خالد (A,P)، سعد (A,L)."""
    s1 = make_session(env, env["a"], 1)
    s2 = make_session(env, env["a"], 2)
    mohammed, khaled, saad = env["sa"]
    mark(env, s1, mohammed, "ABSENT")
    mark(env, s2, mohammed, "ABSENT")
    mark(env, s1, khaled, "ABSENT")
    mark(env, s1, saad, "ABSENT")
    mark(env, s2, saad, "LATE", minutes=5)
    # ‏b: الأولى فقط معتمدة وفيها غائب — الفصل ناقص لاختيار [1,2]
    sb1 = make_session(env, env["b"], 1)
    mark(env, sb1, env["sb"][0], "ABSENT")
    return env


@pytest.mark.django_db
def test_all_absent_matching(multi_env):
    env = multi_env
    report = multi(env, [1, 2])
    assert names(report) == [env["sa"][0].full_name]  # محمد فقط
    statuses = report["students"][0]["period_statuses"]
    assert statuses == [
        {"sequence": 1, "status": "ABSENT"},
        {"sequence": 2, "status": "ABSENT"},
    ]


@pytest.mark.django_db
def test_incomplete_section_excludes_students_entirely(multi_env):
    """‏b معتمد الأولى فقط → غائبه لا يدخل نتيجة [1,2] ويعلن الفصل ناقصًا (113)."""
    env = multi_env
    report = multi(env, [1, 2])
    assert env["sb"][0].full_name not in names(report)
    ids = [s["section_id"] for s in report["incomplete_sections"]]
    assert env["b"].id in ids
    missing = next(s for s in report["incomplete_sections"] if s["section_id"] == env["b"].id)
    assert missing["missing_sequences"] == [2]


@pytest.mark.django_db
def test_any_absent_matching(multi_env):
    env = multi_env
    report = multi(env, [1, 2], match="ANY_ABSENT")
    # الكل غائب في الأولى على الأقل — لكن فقط طلاب الفصول المكتملة
    assert sorted(names(report)) == sorted(s.full_name for s in env["sa"])
    saad_row = next(s for s in report["students"] if s["student_id"] == env["sa"][2].id)
    assert {"sequence": 2, "status": "LATE"} in saad_row["period_statuses"]


@pytest.mark.django_db
def test_single_period_only_ignores_other_marks(multi_env):
    """اختيار الأولى وحدها: الثلاثة غائبون فيها + غائب b (فصل مكتمل للأولى)."""
    env = multi_env
    report = multi(env, [1])
    assert report["summary"]["matching_students"] == 4


@pytest.mark.django_db
def test_selection_validation(env):
    with pytest.raises(ApiError) as exc:
        multi(env, [])
    assert exc.value.code == "INVALID_PERIOD_SELECTION"
    with pytest.raises(ApiError) as exc:
        multi(env, [999])
    assert exc.value.error_details["unknown_sequences"] == [999]
    # التكرار يطبع: [1,1,2] == [1,2]
    make_session(env, env["a"], 1)
    make_session(env, env["a"], 2)
    normalized = multi(env, [2, 1, 1])
    assert [p["sequence"] for p in normalized["periods"]] == [1, 2]


@pytest.mark.django_db
def test_sorting_and_pagination(multi_env):
    env = multi_env
    # غائب من الصف الثاني أيضًا — الترتيب: تسلسل الصف ثم الفصل ثم الاسم
    sc1 = make_session(env, env["c"], 1)
    mark(env, sc1, env["sc"][0], "ABSENT")
    report = multi(env, [1], page=1, page_size=25)
    grades = [s["grade_name"] for s in report["students"]]
    assert grades == sorted(grades, key=lambda g: 0 if g == "الأول الثانوي" else 1)
    page2 = multi(env, [1], page=2, page_size=25)
    assert page2["students"] == []  # ما بعد النتائج — صفحة فارغة لا خطأ


# ---------- ملخص اليوم (البنود 41-58، 115-119) ----------


def build_full_day(env, absent_map, *, periods=PERIOD_COUNT):
    """يبني جلسات معتمدة لكل الحصص مع علامات لكل طالب حسب الخريطة."""
    for seq in range(1, periods + 1):
        session = make_session(env, env["a"], seq)
        for student, spec in absent_map.items():
            state = spec.get(seq)
            if state == "A":
                mark(env, session, student, "ABSENT")
            elif isinstance(state, int):
                mark(env, session, student, "LATE", minutes=state)


@pytest.mark.django_db
def test_daily_full_partial_none_late(env):
    mohammed, khaled, saad = env["sa"]
    build_full_day(
        env,
        {
            mohammed: dict.fromkeys(range(1, 8), "A"),  # غائب اليوم كله
            khaled: {3: "A", 4: "A"},  # غياب جزئي
            saad: {1: 12, 2: 18, 5: 7},  # تأخر فقط
        },
    )
    recalculate_daily_attendance_for_section(
        school=env["school"], section=env["a"], attendance_date=DAY
    )
    rows = {r.student_id: r for r in DailyAttendanceSummary.objects.filter(school=env["school"])}
    full = rows[mohammed.id]
    assert full.absence_status == "FULL" and full.absent_periods == 7
    partial = rows[khaled.id]
    assert partial.absence_status == "PARTIAL" and partial.absent_periods == 2
    assert partial.present_periods == 5
    late = rows[saad.id]
    assert late.absence_status == "NONE"  # التأخر لا يحول اليوم إلى غياب (البند 51)
    assert late.late_periods == 3 and late.total_late_minutes == 37
    assert late.present_periods + late.absent_periods + late.late_periods == 7

    report = get_daily_report(school=env["school"], attendance_date=DAY)
    assert report["summary"]["full_absent"] == 1
    assert report["summary"]["partial_absent"] == 1
    assert report["summary"]["late_students"] == 1
    assert report["summary"]["late_occurrences"] == 3
    assert report["summary"]["late_minutes"] == 37


@pytest.mark.django_db
def test_incomplete_day_undetermined_then_full(env):
    """‏6/7 حصص: غائب الستة → UNDETERMINED لا FULL؛ اعتماد السابعة يقلبه FULL (118-119)."""
    mohammed = env["sa"][0]
    build_full_day(env, {mohammed: dict.fromkeys(range(1, 7), "A")}, periods=6)
    recalculate_daily_attendance_for_section(
        school=env["school"], section=env["a"], attendance_date=DAY
    )
    row = DailyAttendanceSummary.objects.get(student=mohammed)
    assert row.completeness_status == "INCOMPLETE"
    assert row.absence_status == "UNDETERMINED"
    assert row.absent_periods == 6  # الغيابات المعروفة تعرض — الحكم فقط مؤجل

    seventh = make_session(env, env["a"], 7)
    mark(env, seventh, mohammed, "ABSENT")
    recalculate_daily_attendance_for_section(
        school=env["school"], section=env["a"], attendance_date=DAY
    )
    row.refresh_from_db()
    assert row.completeness_status == "COMPLETE"
    assert row.absence_status == "FULL"


@pytest.mark.django_db
def test_recalculation_idempotent(env):
    mohammed = env["sa"][0]
    build_full_day(env, {mohammed: {1: "A"}}, periods=2)
    for _ in range(10):
        recalculate_daily_attendance_for_section(
            school=env["school"], section=env["a"], attendance_date=DAY
        )
    rows = DailyAttendanceSummary.objects.filter(school=env["school"], student=mohammed)
    assert rows.count() == 1
    assert rows.get().absent_periods == 1


# ---------- التاريخية (البنود 8-15، 120-121) ----------


@pytest.mark.django_db
def test_schedule_change_does_not_rewrite_history(env):
    """تغيير الجدول بعد أسبوع لا يغير expected_periods ليوم مضى (120)."""
    build_full_day(env, {env["sa"][0]: {1: "A"}}, periods=7)
    recalculate_daily_attendance_for_section(
        school=env["school"], section=env["a"], attendance_date=DAY
    )
    assert DailyAttendanceSummary.objects.first().expected_periods == 7

    # المدرسة تقلص الجدول إلى 6 حصص
    BellPeriod.objects.filter(school=env["school"], sequence=7).delete()
    recalculate_daily_attendance_for_section(
        school=env["school"], section=env["a"], attendance_date=DAY
    )
    assert DailyAttendanceSummary.objects.first().expected_periods == 7  # snapshot ثابت
    context = AttendanceDayContext.objects.get(school=env["school"], attendance_date=DAY)
    assert len(context.attendance_periods) == 7


@pytest.mark.django_db
def test_start_session_refreshes_read_only_stale_day_context(env, monkeypatch):
    """زيارة التحليلات قبل ضبط يوم الدراسة لا تثبت لقطة فارغة إلى الأبد."""
    from attendance.services.sessions import start_session

    context = AttendanceDayContext.objects.create(
        school=env["school"],
        academic_year=env["year"],
        attendance_date=DAY,
        schedule_snapshot={"schedule_name": None, "is_school_day": False, "periods": []},
        timezone_snapshot="Asia/Riyadh",
    )
    period = env["schedule"].periods.filter(is_attendance_period=True).first()
    monkeypatch.setattr(
        "attendance.services.sessions.get_current_attendance_period",
        lambda _school: (period, DAY),
    )
    start_session(school=env["school"], membership=env["membership"], section=env["a"])
    context.refresh_from_db()
    assert context.schedule_snapshot["is_school_day"] is True
    assert len(context.attendance_periods) == PERIOD_COUNT


@pytest.mark.django_db
def test_period_sequence_snapshot_immutable(make_school, make_user, make_membership):
    """تغيير BellPeriod.sequence بعد الجلسة لا يمس period_sequence المخزن (121، 14-15)."""
    from attendance.services.sessions import start_session
    from tests.attendance_helpers import setup_attendance_env

    school = make_school()
    env2 = setup_attendance_env(school, students_count=1)
    membership = make_membership(make_user("0550000801"), school, ["TEACHER"])
    session, _, _ = start_session(school=school, membership=membership, section=env2["section"])
    original = session.period_sequence
    env2["period"].sequence = 55
    env2["period"].save(update_fields=["sequence"])
    session.refresh_from_db()
    assert session.period_sequence == original
    assert session.bell_period_snapshot["sequence"] == original


@pytest.mark.django_db
def test_submit_and_edit_update_summaries_synchronously(make_school, make_user, make_membership):
    """الاعتماد والتعديل يحدثان الملخص فورًا: A→L→P تنقل العدادات (103-105، 60-61)."""
    from attendance.services.sessions import edit_session, start_session, submit_session
    from tests.attendance_helpers import setup_attendance_env

    school = make_school()
    env2 = setup_attendance_env(school, students_count=2)
    membership = make_membership(make_user("0550000802"), school, ["TEACHER"])
    target = env2["students"][0]
    session, _, _ = start_session(school=school, membership=membership, section=env2["section"])
    submit_session(
        session_id=session.id,
        school=school,
        membership=membership,
        marks=[{"student_id": target.id, "status": "ABSENT"}],
    )
    row = DailyAttendanceSummary.objects.get(student=target)
    assert (row.absent_periods, row.late_periods) == (1, 0)
    other = DailyAttendanceSummary.objects.get(student=env2["students"][1])
    assert other.absence_status == "NONE"  # حاضر واليوم مكتمل (حصة واحدة متوقعة)

    # ‏ABSENT → LATE
    from datetime import timedelta

    arrival = (env2["local_now"] + timedelta(minutes=5)).time().replace(microsecond=0)
    edit_session(
        session_id=session.id,
        school=school,
        membership=membership,
        roles=["TEACHER"],
        marks=[{"student_id": target.id, "status": "LATE", "arrival_time": arrival}],
        reason="وصل متأخرًا",
    )
    row.refresh_from_db()
    assert (row.absent_periods, row.late_periods) == (0, 1)
    assert row.total_late_minutes >= 0

    # ‏LATE → PRESENT
    edit_session(
        session_id=session.id,
        school=school,
        membership=membership,
        roles=["TEACHER"],
        marks=[],
        reason="تصحيح",
    )
    row.refresh_from_db()
    assert (row.absent_periods, row.late_periods, row.total_late_minutes) == (0, 0, 0)
    assert row.absence_status == "NONE"


# ---------- القيد التاريخي (البنود 64-66، 107-110) ----------


@pytest.mark.django_db
def test_enrollment_history_bounds(env):
    from datetime import date as date_cls

    late_joiner = make_students(env["school"], env["a"], env["year"], 1, prefix="20900")[0]
    enrollment = late_joiner.enrollments.get()
    enrollment.enrolled_at = date_cls(2026, 8, 25)
    enrollment.save(update_fields=["enrolled_at"])

    build_full_day(env, {}, periods=7)
    recalculate_daily_attendance_for_section(
        school=env["school"], section=env["a"], attendance_date=DAY
    )
    # المنضم في 25 أغسطس لا صف له يوم 23 (البند 108)
    assert not DailyAttendanceSummary.objects.filter(student=late_joiner).exists()


@pytest.mark.django_db
def test_transfer_keeps_historical_section(env):
    """النقل بعد التاريخ لا يغير فصل التقرير القديم (109-110)."""
    from datetime import date as date_cls

    mohammed = env["sa"][0]
    build_full_day(env, {mohammed: {1: "A"}}, periods=7)
    recalculate_daily_attendance_for_section(
        school=env["school"], section=env["a"], attendance_date=DAY
    )
    assert DailyAttendanceSummary.objects.get(student=mohammed).section_id == env["a"].id

    # نقل يوم 25: إنهاء القديم + قيد جديد في b (نمط الاستيراد نفسه)
    old = mohammed.enrollments.get()
    old.status = "TRANSFERRED"
    old.ended_at = date_cls(2026, 8, 25)
    old.save(update_fields=["status", "ended_at"])
    mohammed.enrollments.create(
        school=env["school"],
        academic_year=env["year"],
        grade=env["grade"],
        section=env["b"],
        enrolled_at=date_cls(2026, 8, 25),
    )

    # إعادة بناء يوم 23 بعد النقل — الفصل التاريخي يبقى a
    recalculate_daily_attendance_for_section(
        school=env["school"], section=env["a"], attendance_date=DAY
    )
    assert DailyAttendanceSummary.objects.get(student=mohammed).section_id == env["a"].id


# ---------- الأدوار والعزل وPII (البنود 87-88، 122-125) ----------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("roles", "expected"),
    [
        (["SCHOOL_MANAGER"], 200),
        (["VICE_PRINCIPAL"], 200),
        (["TEACHER"], 403),
        (["COUNSELOR"], 403),
        (["TEACHER", "VICE_PRINCIPAL"], 200),
    ],
)
def test_analytics_roles(role_client, roles, expected):
    client, school, _ = role_client(roles)
    AcademicYear.objects.create(
        school=school,
        name="ع",
        start_date=DAY,
        end_date=datetime(2027, 6, 25).date(),
        status=AcademicYearStatus.ACTIVE,
    )
    # المدرسة بلا جدول لذلك اليوم: المصرح له يصل 200 (daily) أو 400 حصة غير معروفة
    # (period/multi — تجاوز التفويض ثم فشل التحقق)؛ الممنوع يرفض 403 قبل كل شيء
    daily = client.get(f"/api/v1/attendance/analytics/daily/?date={DAY}")
    assert daily.status_code == (200 if expected == 200 else 403)
    period = client.get(f"/api/v1/attendance/analytics/period/?date={DAY}&period=1")
    assert period.status_code == (400 if expected == 200 else 403)
    response = client.post(
        "/api/v1/attendance/analytics/multi-period/",
        {"date": str(DAY), "period_sequences": [1], "match": "ALL_ABSENT"},
        content_type="application/json",
    )
    assert response.status_code == (400 if expected == 200 else 403)


@pytest.mark.django_db
def test_tenant_isolation_and_pii(env, role_client):
    """مدير مدرسة أخرى لا يرى بيانات env — ولا PII في أي استجابة تحليلات."""
    s1 = make_session(env, env["a"], 1)
    mark(env, s1, env["sa"][0], "ABSENT")

    # مدير في مدرسة env يرى النتيجة بلا رقم هوية أو جوال ولي أمر
    manager_client, _, _ = role_client(["SCHOOL_MANAGER"], school=env["school"])
    response = manager_client.post(
        "/api/v1/attendance/analytics/multi-period/",
        {"date": str(DAY), "period_sequences": [1], "match": "ALL_ABSENT"},
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.content.decode()
    assert env["sa"][0].full_name in body
    assert env["sa"][0].national_id_masked not in body
    assert "national_id" not in body and "guardian" not in body

    daily = manager_client.get(f"/api/v1/attendance/analytics/daily/?date={DAY}")
    assert daily.status_code == 200
    daily_body = daily.content.decode()
    assert "national_id" not in daily_body and "guardian" not in daily_body


@pytest.mark.django_db
def test_foreign_school_sees_nothing(env, role_client):
    s1 = make_session(env, env["a"], 1)
    mark(env, s1, env["sa"][0], "ABSENT")
    foreign_client, foreign_school, _ = role_client(["SCHOOL_MANAGER"])
    AcademicYear.objects.create(
        school=foreign_school,
        name="ع",
        start_date=DAY,
        end_date=datetime(2027, 6, 25).date(),
        status=AcademicYearStatus.ACTIVE,
    )
    response = foreign_client.post(
        "/api/v1/attendance/analytics/multi-period/",
        {"date": str(DAY), "period_sequences": [1], "match": "ALL_ABSENT"},
        content_type="application/json",
    )
    # مدرسة بلا جدول لهذا اليوم → الحصة غير معروفة (لا تسرب من مدرسة env)
    assert response.status_code == 400
    assert env["sa"][0].full_name not in response.content.decode()


@pytest.mark.django_db
def test_purge_deletes_student_data_keeps_context(env):
    """الحذف النهائي: علامات+تعديلات+ملخصات تحذف؛ الجلسات وسياق اليوم يبقيان (124)."""
    from students.services.purge import purge_student

    mohammed = env["sa"][0]
    s1 = make_session(env, env["a"], 1)
    mark(env, s1, mohammed, "ABSENT")
    recalculate_daily_attendance_for_section(
        school=env["school"], section=env["a"], attendance_date=DAY
    )
    assert DailyAttendanceSummary.objects.filter(student=mohammed).exists()

    mohammed.status = "WITHDRAWN"
    mohammed.save(update_fields=["status"])
    purge_student(student=mohammed)

    assert not DailyAttendanceSummary.objects.filter(student_id=mohammed.id).exists()
    assert not AttendanceMark.objects.filter(student_id=mohammed.id).exists()
    assert AttendanceSession.objects.filter(id=s1.id).exists()
    assert AttendanceDayContext.objects.filter(school=env["school"]).exists()
    # التحليلات لا تعيد إظهاره ولا تنكسر
    report = multi(env, [1])
    assert report["summary"]["matching_students"] == 0


@pytest.mark.django_db
def test_unregistered_summary_purge_fails_loudly(env, monkeypatch):
    from django.db.models import ProtectedError

    from students.services import purge as purge_service

    mohammed = env["sa"][0]
    build_full_day(env, {mohammed: {1: "A"}}, periods=1)
    recalculate_daily_attendance_for_section(
        school=env["school"], section=env["a"], attendance_date=DAY
    )
    mohammed.status = "WITHDRAWN"
    mohammed.save(update_fields=["status"])

    stripped = [step for step in purge_service.PURGE_STEPS if step[0] != "ملخصات الحضور اليومية"]
    monkeypatch.setattr(purge_service, "PURGE_STEPS", stripped)
    with pytest.raises(ProtectedError):
        purge_service.purge_student(student=mohammed)


@pytest.mark.django_db
def test_multi_period_query_count_stable(env, django_assert_max_num_queries):
    """عدد الاستعلامات لا يتبع عدد الطلاب (94-95، 100)."""
    extra = make_students(env["school"], env["a"], env["year"], 30, prefix="20800")
    s1 = make_session(env, env["a"], 1)
    s2 = make_session(env, env["a"], 2)
    for student in extra:
        mark(env, s1, student, "ABSENT")
        mark(env, s2, student, "ABSENT")

    multi(env, [1, 2])  # تهيئة سياق اليوم
    with django_assert_max_num_queries(10):
        report = multi(env, [1, 2])
    assert report["summary"]["matching_students"] == 30
