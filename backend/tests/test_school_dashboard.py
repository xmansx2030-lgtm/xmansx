"""اختبارات لوحة إدارة المدرسة (م15) — صحة الأرقام والدلالات لا مجرد الاستجابة.

الاختبارات تبني بيانات حقيقية عبر خدمات المراحل السابقة (لا تلفيق صفوف ملخص
يدويًا حيثما أمكن) حتى تُثبت أن اللوحة تقرأ من مصدر الحقيقة نفسه.
"""

from datetime import date, datetime, time, timedelta
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
from common.errors import ApiError
from devices.models import ArrivalSource, ArrivalStatus, SchoolArrival
from school_dashboard.ranges import compare, resolve_range, resolve_scope
from school_dashboard.selectors import attendance as attendance_selectors
from school_dashboard.selectors import attention as attention_selectors
from school_dashboard.selectors import followup as followup_selectors
from students.models import Grade, Section
from tests.attendance_helpers import make_students

TZ = ZoneInfo("Asia/Riyadh")
DAY = date(2026, 8, 16)      # أحد
DAY2 = date(2026, 8, 17)     # اثنين
PERIOD_COUNT = 7


class Range:
    """نطاق بسيط للاختبارات — نفس واجهة DateRange."""

    def __init__(self, from_date, to_date, preset="CUSTOM"):
        self.from_date = from_date
        self.to_date = to_date
        self.preset = preset

    @property
    def days(self):
        return (self.to_date - self.from_date).days + 1

    def previous(self):
        end = self.from_date - timedelta(days=1)
        return Range(end - timedelta(days=self.days - 1), end, self.preset)

    def as_dict(self):
        return {
            "from_date": self.from_date.isoformat(),
            "to_date": self.to_date.isoformat(),
            "days": self.days,
            "preset": self.preset,
        }


@pytest.fixture
def env(make_school, make_user, make_membership):
    school = make_school()
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
    section_b = Section.objects.create(school=school, grade=grade, code="2", name="2")
    students = make_students(school, section, year, 5, prefix="90100")
    teacher = make_membership(make_user("0551500001"), school, ["TEACHER"])
    vice = make_membership(make_user("0551500002"), school, ["VICE_PRINCIPAL"])
    return {
        "school": school, "year": year, "grade": grade, "section": section,
        "section_b": section_b, "students": students, "teacher": teacher, "vice": vice,
    }


def make_session(env, seq, *, day=DAY, section=None, status="SUBMITTED"):
    return AttendanceSession.objects.create(
        school=env["school"], academic_year=env["year"],
        section=section or env["section"], attendance_date=day, period_sequence=seq,
        bell_period_snapshot={
            "sequence": seq, "name": f"الحصة {seq}",
            "start_time": f"{6 + seq:02d}:00", "end_time": f"{6 + seq:02d}:45",
            "attendance_date": day.isoformat(), "timezone": "Asia/Riyadh",
        },
        status=status, roster_fingerprint="fp", unprepared_alert_minutes_snapshot=25,
        started_by_membership=env["teacher"],
        submitted_by_membership=env["teacher"] if status == "SUBMITTED" else None,
        submitted_at=datetime(2026, 8, 16, 6 + seq, 10, tzinfo=TZ)
        if status == "SUBMITTED" else None,
    )


def mark(env, session, student, status):
    return AttendanceMark.objects.create(
        school=env["school"], session=session, student=student, status=status,
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
    return sessions


def arrival(env, student, *, day=DAY, late_minutes=12):
    return SchoolArrival.objects.create(
        school=env["school"], student=student, attendance_date=day,
        first_arrival_at=datetime(day.year, day.month, day.day, 7, 15, tzinfo=TZ),
        raw_late_minutes=late_minutes + 5, counted_late_minutes=late_minutes,
        status=ArrivalStatus.LATE if late_minutes else ArrivalStatus.ON_TIME,
        source=ArrivalSource.BIOMETRIC,
    )


# ---------- تصنيف الطلاب (السيناريو 152) ----------


@pytest.mark.django_db
def test_each_student_lands_in_exactly_one_bucket(env):
    """A كامل بدون عذر · B كامل بعذر · C جزئي · D غير مكتمل · E متأخر صباحيًا."""
    from excuses.services.coverage import approve_excuse, resolve_coverage_plan
    from excuses.services.excuses import create_excuse

    a, b, c, _d, e = env["students"]
    for seq in range(1, PERIOD_COUNT + 1):
        session = make_session(env, seq)
        mark(env, session, a, "ABSENT")
        mark(env, session, b, "ABSENT")
        if seq in (2, 3):
            mark(env, session, c, "ABSENT")
    arrival(env, e, late_minutes=12)
    recalc(env)

    # اليوم الناقص في فصل مستقل: إعادة الحساب تنشئ صفًا لكل طلاب الفصل، فخلطه
    # مع الفصل المكتمل يجعل كل طلابه UNDETERMINED
    incomplete_student = make_students(
        env["school"], env["section_b"], env["year"], 1, prefix="90300"
    )[0]
    session = make_session(env, 1, section=env["section_b"])
    mark(env, session, incomplete_student, "ABSENT")
    recalc(env, section=env["section_b"])

    # B يحصل على عذر يوم كامل معتمد
    excuse = create_excuse(
        school=env["school"], membership=env["vice"], student=b,
        reason_type="MEDICAL_REPORT", notes="",
        targets=[{"attendance_date": DAY}],
    )
    plan = resolve_coverage_plan(excuse)
    approve_excuse(
        excuse_id=excuse.id, school=env["school"], membership=env["vice"],
        preview_hash=plan["preview_hash"],
    )

    kpis = attendance_selectors.attendance_kpis(
        school=env["school"], date_range=Range(DAY, DAY2)
    )
    assert kpis["full_absence_days"] == 2            # A و B
    assert kpis["unexcused_full_absence_days"] == 1  # A فقط
    assert kpis["excused_full_absence_days"] == 1    # B فقط
    assert kpis["partial_absence_days"] == 1         # C
    assert kpis["no_absence_days"] == 2              # D و E حضرا
    assert kpis["undetermined_days"] == 1            # اليوم الناقص — ليس غيابًا
    assert kpis["morning_late_occurrences"] == 1     # E


@pytest.mark.django_db
def test_mixed_full_day_counted_in_neither_bucket(env):
    """يوم كامل مختلط لا يُعرض «بدون عذر» ولا «بعذر» (بند 24)."""
    from excuses.services.coverage import approve_excuse, resolve_coverage_plan
    from excuses.services.excuses import create_excuse

    student = env["students"][0]
    full_day_absent(env, student)
    recalc(env)
    excuse = create_excuse(
        school=env["school"], membership=env["vice"], student=student,
        reason_type="MEDICAL_REPORT", notes="",
        targets=[{"attendance_date": DAY, "period_sequence": 1}],
    )
    plan = resolve_coverage_plan(excuse)
    approve_excuse(
        excuse_id=excuse.id, school=env["school"], membership=env["vice"],
        preview_hash=plan["preview_hash"],
    )

    kpis = attendance_selectors.attendance_kpis(
        school=env["school"], date_range=Range(DAY, DAY)
    )
    assert kpis["full_absence_days"] == 1
    assert kpis["mixed_full_absence_days"] == 1
    assert kpis["unexcused_full_absence_days"] == 0
    assert kpis["excused_full_absence_days"] == 0


@pytest.mark.django_db
def test_undetermined_never_counted_as_absence(env):
    student = env["students"][0]
    session = make_session(env, 1)
    mark(env, session, student, "ABSENT")
    recalc(env)
    kpis = attendance_selectors.attendance_kpis(
        school=env["school"], date_range=Range(DAY, DAY)
    )
    # كل طلاب الفصل الخمسة يومهم ناقص (حصة واحدة من سبع) — ولا أحد منهم «غائب»
    assert kpis["undetermined_days"] == 5
    assert kpis["full_absence_days"] == 0
    assert kpis["partial_absence_days"] == 0
    assert kpis["completeness"]["incomplete_student_days"] == 5
    assert kpis["completeness"]["incomplete_pct"] == 100.0
    assert kpis["completeness"]["is_significant"] is True


@pytest.mark.django_db
def test_live_attendance_snapshot_is_current_and_excludes_unsubmitted_sections(env):
    """الحصة مستقلة، والاستئذان ليس عذر غياب، والتأخر الصباحي عداد منفصل."""
    from excuses.services.coverage import approve_excuse, resolve_coverage_plan
    from excuses.services.excuses import create_excuse
    from student_leaves.models import StudentLeavePermission

    continuously_absent, absent_then_present, present_now, second_present, leave_now = (
        env["students"]
    )
    for seq in (1, 2):
        session = make_session(env, seq)
        mark(env, session, continuously_absent, "ABSENT")
        if seq == 1:
            mark(env, session, absent_then_present, "ABSENT")
            mark(env, session, second_present, "ABSENT")
        else:
            mark(env, session, leave_now, "ABSENT")

    StudentLeavePermission.objects.create(
        school=env["school"], student=leave_now, leave_date=DAY,
        leave_time=time(8, 15), reason="موعد رسمي",
        recorded_by_membership=env["vice"],
    )
    # عذر غياب معتمد للحصة الحالية يبقى في «غائب في الحصة»، ولا يتحول إلى
    # «مستأذن الآن»؛ فالاستئذان سجل خروج مستقل تمامًا.
    excuse = create_excuse(
        school=env["school"], membership=env["vice"], student=continuously_absent,
        reason_type="MEDICAL_REPORT", notes="",
        targets=[{"attendance_date": DAY, "period_sequence": 2}],
    )
    plan = resolve_coverage_plan(excuse)
    approve_excuse(
        excuse_id=excuse.id, school=env["school"], membership=env["vice"],
        preview_hash=plan["preview_hash"],
    )
    arrival(env, absent_then_present, late_minutes=7)
    StudentLeavePermission.objects.create(
        school=env["school"], student=absent_then_present, leave_date=DAY,
        leave_time=time(9, 0), reason="خروج لاحق",
        recorded_by_membership=env["vice"],
    )

    # فصل نشط آخر اعتمد الحصة الحالية فقط: يدخل في أرقام الحصة فورًا، لكنه لا
    # يدخل في «غائب اليوم» حتى يكتمل تحضيره من بداية اليوم.
    make_students(env["school"], env["section_b"], env["year"], 1, prefix="90400")
    make_session(env, 2, section=env["section_b"])

    snapshot = attendance_selectors.live_attendance_snapshot(
        school=env["school"], attendance_date=DAY, current_period_sequence=2,
        current_time=time(8, 30),
    )

    assert snapshot == {
        "status": "AVAILABLE",
        "total_students": 6,
        "covered_students": 6,
        "pending_students": 0,
        "present_students": 4,
        "absent_students": 1,
        "leave_students": 1,
        "morning_late_students": 1,
        "daily_absent_students": 1,
        "daily_covered_students": 5,
        "daily_pending_sections": 1,
        "covered_sections": 2,
        "pending_sections": 0,
        "current_period_sequence": 2,
    }


@pytest.mark.django_db
def test_dashboard_keeps_daily_presence_continuous_absence_and_leave_distinct(env):
    """نموذج مصغر: حضر سابقًا ثم استأذن لا يضيع من حضور اليوم ولا يصبح غائبًا."""
    from student_leaves.models import StudentLeavePermission

    _present_one, _present_two, left_after_attending, absent_one, absent_two = env["students"]
    first = make_session(env, 1)
    second = make_session(env, 2)
    for student in (absent_one, absent_two):
        mark(env, first, student, "ABSENT")
        mark(env, second, student, "ABSENT")
    mark(env, second, left_after_attending, "ABSENT")
    StudentLeavePermission.objects.create(
        school=env["school"], student=left_after_attending, leave_date=DAY,
        leave_time=time(8, 15), reason="خروج أثناء اليوم",
        recorded_by_membership=env["vice"],
    )
    recalc(env)

    daily = attendance_selectors.daily_attendance_snapshot(
        school=env["school"], attendance_date=DAY
    )
    live = attendance_selectors.live_attendance_snapshot(
        school=env["school"], attendance_date=DAY, current_period_sequence=2,
        current_time=time(8, 30),
    )

    assert daily["total_students"] == 5
    assert daily["present_students"] == 3
    assert live["daily_absent_students"] == 2
    assert live["leave_students"] == 1
    assert live["present_students"] == 2
    assert live["absent_students"] == 2


@pytest.mark.django_db
def test_live_attendance_snapshot_has_no_status_outside_an_active_period(env):
    snapshot = attendance_selectors.live_attendance_snapshot(
        school=env["school"], attendance_date=DAY, current_period_sequence=None
    )
    assert snapshot["status"] == "NO_ACTIVE_PERIOD"
    assert snapshot["total_students"] == 0


@pytest.mark.django_db
def test_daily_attendance_counts_proven_presence_not_every_prepared_student(env):
    """الحضور إثبات حضور فعلي، وليس كل من شملهم التحضير ومنهم الغائب."""
    always_absent, *_ = env["students"]
    session = make_session(env, 1)
    mark(env, session, always_absent, "ABSENT")
    recalc(env)
    # فصل بلا أي جلسة لا يُعد حاضرًا ولا غائبًا.
    make_students(env["school"], env["section_b"], env["year"], 1, prefix="90500")

    snapshot = attendance_selectors.daily_attendance_snapshot(
        school=env["school"], attendance_date=DAY
    )

    assert snapshot == {
        "total_students": 6,
        "present_students": 4,
        "absent_students": 1,
        "unrecorded_students": 1,
    }

    # تصحيح الغائب إلى حاضر يحدث ملخص اليوم فورًا، بلا اعتماد على حصة جارية.
    from attendance.services.sessions import edit_session
    from school_dashboard.cache import build_key

    cache_parts = {"roles": ["VICE_PRINCIPAL"]}
    before_cache_key = build_key(
        school_id=env["school"].id, section="today", parts=cache_parts
    )

    edit_session(
        session_id=session.id,
        school=env["school"],
        membership=env["vice"],
        roles=["VICE_PRINCIPAL"],
        marks=[],
        reason="تصحيح حالة الطالب",
    )
    corrected = attendance_selectors.daily_attendance_snapshot(
        school=env["school"], attendance_date=DAY
    )
    assert corrected["present_students"] == 5
    assert corrected["absent_students"] == 0
    assert build_key(
        school_id=env["school"].id, section="today", parts=cache_parts
    ) != before_cache_key


@pytest.mark.django_db
def test_daily_attendance_accepts_morning_arrival_as_presence_proof(env):
    student = make_students(
        env["school"], env["section_b"], env["year"], 1, prefix="90600"
    )[0]
    arrival(env, student, late_minutes=0)

    snapshot = attendance_selectors.daily_attendance_snapshot(
        school=env["school"], attendance_date=DAY
    )

    assert snapshot == {
        "total_students": 6,
        "present_students": 1,
        "absent_students": 0,
        "unrecorded_students": 5,
    }


# ---------- الاتجاه والفصول ----------


@pytest.mark.django_db
def test_trend_has_one_point_per_day(env):
    student = env["students"][0]
    full_day_absent(env, student, day=DAY)
    full_day_absent(env, student, day=DAY2)
    recalc(env, day=DAY)
    recalc(env, day=DAY2)
    trend = attendance_selectors.attendance_trend(
        school=env["school"], date_range=Range(DAY, DAY2)
    )
    assert trend["granularity"] == "DAY"
    assert [point["date"] for point in trend["points"]] == [
        DAY.isoformat(), DAY2.isoformat()
    ]
    assert trend["points"][0]["unexcused_full_absence"] == 1


@pytest.mark.django_db
def test_section_breakdown_and_scope_filter(env):
    """الفلتر يقصر الأرقام على الفصل المحدد."""
    other_students = make_students(
        env["school"], env["section_b"], env["year"], 2, prefix="90200"
    )
    full_day_absent(env, env["students"][0])
    for seq in range(1, PERIOD_COUNT + 1):
        session = make_session(env, seq, section=env["section_b"])
        mark(env, session, other_students[0], "ABSENT")
    recalc(env)
    recalc(env, section=env["section_b"])

    breakdown = attendance_selectors.section_breakdown(
        school=env["school"], date_range=Range(DAY, DAY)
    )
    assert len(breakdown["sections"]) == 2

    scoped = attendance_selectors.attendance_kpis(
        school=env["school"], date_range=Range(DAY, DAY),
        scope={"section_id": env["section"].id},
    )
    assert scoped["unexcused_full_absence_days"] == 1
    assert scoped["distinct_students"] == 5  # طلاب هذا الفصل فقط


@pytest.mark.django_db
def test_historical_section_attribution(env):
    """طالب نُقل لاحقًا يبقى محسوبًا على فصله وقت الغياب (بند 61/155)."""
    student = env["students"][0]
    full_day_absent(env, student, day=DAY)
    recalc(env)
    # نقل الطالب إلى فصل آخر بعد ذلك اليوم
    enrollment = student.enrollments.first()
    enrollment.ended_at = DAY2
    # القيد الجزئي يسمح بقيد ACTIVE واحد لكل عام — القديم يصبح «منقول»
    enrollment.status = "TRANSFERRED"
    enrollment.save(update_fields=["ended_at", "status"])
    from students.models import StudentEnrollment

    StudentEnrollment.objects.create(
        school=env["school"], student=student, academic_year=env["year"],
        grade=env["grade"], section=env["section_b"], enrolled_at=DAY2,
    )

    scoped_old = attendance_selectors.attendance_kpis(
        school=env["school"], date_range=Range(DAY, DAY),
        scope={"section_id": env["section"].id},
    )
    scoped_new = attendance_selectors.attendance_kpis(
        school=env["school"], date_range=Range(DAY, DAY),
        scope={"section_id": env["section_b"].id},
    )
    assert scoped_old["unexcused_full_absence_days"] == 1
    assert scoped_new["unexcused_full_absence_days"] == 0


# ---------- الإنذارات والإجراءات والإحالات ----------


@pytest.mark.django_db
def test_warning_due_and_issued_stay_separate(env):
    """مستحق ≠ صادر (بند 35/96)."""
    from student_warnings.services.issuance import issue_student_warning

    student = env["students"][0]
    for offset in range(3):
        day = DAY - timedelta(days=offset * 7)
        for seq in range(1, PERIOD_COUNT + 1):
            session = make_session(env, seq, day=day)
            mark(env, session, student, "ABSENT")
        recalc(env, day=day)

    metrics = followup_selectors.warning_metrics(
        school=env["school"], date_range=Range(DAY - timedelta(days=30), DAY)
    )
    assert metrics["due_students_by_type"].get("UNEXCUSED_FULL_DAY_ABSENCE") == 1
    assert metrics["issued_in_range"]["total"] == 0

    issue_student_warning(
        school=env["school"], membership=env["vice"], student=student,
        warning_type="UNEXCUSED_FULL_DAY_ABSENCE", level="LEVEL_1",
    )
    after = followup_selectors.warning_metrics(
        school=env["school"], date_range=Range(DAY - timedelta(days=30), date.today())
    )
    assert after["issued_in_range"]["total"] == 1
    assert after["issued_in_range"]["level_1"] == 1
    assert after["issued_students_by_type"].get("UNEXCUSED_FULL_DAY_ABSENCE") == 1


@pytest.mark.django_db
def test_action_and_referral_metrics(env):
    """إحالة ≠ حالة إرشادية، والإجراءات عدّاد نشاط فقط (بنود 39/97)."""
    from referrals.services.referrals import create_referral
    from student_actions.services import create_student_action

    student = env["students"][0]
    create_student_action(
        school=env["school"], membership=env["vice"], student=student,
        action_type="PARENT_CONTACT", notes="اتصال",
    )
    create_referral(
        school=env["school"], membership=env["vice"], roles=["VICE_PRINCIPAL"],
        student=student, category="ATTENDANCE", reason_code="REPEATED_ABSENCE",
        description="غياب متكرر.",
    )
    today_range = Range(date.today(), date.today())

    actions = followup_selectors.action_metrics(school=env["school"], date_range=today_range)
    assert actions["total"] >= 1
    assert actions["by_type"]["PARENT_CONTACT"] >= 1

    referrals = followup_selectors.referral_metrics(
        school=env["school"], date_range=today_range
    )
    assert referrals["created_in_range"]["total"] == 1
    assert referrals["created_in_range"]["new"] == 1
    assert referrals["open_now"] == 1
    assert referrals["unassigned_now"] == 1
    assert referrals["by_category"]["ATTENDANCE"] == 1
    assert referrals["by_source"]["VICE_PRINCIPAL"] == 1


@pytest.mark.django_db
def test_counseling_seam_reports_aggregates_only(env):
    """م14 مدمجة: الفاصل يعيد أعدادًا حقيقية — ولا نص إرشادي في اللوحة."""
    metrics = followup_selectors.counseling_metrics(
        school=env["school"], date_range=Range(DAY, DAY)
    )
    assert metrics["available"] is True
    assert metrics["open_cases"] == 0
    assert metrics["waiting_teacher_responses"] == 0
    assert metrics["overdue_activities"] == 0
    # أعداد فقط — لا مفاتيح نصية حساسة
    for forbidden in ("notes", "summary", "description", "question"):
        assert forbidden not in metrics


@pytest.mark.django_db
def test_case_and_teacher_request_move_dashboard_counters(env, make_user, make_membership):
    """تكامل م14←م15: فتح حالة يرفع العداد، والرد يخفض «بانتظار رد معلم»."""
    from counseling.services.cases import open_counselor_case
    from counseling.services.teacher_requests import (
        request_teacher_follow_up,
        respond_to_request,
    )
    from referrals.models import ReferralCategory, ReferralReason
    from referrals.services.referrals import acknowledge_referral, create_referral

    school = env["school"]
    counselor = make_membership(make_user("0551500009"), school, ["COUNSELOR"])
    student = env["students"][0]
    today = date.today()
    today_range = Range(today, today)

    before = followup_selectors.counseling_metrics(school=school, date_range=today_range)
    assert before["open_cases"] == 0

    referral = create_referral(
        school=school, membership=env["vice"], roles=["VICE_PRINCIPAL"], student=student,
        category=ReferralCategory.ATTENDANCE,
        reason_code=ReferralReason.REPEATED_ABSENCE,
        description="غياب متكرر يحتاج متابعة إرشادية مستمرة.",
        assigned_counselor_id=counselor.id,
    )
    acknowledge_referral(
        referral_id=referral.id, school=school, membership=counselor, roles=["COUNSELOR"]
    )
    case = open_counselor_case(
        school=school, membership=counselor, roles=["COUNSELOR"], referral_id=referral.id
    )

    after_open = followup_selectors.counseling_metrics(school=school, date_range=today_range)
    assert after_open["open_cases"] == before["open_cases"] + 1
    assert after_open["waiting_teacher_responses"] == 0
    # الإحالة والحالة عددان مستقلان لا يُدمجان
    referrals = followup_selectors.referral_metrics(school=school, date_range=today_range)
    assert referrals["created_in_range"]["total"] == 1

    follow_up = request_teacher_follow_up(
        case=case, membership=counselor, roles=["COUNSELOR"],
        teacher_membership_id=env["teacher"].id,
        request_type="CLASSROOM_BEHAVIOR",
        question="كيف كان تفاعله هذا الأسبوع؟",
    )
    waiting = followup_selectors.counseling_metrics(school=school, date_range=today_range)
    assert waiting["waiting_teacher_responses"] == 1

    respond_to_request(
        school=school, membership=env["teacher"], request_id=follow_up.id,
        observation="تحسن حضوره وتفاعله في الحصص.",
        improvement_status="IMPROVED",
    )
    answered = followup_selectors.counseling_metrics(school=school, date_range=today_range)
    assert answered["waiting_teacher_responses"] == 0
    assert answered["open_cases"] == after_open["open_cases"]


# ---------- طابور «يحتاج متابعة» ----------


@pytest.mark.django_db
def test_attention_queue_collects_operational_items(env):
    from excuses.services.excuses import create_excuse
    from referrals.services.referrals import create_referral

    student = env["students"][0]
    full_day_absent(env, student)
    recalc(env)
    create_excuse(
        school=env["school"], membership=env["vice"], student=student,
        reason_type="MEDICAL_REPORT", notes="",
        targets=[{"attendance_date": DAY}],
    )
    create_referral(
        school=env["school"], membership=env["vice"], roles=["VICE_PRINCIPAL"],
        student=student, category="ATTENDANCE", reason_code="REPEATED_ABSENCE",
        description="غياب.",
    )
    queue = attention_selectors.attention_queue(school=env["school"])
    kinds = {item["kind"] for item in queue["items"]}
    assert "EXCUSE_PENDING" in kinds
    assert "REFERRAL_UNASSIGNED" in kinds
    # كل عنصر يحمل هدف تنقل ونوع كيان — طابور عمل لا تصنيف طلاب
    for item in queue["items"]:
        assert item["target_url"]
        assert item["entity_type"] in {"SECTION", "STUDENT", "EXCUSE", "REFERRAL", "CASE"}
        assert item["priority"] in {"HIGH", "NORMAL"}


def test_submitted_late_section_is_history_not_an_open_attention_item(monkeypatch):
    monkeypatch.setattr(
        attention_selectors,
        "get_current_section_attendance_statuses",
        lambda **_kwargs: {
            "sections": [
                {
                    "section_id": 1,
                    "grade_name": "الأول الثانوي",
                    "section_name": "أ",
                    "attendance_status": "SUBMITTED",
                    "timeliness_status": "OVERDUE",
                    "minutes_overdue": 4,
                },
                {
                    "section_id": 2,
                    "grade_name": "الأول الثانوي",
                    "section_name": "ب",
                    "attendance_status": "NOT_STARTED",
                    "timeliness_status": "OVERDUE",
                    "minutes_overdue": 4,
                },
            ]
        },
    )

    items = attention_selectors.overdue_sections(school=object())

    assert [item["entity_id"] for item in items] == [2]
    assert items[0]["reason_code"] == "SECTION_NOT_SUBMITTED"


@pytest.mark.django_db
def test_today_operations_is_on_track_when_all_sections_submitted_late(env, monkeypatch):
    from attendance.selectors import monitoring as monitoring_selectors

    monkeypatch.setattr(
        monitoring_selectors,
        "get_current_section_attendance_statuses",
        lambda **_kwargs: {
            "school_time": "2026-08-16T09:15:00+03:00",
            "date": DAY.isoformat(),
            "period": {
                "sequence": 3,
                "name": "الحصة الثالثة",
                "start_time": "09:00",
                "end_time": "09:45",
                "timezone": "Asia/Riyadh",
            },
            "alert": {"minutes": 5, "alert_at": "09:05"},
            "summary": {
                "total": 2,
                "submitted": 2,
                "in_progress": 0,
                "not_started": 0,
                "overdue_total": 1,
                "overdue_submitted": 1,
                "overdue_in_progress": 0,
                "overdue_not_started": 0,
            },
            "sections": [],
        },
    )

    result = attendance_selectors.today_operations(school=env["school"])

    assert result["operational_state"] == "ON_TRACK"
    assert "اكتمل تحضير جميع فصول" in result["headline"]
    assert "اعتمد 1 فصل متأخرًا" in result["headline"]


# ---------- النطاقات والمقارنة ----------


@pytest.mark.django_db
def test_range_presets_and_previous_period(env):
    school = env["school"]
    today_range = resolve_range(school=school, params={"preset": "TODAY"})
    assert today_range.days == 1
    week = resolve_range(school=school, params={"preset": "LAST_7_DAYS"})
    assert week.days == 7
    previous = week.previous()
    assert previous.days == 7                      # فترتان متساويتان دائمًا
    assert previous.to_date == week.from_date - timedelta(days=1)


@pytest.mark.django_db
def test_invalid_ranges_rejected(env):
    school = env["school"]
    with pytest.raises(ApiError) as exc:
        resolve_range(school=school, params={"from_date": "abc", "to_date": "2026-08-16"})
    assert exc.value.code == "DASHBOARD_INVALID_DATE_RANGE"

    with pytest.raises(ApiError) as exc:
        resolve_range(
            school=school, params={"from_date": "2026-08-20", "to_date": "2026-08-01"}
        )
    assert exc.value.code == "DASHBOARD_INVALID_DATE_RANGE"

    with pytest.raises(ApiError) as exc:
        resolve_range(
            school=school, params={"from_date": "2020-01-01", "to_date": "2026-08-01"}
        )
    assert exc.value.code == "DASHBOARD_RANGE_TOO_LARGE"


def test_comparison_never_divides_by_zero():
    assert compare(5, 0)["change_pct"] is None
    assert compare(5, 0)["is_new"] is True
    assert compare(0, 0)["is_new"] is False
    assert compare(42, 50)["change_pct"] == -16.0
    assert compare(50, 40)["change_pct"] == 25.0


@pytest.mark.django_db
def test_scope_rejects_foreign_ids(env, make_school):
    other = make_school()
    other_grade = Grade.objects.create(school=other, name="صف", code="X", sequence=1)
    with pytest.raises(ApiError) as exc:
        resolve_scope(school=env["school"], params={"grade": other_grade.id})
    assert exc.value.code == "DASHBOARD_INVALID_GRADE"

    with pytest.raises(ApiError) as exc:
        resolve_scope(school=env["school"], params={"grade": "abc"})
    assert exc.value.code == "DASHBOARD_INVALID_GRADE"
