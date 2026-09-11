"""اختبارات نطاق الأعذار (م10) — التصنيف الإداري لا يمس سجل الحضور الخام أبدًا."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from academics.models import (
    AcademicYearStatus,
)
from attendance.models import (
    AttendanceMark,
    AttendanceMarkStatus,
    AttendanceSession,
    DailyAbsenceStatus,
    DailyAttendanceSummary,
)
from attendance.services.daily_summary import recalculate_daily_attendance_for_section
from attendance.services.sessions import edit_session
from common.errors import ApiError
from excuses.models import (
    AbsenceExcuse,
    AbsenceExcuseCoverage,
    AbsenceExcuseStatus,
    ExcuseCoverageStatus,
)
from excuses.selectors import (
    EXCUSED,
    UNEXCUSED,
    count_excused_full_absence_days,
    count_unexcused_absent_periods,
    count_unexcused_full_absence_days,
    get_effective_absence_classification,
)
from excuses.services.coverage import (
    approve_excuse,
    cancel_excuse,
    reconcile_excuse_coverage_for_date,
    resolve_coverage_plan,
)
from excuses.services.excuses import create_excuse, reject_excuse
from students.models import Grade, Section
from tests.attendance_helpers import make_students

TZ = ZoneInfo("Asia/Riyadh")
DAY = datetime(2026, 8, 16).date()  # أحد ماضٍ (اليوم المرجعي 2026-08-19)
DAY2 = datetime(2026, 8, 17).date()  # اثنين
PERIOD_COUNT = 7


@pytest.fixture
def env(make_school, make_user, make_membership):
    """نفس البيئة السابقة حرفيًا — استخرجت إلى tests/excuse_env.py لتشاركها م11."""
    from tests.excuse_env import build_env

    school = make_school()
    return build_env(
        school=school,
        teacher_membership=make_membership(make_user("0550000900"), school, ["TEACHER"]),
        vice_membership=make_membership(
            make_user("0550000901"), school, ["VICE_PRINCIPAL"]
        ),
    )


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


def summary(env, student, *, day=DAY):
    return DailyAttendanceSummary.objects.get(
        school=env["school"], student=student, attendance_date=day
    )


# ---------- التصنيف الافتراضي والفعال (البنود 117-119) ----------


@pytest.mark.django_db
def test_absent_without_excuse_is_unexcused(env):
    student = env["students"][0]
    sessions = full_day_absent(env, student)
    assert get_effective_absence_classification(
        student=student, attendance_session=sessions[0]
    ) == UNEXCUSED
    row = summary(env, student)
    assert row.excused_absent_periods == 0
    assert row.unexcused_absent_periods == PERIOD_COUNT


@pytest.mark.django_db
def test_approved_full_day_excuse_classifies_excused(env):
    student = env["students"][0]
    sessions = full_day_absent(env, student)
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    approve(env, excuse)
    assert get_effective_absence_classification(
        student=student, attendance_session=sessions[0]
    ) == EXCUSED
    row = summary(env, student)
    assert row.excused_absent_periods == PERIOD_COUNT
    assert row.unexcused_absent_periods == 0
    assert row.absence_status == DailyAbsenceStatus.FULL  # الحقيقة لا تتغير


@pytest.mark.django_db
def test_raw_attendance_marks_unchanged_after_approval(env):
    student = env["students"][0]
    full_day_absent(env, student)
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    approve(env, excuse)
    statuses = set(
        AttendanceMark.objects.filter(student=student).values_list("status", flat=True)
    )
    assert statuses == {AttendanceMarkStatus.ABSENT}  # اختبار إلزامي (بند 119)


@pytest.mark.django_db
def test_partial_period_excuse(env):
    student = env["students"][0]
    for seq in range(1, PERIOD_COUNT + 1):
        session = make_session(env, seq)
        if seq in (2, 3, 5):
            mark(env, session, student, "ABSENT")
    recalc(env)
    excuse = excuse_for(env, student, [
        {"attendance_date": DAY, "period_sequence": 2},
        {"attendance_date": DAY, "period_sequence": 3},
    ])
    approve(env, excuse)
    row = summary(env, student)
    assert row.absent_periods == 3
    assert row.excused_absent_periods == 2
    assert row.unexcused_absent_periods == 1


@pytest.mark.django_db
def test_multi_day_excuse_covers_only_actual_absences(env):
    student = env["students"][0]
    full_day_absent(env, student, day=DAY)
    # اليوم الثاني: غياب حصتين فقط والبقية حضور
    for seq in range(1, PERIOD_COUNT + 1):
        session = make_session(env, seq, day=DAY2)
        if seq in (1, 2):
            mark(env, session, student, "ABSENT")
    recalc(env, day=DAY2)
    excuse = excuse_for(env, student, [
        {"attendance_date": DAY}, {"attendance_date": DAY2},
    ])
    approve(env, excuse)
    assert AbsenceExcuseCoverage.objects.filter(
        excuse=excuse, status=ExcuseCoverageStatus.ACTIVE
    ).count() == PERIOD_COUNT + 2
    assert summary(env, student, day=DAY2).excused_absent_periods == 2


@pytest.mark.django_db
def test_present_periods_are_not_covered(env):
    student = env["students"][0]
    for seq in range(1, PERIOD_COUNT + 1):
        session = make_session(env, seq)
        if seq == 1:
            mark(env, session, student, "ABSENT")
        # البقية حاضر (لا علامة)
    recalc(env)
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    approve(env, excuse)
    coverages = AbsenceExcuseCoverage.objects.filter(excuse=excuse)
    assert coverages.count() == 1
    assert coverages.first().period_sequence_snapshot == 1
    assert summary(env, student).excused_absent_periods == 1


@pytest.mark.django_db
def test_incomplete_day_preview_and_partial_coverage(env):
    student = env["students"][0]
    # 4 جلسات معتمدة غياب + 3 حصص لم تحضر
    for seq in range(1, 5):
        session = make_session(env, seq)
        mark(env, session, student, "ABSENT")
    recalc(env)
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    plan = resolve_coverage_plan(excuse)
    assert plan["days"][0]["missing_periods"] == 3
    assert plan["days"][0]["complete"] is False
    approve(env, excuse)
    assert AbsenceExcuseCoverage.objects.filter(excuse=excuse).count() == 4
    row = summary(env, student)
    assert row.absence_status == DailyAbsenceStatus.UNDETERMINED  # العذر لا يكمل التحضير


@pytest.mark.django_db
def test_later_session_submit_expands_coverage(env):
    """‏Session جديدة تعتمد بعد اعتماد عذر Full-Day — التغطية تتوسع (بند 56/126)."""
    student = env["students"][0]
    for seq in range(1, PERIOD_COUNT):
        session = make_session(env, seq)
        mark(env, session, student, "ABSENT")
    recalc(env)
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    approve(env, excuse)
    assert AbsenceExcuseCoverage.objects.filter(excuse=excuse).count() == PERIOD_COUNT - 1

    # الحصة الأخيرة تعتمد الآن والطالب غائب فيها — reconcile كما في hook الاعتماد
    session = make_session(env, PERIOD_COUNT)
    mark(env, session, student, "ABSENT")
    reconcile_excuse_coverage_for_date(school=env["school"], attendance_date=DAY)
    recalc(env)
    assert AbsenceExcuseCoverage.objects.filter(
        excuse=excuse, status=ExcuseCoverageStatus.ACTIVE
    ).count() == PERIOD_COUNT
    row = summary(env, student)
    assert row.excused_absent_periods == PERIOD_COUNT
    assert row.unexcused_absent_periods == 0
    assert row.absence_status == DailyAbsenceStatus.FULL


@pytest.mark.django_db
def test_attendance_edit_absent_to_present_voids_coverage(env):
    student = env["students"][0]
    sessions = full_day_absent(env, student)
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    approve(env, excuse)

    # تصحيح إداري: الحصة الأولى تصبح حضورًا (حذف العلامة = PRESENT)
    other_marks = [
        {"student_id": m.student_id, "status": m.status}
        for m in sessions[0].marks.exclude(student=student)
    ]
    edit_session(
        session_id=sessions[0].id, school=env["school"], membership=env["vice"],
        roles=["VICE_PRINCIPAL"], marks=other_marks, reason="تصحيح",
    )
    voided = AbsenceExcuseCoverage.objects.get(
        excuse=excuse, attendance_session=sessions[0]
    )
    assert voided.status == ExcuseCoverageStatus.VOIDED
    assert voided.void_reason == "ATTENDANCE_CHANGED"
    row = summary(env, student)
    assert row.absent_periods == PERIOD_COUNT - 1
    assert row.excused_absent_periods == PERIOD_COUNT - 1
    assert row.unexcused_absent_periods == 0


@pytest.mark.django_db
def test_attendance_edit_present_to_absent_creates_coverage(env):
    """ترتيب الإجراءات لا يهم (بند 55): العذر أولًا ثم التصحيح إلى غياب."""
    student = env["students"][0]
    sessions = []
    for seq in range(1, PERIOD_COUNT + 1):
        session = make_session(env, seq)
        if seq > 1:
            mark(env, session, student, "ABSENT")
        sessions.append(session)
    recalc(env)
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    approve(env, excuse)
    assert AbsenceExcuseCoverage.objects.filter(excuse=excuse).count() == PERIOD_COUNT - 1

    edit_session(
        session_id=sessions[0].id, school=env["school"], membership=env["vice"],
        roles=["VICE_PRINCIPAL"],
        marks=[{"student_id": student.id, "status": "ABSENT"}],
        reason="تصحيح إلى غياب",
    )
    assert AbsenceExcuseCoverage.objects.filter(
        excuse=excuse, status=ExcuseCoverageStatus.ACTIVE
    ).count() == PERIOD_COUNT
    row = summary(env, student)
    assert row.unexcused_absent_periods == 0


@pytest.mark.django_db
def test_cancel_excuse_voids_and_restores_unexcused(env):
    student = env["students"][0]
    full_day_absent(env, student)
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    approve(env, excuse)
    cancel_excuse(
        excuse_id=excuse.id, school=env["school"], membership=env["vice"],
        reason="تقرير غير صحيح",
    )
    excuse.refresh_from_db()
    assert excuse.status == AbsenceExcuseStatus.CANCELLED
    assert not AbsenceExcuseCoverage.objects.filter(
        excuse=excuse, status=ExcuseCoverageStatus.ACTIVE
    ).exists()
    row = summary(env, student)
    assert row.excused_absent_periods == 0
    assert row.unexcused_absent_periods == PERIOD_COUNT


@pytest.mark.django_db
def test_rejected_excuse_has_no_effect(env):
    student = env["students"][0]
    full_day_absent(env, student)
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    reject_excuse(
        excuse_id=excuse.id, school=env["school"], membership=env["vice"],
        reason="بلا مستند",
    )
    excuse.refresh_from_db()
    assert excuse.status == AbsenceExcuseStatus.REJECTED
    assert not AbsenceExcuseCoverage.objects.exists()
    assert summary(env, student).unexcused_absent_periods == PERIOD_COUNT


@pytest.mark.django_db
def test_overlapping_approved_excuse_rejected(env):
    student = env["students"][0]
    full_day_absent(env, student)
    first = excuse_for(env, student, [{"attendance_date": DAY}])
    approve(env, first)
    second = excuse_for(env, student, [{"attendance_date": DAY, "period_sequence": 3}])
    plan = resolve_coverage_plan(second)
    with pytest.raises(ApiError) as exc:
        approve_excuse(
            excuse_id=second.id, school=env["school"], membership=env["vice"],
            preview_hash=plan["preview_hash"],
        )
    assert exc.value.code == "ABSENCE_ALREADY_EXCUSED"
    second.refresh_from_db()
    assert second.status == AbsenceExcuseStatus.PENDING


@pytest.mark.django_db
def test_double_approval_idempotent(env):
    student = env["students"][0]
    full_day_absent(env, student)
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    plan = resolve_coverage_plan(excuse)
    approve_excuse(
        excuse_id=excuse.id, school=env["school"], membership=env["vice"],
        preview_hash=plan["preview_hash"],
    )
    with pytest.raises(ApiError) as exc:
        approve_excuse(
            excuse_id=excuse.id, school=env["school"], membership=env["vice"],
            preview_hash=plan["preview_hash"],
        )
    assert exc.value.code == "EXCUSE_ALREADY_APPROVED"
    assert AbsenceExcuseCoverage.objects.filter(excuse=excuse).count() == PERIOD_COUNT


@pytest.mark.django_db
def test_concurrent_approval_blocked_by_db_constraint(env):
    """طلبان متزامنان لا ينتجان تغطيتين نشطتين لنفس الغياب — القيد الجزئي يحسم."""
    from django.db import IntegrityError, transaction

    student = env["students"][0]
    sessions = full_day_absent(env, student)
    first = excuse_for(env, student, [{"attendance_date": DAY}])
    approve(env, first)

    second = excuse_for(env, student, [{"attendance_date": DAY}])
    with pytest.raises(IntegrityError), transaction.atomic():
        AbsenceExcuseCoverage.objects.create(
            school=env["school"], excuse=second, student=student,
            attendance_session=sessions[0], attendance_date=DAY,
            period_sequence_snapshot=1,
        )
    assert AbsenceExcuseCoverage.objects.filter(
        attendance_session=sessions[0], status=ExcuseCoverageStatus.ACTIVE
    ).count() == 1


@pytest.mark.django_db
def test_pending_overlap_allowed_until_approval(env):
    """التداخل مسموح في PENDING (بند 43) — يحسم عند الاعتماد."""
    student = env["students"][0]
    full_day_absent(env, student)
    first = excuse_for(env, student, [{"attendance_date": DAY}])
    second = excuse_for(env, student, [{"attendance_date": DAY, "period_sequence": 2}])
    assert first.status == AbsenceExcuseStatus.PENDING
    assert second.status == AbsenceExcuseStatus.PENDING
    plan = resolve_coverage_plan(second)
    assert plan["already_excused"] == []  # لا شيء معتمد بعد
    approve(env, first)
    # الآن معاينة الثاني تحذر: الغياب مغطى مسبقًا
    assert len(resolve_coverage_plan(second)["already_excused"]) == 1


@pytest.mark.django_db
def test_reconcile_scoped_to_affected_students(env):
    """‏Reconcile لا يمس طلابًا بلا أعذار ولا تغطيات (بند 57)."""
    covered_student, other = env["students"][0], env["students"][1]
    for seq in range(1, PERIOD_COUNT + 1):
        session = make_session(env, seq)
        mark(env, session, covered_student, "ABSENT")
        mark(env, session, other, "ABSENT")
    recalc(env)
    excuse = excuse_for(env, covered_student, [{"attendance_date": DAY}])
    approve(env, excuse)

    affected = reconcile_excuse_coverage_for_date(
        school=env["school"], attendance_date=DAY
    )
    assert affected == set()  # لا تغيير: الحالة متسقة أصلًا
    assert summary(env, other).unexcused_absent_periods == PERIOD_COUNT
    assert not AbsenceExcuseCoverage.objects.filter(student=other).exists()


@pytest.mark.django_db
def test_cross_school_target_cannot_be_covered(env, make_school, make_user, make_membership):
    """عذر مدرسة A لا يغطي جلسة مدرسة B (بند 150)."""
    from academics.models import AcademicYear as AY

    student = env["students"][0]
    full_day_absent(env, student)
    school_b = make_school()
    year_b = AY.objects.create(
        school=school_b, name="2026/2027", start_date=datetime(2026, 8, 1).date(),
        end_date=datetime(2027, 6, 25).date(), status=AcademicYearStatus.ACTIVE,
    )
    grade_b = Grade.objects.create(school=school_b, name="أول", code="G1", sequence=1)
    section_b = Section.objects.create(school=school_b, grade=grade_b, code="1", name="1")
    student_b = make_students(school_b, section_b, year_b, 1, prefix="30900")[0]
    teacher_b = make_membership(make_user("0550000999"), school_b, ["TEACHER"])
    session_b = AttendanceSession.objects.create(
        school=school_b, academic_year=year_b, section=section_b,
        attendance_date=DAY, period_sequence=1, bell_period_snapshot={},
        status="SUBMITTED", roster_fingerprint="fp",
        unprepared_alert_minutes_snapshot=25, started_by_membership=teacher_b,
        submitted_by_membership=teacher_b,
        submitted_at=datetime(2026, 8, 16, 8, 0, tzinfo=TZ),
    )
    AttendanceMark.objects.create(
        school=school_b, session=session_b, student=student_b, status="ABSENT"
    )
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    approve(env, excuse)
    # التغطيات كلها ضمن مدرسة العذر فقط
    assert set(
        AbsenceExcuseCoverage.objects.filter(excuse=excuse).values_list(
            "school_id", flat=True
        )
    ) == {env["school"].id}
    assert not AbsenceExcuseCoverage.objects.filter(attendance_session=session_b).exists()


@pytest.mark.django_db
def test_cancel_reconciles_to_other_approved_excuse(env):
    """إلغاء عذر لا يترك الغياب «بدون عذر» إن كان عذر معتمد آخر يغطيه."""
    student = env["students"][0]
    # يوم لم تعتمد فيه أي جلسة بعد → عذران معتمدان بلا تغطية (يوم ناقص)
    first = excuse_for(env, student, [{"attendance_date": DAY}])
    approve(env, first)
    second = excuse_for(env, student, [{"attendance_date": DAY}], reason="FAMILY")
    approve(env, second)

    # الآن تعتمد الحصص والطالب غائب → المواءمة تغطي بالأقدم (first)
    full_day_absent(env, student)
    reconcile_excuse_coverage_for_date(school=env["school"], attendance_date=DAY)
    recalc(env)
    assert summary(env, student).excused_absent_periods == PERIOD_COUNT

    cancel_excuse(
        excuse_id=first.id, school=env["school"], membership=env["vice"],
        reason="مستند غير صحيح",
    )
    # العذر الثاني ما زال معتمدًا ويغطي نفس الغياب — لا يعود «بدون عذر»
    row = summary(env, student)
    assert row.excused_absent_periods == PERIOD_COUNT
    assert row.unexcused_absent_periods == 0
    assert AbsenceExcuseCoverage.objects.filter(
        excuse=second, status=ExcuseCoverageStatus.ACTIVE
    ).count() == PERIOD_COUNT


@pytest.mark.django_db
def test_preview_hash_bound_to_targets(env):
    """تبديل الأهداف بعد المعاينة يبطلها — لا اعتماد نطاق لم يشاهده المعتمد."""
    from excuses.services.excuses import update_excuse

    student = env["students"][0]
    full_day_absent(env, student)
    excuse = excuse_for(env, student, [{"attendance_date": DAY, "period_sequence": 1}])
    plan = resolve_coverage_plan(excuse)

    update_excuse(
        excuse_id=excuse.id, school=env["school"], membership=env["vice"],
        targets=[{"attendance_date": DAY}],  # يوم كامل بدل حصة واحدة
    )
    with pytest.raises(ApiError) as exc:
        approve_excuse(
            excuse_id=excuse.id, school=env["school"], membership=env["vice"],
            preview_hash=plan["preview_hash"],
        )
    assert exc.value.code == "EXCUSE_PREVIEW_STALE"


@pytest.mark.django_db
def test_preview_hash_differs_between_excuses(env):
    """بصمة النطاق الفارغ ليست ثابتًا عالميًا يصلح لاعتماد أي عذر بلا معاينة."""
    student = env["students"][0]
    first = excuse_for(env, student, [{"attendance_date": DAY}])
    second = excuse_for(env, env["students"][1], [{"attendance_date": DAY}])
    assert (
        resolve_coverage_plan(first)["preview_hash"]
        != resolve_coverage_plan(second)["preview_hash"]
    )


@pytest.mark.django_db
def test_stale_coverage_not_misattributed_to_another_absence(env):
    """تغطية بقيت لجلسة لم يعد الطالب غائبًا فيها لا تُنسب لغياب آخر."""
    student = env["students"][0]
    sessions = full_day_absent(env, student, periods=2)
    excuse = excuse_for(env, student, [
        {"attendance_date": DAY, "period_sequence": 1},
    ])
    approve(env, excuse)

    # حالة فساد: العلامة الأولى تصبح حضورًا مباشرة في DB بلا مواءمة
    AttendanceMark.objects.filter(session=sessions[0], student=student).delete()
    recalc(env)

    row = summary(env, student)
    assert row.absent_periods == 1          # الحصة الثانية فقط
    assert row.excused_absent_periods == 0  # التغطية القديمة لا تُنسب إليها
    assert row.unexcused_absent_periods == 1


@pytest.mark.django_db
def test_future_target_rejected(env):
    student = env["students"][0]
    with pytest.raises(ApiError) as exc:
        excuse_for(env, student, [{"attendance_date": datetime(2030, 1, 1).date()}])
    assert exc.value.code == "EXCUSE_FUTURE_DATE_NOT_ALLOWED"


@pytest.mark.django_db
def test_full_day_plus_period_target_conflict_rejected(env):
    student = env["students"][0]
    with pytest.raises(ApiError) as exc:
        excuse_for(env, student, [
            {"attendance_date": DAY},
            {"attendance_date": DAY, "period_sequence": 3},
        ])
    assert exc.value.code == "EXCUSE_INVALID_TARGET"


@pytest.mark.django_db
def test_stale_preview_rejected(env):
    student = env["students"][0]
    sessions = full_day_absent(env, student)
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    plan = resolve_coverage_plan(excuse)

    # الحضور يتغير بين المعاينة والاعتماد
    other_marks = [
        {"student_id": m.student_id, "status": m.status}
        for m in sessions[0].marks.exclude(student=student)
    ]
    edit_session(
        session_id=sessions[0].id, school=env["school"], membership=env["vice"],
        roles=["VICE_PRINCIPAL"], marks=other_marks, reason="تصحيح",
    )
    with pytest.raises(ApiError) as exc:
        approve_excuse(
            excuse_id=excuse.id, school=env["school"], membership=env["vice"],
            preview_hash=plan["preview_hash"],
        )
    assert exc.value.code == "EXCUSE_PREVIEW_STALE"


@pytest.mark.django_db
def test_no_absence_found_on_complete_day(env):
    student = env["students"][0]
    for seq in range(1, PERIOD_COUNT + 1):
        make_session(env, seq)  # حاضر في كل الحصص
    recalc(env)
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    plan = resolve_coverage_plan(excuse)
    with pytest.raises(ApiError) as exc:
        approve_excuse(
            excuse_id=excuse.id, school=env["school"], membership=env["vice"],
            preview_hash=plan["preview_hash"],
        )
    assert exc.value.code == "EXCUSE_NO_ABSENCE_FOUND"


# ---------- ملخصات اليوم (البنود 136-140) ----------


@pytest.mark.django_db
def test_summary_invariant_for_all_rows(env):
    students = env["students"]
    for seq in range(1, PERIOD_COUNT + 1):
        session = make_session(env, seq)
        mark(env, session, students[0], "ABSENT")
        if seq <= 3:
            mark(env, session, students[1], "ABSENT")
    recalc(env)
    excuse = excuse_for(env, students[1], [
        {"attendance_date": DAY, "period_sequence": 1},
    ])
    approve(env, excuse)
    for row in DailyAttendanceSummary.objects.filter(school=env["school"]):
        assert (
            row.excused_absent_periods + row.unexcused_absent_periods
            == row.absent_periods
        )


@pytest.mark.django_db
def test_mixed_full_day_not_counted_in_either(env):
    student = env["students"][0]
    full_day_absent(env, student)
    excuse = excuse_for(env, student, [
        {"attendance_date": DAY, "period_sequence": 1},
        {"attendance_date": DAY, "period_sequence": 2},
    ])
    approve(env, excuse)
    row = summary(env, student)
    assert row.absence_status == DailyAbsenceStatus.FULL
    assert row.excused_absent_periods == 2
    assert row.unexcused_absent_periods == PERIOD_COUNT - 2
    assert count_excused_full_absence_days(school=env["school"], student=student) == 0
    assert count_unexcused_full_absence_days(school=env["school"], student=student) == 0


@pytest.mark.django_db
def test_phase11_selectors(env):
    student = env["students"][0]
    full_day_absent(env, student, day=DAY)
    full_day_absent(env, student, day=DAY2)
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    approve(env, excuse)
    assert count_excused_full_absence_days(school=env["school"], student=student) == 1
    assert count_unexcused_full_absence_days(school=env["school"], student=student) == 1
    assert count_unexcused_absent_periods(
        school=env["school"], student=student
    ) == PERIOD_COUNT


@pytest.mark.django_db
def test_undetermined_day_unaffected_by_excuse(env):
    student = env["students"][0]
    session = make_session(env, 1)
    mark(env, session, student, "ABSENT")
    recalc(env)
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    approve(env, excuse)
    row = summary(env, student)
    assert row.absence_status == DailyAbsenceStatus.UNDETERMINED  # لا يتحول FULL (بند 65)
    assert row.excused_absent_periods == 1


# ---------- الحذف النهائي (بند 104) ----------


@pytest.mark.django_db
def test_purge_deletes_excuse_data(env):
    from students.services.purge import purge_student

    student = env["students"][0]
    full_day_absent(env, student)
    excuse = excuse_for(env, student, [{"attendance_date": DAY}])
    approve(env, excuse)
    student.status = "WITHDRAWN"
    student.save(update_fields=["status"])

    deleted, _, _ = purge_student(student)
    assert deleted > 0
    assert not AbsenceExcuse.objects.filter(id=excuse.id).exists()
    assert not AbsenceExcuseCoverage.objects.filter(excuse_id=excuse.id).exists()
