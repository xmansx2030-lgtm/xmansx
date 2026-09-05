"""اختبارات الإنذارات (م11) — القواعد، الاستحقاق، الإصدار، Snapshot، الإلغاء، العزل.

يبني فوق مصانع م10 (نفس البيئة) ولا يعيد بناء منطق الغياب/الأعذار.
"""

from datetime import UTC, datetime, timedelta

import pytest

from attendance.models import DailyAbsenceStatus, DailyAttendanceSummary
from common.errors import ApiError
from devices.models import ArrivalSource, ArrivalStatus, SchoolArrival
from student_warnings.models import (
    StudentWarning,
    WarningLevel,
    WarningRuleType,
    WarningStatus,
)
from student_warnings.selectors.eligibility import (
    DUE,
    ISSUED,
    NOT_DUE,
    eligibility_dashboard,
    evaluate_student_warning_eligibility,
    get_warning_current_metric,
)
from student_warnings.services.issuance import (
    issue_student_warning,
    void_student_warning,
)
from student_warnings.services.rules import get_rules_map, update_rules
from tests.excuse_env import (  # بيئة م10 المشتركة — بلا إعادة بناء لمنطق الأعذار
    DAY,
    DAY2,
    PERIOD_COUNT,
    approve,
    build_env,
    excuse_for,
    make_session,
    mark,
    recalc,
)


@pytest.fixture
def env(make_school, make_user, make_membership):
    school = make_school()
    return build_env(
        school=school,
        teacher_membership=make_membership(make_user("0550000900"), school, ["TEACHER"]),
        vice_membership=make_membership(
            make_user("0550000901"), school, ["VICE_PRINCIPAL"]
        ),
    )

ABSENCE = WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE
MORNING = WarningRuleType.MORNING_LATE_OCCURRENCES


# ---------- أدوات ----------


def set_rules(env, rule_type, one, two, three, *, enabled=True):
    return update_rules(
        school=env["school"],
        actor=None,
        payload={rule_type: {"is_enabled": enabled, "levels": {
            "LEVEL_1": one, "LEVEL_2": two, "LEVEL_3": three,
        }}},
    )


def ensure_school_day(env, day):
    """بيئة م10 تعرّف الأحد/الاثنين فقط — أي يوم إضافي يحتاج تعريفًا وإلا صار
    «غير محسوم» (لا يحتسب في مقياس الغياب — وهو سلوك صحيح نتفاداه هنا عمدًا)."""
    from academics.models import BellSchedule, SchoolWeekDay
    from attendance.services.periods import _PY_TO_SCHOOL_WEEKDAY

    schedule = BellSchedule.objects.filter(school=env["school"]).first()
    SchoolWeekDay.objects.update_or_create(
        school=env["school"],
        weekday=_PY_TO_SCHOOL_WEEKDAY[day.weekday()],
        defaults={"is_school_day": True, "bell_schedule": schedule},
    )


def sessions_for_day(env, day):
    """جلسات اليوم السبع — تعاد استخدامها لعدة طلاب (قيد UNIQUE لكل فصل/يوم/حصة)."""
    from attendance.models import AttendanceSession

    ensure_school_day(env, day)
    result = []
    for seq in range(1, PERIOD_COUNT + 1):
        existing = AttendanceSession.objects.filter(
            school=env["school"], section=env["section"],
            attendance_date=day, period_sequence=seq,
        ).first()
        result.append(existing or make_session(env, seq, day=day))
    return result


def absence_days(env, student, count, *, start_day=DAY):
    """‏count أيام غياب كامل بدون عذر للطالب (تعمل مع عدة طلاب في نفس الأيام)."""
    for offset in range(count):
        day = start_day + timedelta(days=offset)
        for session in sessions_for_day(env, day):
            mark(env, session, student, "ABSENT")
        recalc(env, day=day)


def morning_late(env, student, count, *, start_day=DAY, status=ArrivalStatus.LATE):
    for offset in range(count):
        day = start_day + timedelta(days=offset)
        SchoolArrival.objects.create(
            school=env["school"], student=student, attendance_date=day,
            first_arrival_at=datetime(2026, 8, 16, 4, 18, tzinfo=UTC)
            + timedelta(days=offset),
            raw_late_minutes=18, counted_late_minutes=13,
            status=status, source=ArrivalSource.BIOMETRIC,
        )


def evaluate(env, student, rule_type=ABSENCE):
    return evaluate_student_warning_eligibility(
        school=env["school"], student=student
    )["types"][rule_type]


def issue(env, student, rule_type, level, membership=None):
    return issue_student_warning(
        school=env["school"], membership=membership or env["vice"],
        student=student, warning_type=rule_type, level=level,
    )


# ---------- القواعد (البنود 92-95، 13-18) ----------


@pytest.mark.django_db
def test_default_rules_are_created_and_isolated_per_school(env, make_school):
    rules = get_rules_map(school=env["school"])
    assert rules[ABSENCE]["levels"] == {"LEVEL_1": 3, "LEVEL_2": 5, "LEVEL_3": 10}
    assert rules[MORNING]["levels"] == {"LEVEL_1": 3, "LEVEL_2": 5, "LEVEL_3": 10}
    assert rules[ABSENCE]["is_enabled"] is True

    other = make_school("مدرسة ثانية")
    set_rules(env, ABSENCE, 2, 4, 7)
    assert get_rules_map(school=env["school"])[ABSENCE]["levels"]["LEVEL_1"] == 2
    # مدرسة أخرى تبقى على الافتراضي — عزل تام
    assert get_rules_map(school=other)[ABSENCE]["levels"]["LEVEL_1"] == 3


@pytest.mark.django_db
def test_threshold_order_validation(env):
    set_rules(env, ABSENCE, 3, 5, 10)  # ترتيب صحيح
    with pytest.raises(ApiError) as exc:
        set_rules(env, ABSENCE, 5, 3, 10)  # غير تصاعدي
    assert exc.value.code == "INVALID_WARNING_THRESHOLD_ORDER"
    with pytest.raises(ApiError) as exc:
        set_rules(env, ABSENCE, 3, 3, 10)  # تساوٍ مرفوض
    assert exc.value.code == "INVALID_WARNING_THRESHOLD_ORDER"
    with pytest.raises(ApiError) as exc:
        set_rules(env, ABSENCE, 0, 5, 10)  # أقل من 1
    assert exc.value.code == "INVALID_WARNING_THRESHOLD"
    # الفشل لم يترك قواعد متناقضة — القيم الأصلية سليمة (تحديث ذري)
    assert get_rules_map(school=env["school"])[ABSENCE]["levels"] == {
        "LEVEL_1": 3, "LEVEL_2": 5, "LEVEL_3": 10
    }


# ---------- استحقاق الغياب (البنود 96-103) ----------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("days", "expected_due"),
    [(2, None), (3, WarningLevel.LEVEL_1), (5, WarningLevel.LEVEL_2)],
)
def test_absence_eligibility_thresholds(env, days, expected_due):
    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, days)
    state = evaluate(env, student)
    assert state["current_value"] == days
    assert state["highest_due_level"] == expected_due


@pytest.mark.django_db
def test_excused_partial_and_undetermined_days_are_excluded(env):
    """بعذر/جزئي/غير محسوم لا تدخل مقياس الغياب الكامل بدون عذر (100-102)."""
    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    # يوم كامل بعذر معتمد
    absence_days(env, student, 1, start_day=DAY)
    approve(env, excuse_for(env, student, [{"attendance_date": DAY}]))
    # يوم جزئي: كل الحصص معتمدة والغياب في واحدة فقط
    partial_sessions = sessions_for_day(env, DAY2)
    mark(env, partial_sessions[0], student, "ABSENT")
    recalc(env, day=DAY2)
    # يوم غير محسوم: جلسة واحدة فقط ولم تعتمد
    third = DAY2 + timedelta(days=1)
    ensure_school_day(env, third)
    make_session(env, 1, day=third, status="IN_PROGRESS")
    recalc(env, day=third)

    state = evaluate(env, student)
    assert state["current_value"] == 0
    assert state["highest_due_level"] is None


@pytest.mark.django_db
def test_mixed_day_is_excluded_by_documented_policy(env):
    """يوم فيه غياب بعذر وبدون عذر معًا لا يحتسب كيوم كامل بدون عذر (البند 4)."""
    student = env["students"][0]
    set_rules(env, ABSENCE, 1, 2, 3)
    sessions = sessions_for_day(env, DAY)
    for session in sessions:
        mark(env, session, student, "ABSENT")
    recalc(env, day=DAY)
    approve(
        env,
        excuse_for(
            env, student,
            [{
                "attendance_date": DAY,
                "period_sequence": sessions[0].period_sequence,  # حصة واحدة فقط
            }],
        ),
    )
    row = DailyAttendanceSummary.objects.get(student=student, attendance_date=DAY)
    assert row.absence_status == DailyAbsenceStatus.FULL
    assert row.excused_absent_periods > 0 and row.unexcused_absent_periods > 0
    assert evaluate(env, student)["current_value"] == 0


# ---------- استحقاق التأخر الصباحي (البنود 104-108) ----------


@pytest.mark.django_db
def test_morning_late_metric_counts_occurrences_only(env):
    student = env["students"][0]
    set_rules(env, MORNING, 3, 5, 10)
    morning_late(env, student, 2)
    assert evaluate(env, student, MORNING)["highest_due_level"] is None
    morning_late(env, student, 1, start_day=DAY + timedelta(days=5))
    state = evaluate(env, student, MORNING)
    assert state["current_value"] == 3  # عدد المرات لا مجموع الدقائق
    assert state["highest_due_level"] == WarningLevel.LEVEL_1


@pytest.mark.django_db
def test_on_time_arrival_and_period_late_do_not_count(env):
    """الوصول في الوقت لا يحتسب، وتأخر الحصص عداد منفصل تمامًا (106-107)."""
    student = env["students"][0]
    set_rules(env, MORNING, 3, 5, 10)
    morning_late(env, student, 3, status=ArrivalStatus.ON_TIME)
    # ثلاث حالات تأخر حصص
    for seq in (1, 2, 3):
        session = make_session(env, seq, day=DAY2)
        mark(env, session, student, "LATE", minutes=9)
    recalc(env, day=DAY2)

    state = evaluate(env, student, MORNING)
    assert state["current_value"] == 0
    assert state["highest_due_level"] is None


@pytest.mark.django_db
def test_corrected_arrival_lowers_current_metric(env):
    student = env["students"][0]
    set_rules(env, MORNING, 3, 5, 10)
    morning_late(env, student, 3)
    assert evaluate(env, student, MORNING)["current_value"] == 3
    arrival = SchoolArrival.objects.filter(student=student).first()
    arrival.status = ArrivalStatus.ON_TIME
    arrival.counted_late_minutes = 0
    arrival.save(update_fields=["status", "counted_late_minutes"])
    assert evaluate(env, student, MORNING)["current_value"] == 2


# ---------- الإصدار (البنود 109-115، 43-47) ----------


@pytest.mark.django_db
def test_issue_level_1_creates_warning_with_snapshot(env):
    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, 3)
    morning_late(env, student, 2, start_day=DAY + timedelta(days=10))

    warning = issue(env, student, ABSENCE, WarningLevel.LEVEL_1)
    assert warning.status == WarningStatus.ISSUED
    assert warning.threshold_at_issue == 3
    assert warning.metric_value_at_issue == 3
    assert warning.student_name_snapshot == student.full_name
    assert warning.grade_name_snapshot == env["grade"].name
    assert warning.section_name_snapshot == env["section"].name
    assert warning.unexcused_full_absence_days_at_issue == 3
    # عدادان منفصلان في نفس الـsnapshot — لا جمع بينهما
    assert warning.morning_late_occurrences_at_issue == 2
    assert warning.period_late_occurrences_at_issue == 0
    assert warning.issued_by_membership_id == env["vice"].id
    assert warning.academic_year_id == env["year"].id
    assert len(warning.detail_rows_snapshot) == 3
    assert all(
        row["status"] == "غياب يوم دراسي كامل بدون عذر"
        for row in warning.detail_rows_snapshot
    )
    assert all(
        "arrival_time" not in row and "late_minutes" not in row
        for row in warning.detail_rows_snapshot
    )


@pytest.mark.django_db
def test_issue_morning_late_freezes_only_arrival_details(env):
    student = env["students"][0]
    set_rules(env, MORNING, 3, 5, 10)
    morning_late(env, student, 3)

    warning = issue(env, student, MORNING, WarningLevel.LEVEL_1)

    assert warning.metric_value_at_issue == 3
    assert len(warning.detail_rows_snapshot) == 3
    assert all(
        row["status"] == "تأخر عن بداية الدوام الصباحي"
        for row in warning.detail_rows_snapshot
    )
    assert all(
        row["arrival_time"] and row["late_minutes"] == 13
        for row in warning.detail_rows_snapshot
    )
    assert all("غياب" not in row["status"] for row in warning.detail_rows_snapshot)


@pytest.mark.django_db
def test_issue_does_not_modify_raw_data(env):
    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, 3)
    before = list(
        DailyAttendanceSummary.objects.filter(student=student).values_list(
            "absence_status", "unexcused_absent_periods", "excused_absent_periods"
        )
    )
    issue(env, student, ABSENCE, WarningLevel.LEVEL_1)
    after = list(
        DailyAttendanceSummary.objects.filter(student=student).values_list(
            "absence_status", "unexcused_absent_periods", "excused_absent_periods"
        )
    )
    assert before == after


@pytest.mark.django_db
def test_duplicate_and_double_click_produce_one_warning(env):
    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, 3)
    issue(env, student, ABSENCE, WarningLevel.LEVEL_1)
    with pytest.raises(ApiError) as exc:
        issue(env, student, ABSENCE, WarningLevel.LEVEL_1)
    assert exc.value.code == "WARNING_ALREADY_ISSUED"
    assert StudentWarning.objects.filter(student=student).count() == 1


@pytest.mark.django_db
def test_level_not_reached_and_disabled_rule_are_rejected(env):
    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, 2)
    with pytest.raises(ApiError) as exc:
        issue(env, student, ABSENCE, WarningLevel.LEVEL_1)
    assert exc.value.code == "WARNING_LEVEL_NOT_REACHED"
    assert exc.value.error_details["current_value"] == 2

    absence_days(env, student, 1, start_day=DAY + timedelta(days=5))
    set_rules(env, ABSENCE, 3, 5, 10, enabled=False)
    with pytest.raises(ApiError) as exc:
        issue(env, student, ABSENCE, WarningLevel.LEVEL_1)
    assert exc.value.code == "WARNING_TYPE_DISABLED"
    assert not StudentWarning.objects.filter(student=student).exists()


@pytest.mark.django_db
def test_level_2_due_independently_when_level_1_missing(env):
    """وصل للمستوى الثاني بلا إصدار الأول: كلاهما مستحق بشكل مستقل — لا إنشاء صامت."""
    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, 5)
    state = evaluate(env, student)
    assert state["levels"]["LEVEL_1"]["state"] == DUE
    assert state["levels"]["LEVEL_2"]["state"] == DUE
    assert state["levels"]["LEVEL_3"]["state"] == NOT_DUE
    assert state["highest_reached_level"] == WarningLevel.LEVEL_2
    assert StudentWarning.objects.count() == 0  # لا إصدار تلقائي

    issue(env, student, ABSENCE, WarningLevel.LEVEL_2)
    state = evaluate(env, student)
    assert state["levels"]["LEVEL_2"]["state"] == ISSUED
    assert state["levels"]["LEVEL_1"]["state"] == DUE  # ما زال متاحًا للإصدار


@pytest.mark.django_db
def test_rule_change_after_issue_keeps_snapshot(env):
    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, 3)
    warning = issue(env, student, ABSENCE, WarningLevel.LEVEL_1)
    set_rules(env, ABSENCE, 2, 4, 7)
    warning.refresh_from_db()
    assert warning.threshold_at_issue == 3  # العتبة القديمة ثابتة
    assert warning.metric_value_at_issue == 3


@pytest.mark.django_db
def test_excuse_after_warning_keeps_warning_and_shows_drift(env):
    """السيناريو الحاسم (52-55، 119): عذر لاحق يخفض الحالي ولا يمحو الإنذار."""
    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, 5)
    warning = issue(env, student, ABSENCE, WarningLevel.LEVEL_2)
    assert warning.metric_value_at_issue == 5

    for offset in (0, 1):  # عذر معتمد ليومين مختلفين
        day = DAY + timedelta(days=offset)
        approve(env, excuse_for(env, student, [{"attendance_date": day}]))

    warning.refresh_from_db()
    assert warning.status == WarningStatus.ISSUED
    assert warning.metric_value_at_issue == 5  # Snapshot لم يمس
    assert get_warning_current_metric(warning=warning) == 3  # الحالي انخفض


@pytest.mark.django_db
def test_student_transfer_after_issue_keeps_placement_snapshot(env):
    from students.models import Section

    student = env["students"][0]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, 3)
    warning = issue(env, student, ABSENCE, WarningLevel.LEVEL_1)
    old_section_name = warning.section_name_snapshot

    new_section = Section.objects.create(
        school=env["school"], grade=env["grade"], code="9", name="9"
    )
    enrollment = student.enrollments.get()
    enrollment.section = new_section
    enrollment.save(update_fields=["section"])
    student.full_name = "اسم جديد تمامًا"
    student.save(update_fields=["full_name"])

    warning.refresh_from_db()
    assert warning.section_name_snapshot == old_section_name
    assert warning.student_name_snapshot != student.full_name


# ---------- الإلغاء (البنود 120-122، 49-51) ----------


@pytest.mark.django_db
def test_void_and_reissue_policy(env, make_membership, make_user):
    student = env["students"][0]
    manager = make_membership(make_user("0550000910"), env["school"], ["SCHOOL_MANAGER"])
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, student, 3)
    warning = issue(env, student, ABSENCE, WarningLevel.LEVEL_1)

    voided = void_student_warning(
        school=env["school"], membership=manager, warning=warning, reason="أُصدر بالخطأ"
    )
    assert voided.status == WarningStatus.VOIDED
    assert voided.voided_by_membership_id == manager.id
    assert voided.voided_at is not None and voided.void_reason == "أُصدر بالخطأ"

    with pytest.raises(ApiError) as exc:
        void_student_warning(
            school=env["school"], membership=manager, warning=voided, reason="مرة أخرى"
        )
    assert exc.value.code == "WARNING_ALREADY_VOIDED"

    # الملغى لا يحجز المستوى — يسمح بإعادة الإصدار (سياسة موثقة)
    assert evaluate(env, student)["levels"]["LEVEL_1"]["state"] == DUE
    reissued = issue(env, student, ABSENCE, WarningLevel.LEVEL_1)
    assert reissued.id != warning.id
    assert StudentWarning.objects.filter(student=student).count() == 2


# ---------- اللوحة والأداء ----------


@pytest.mark.django_db
def test_dashboard_lists_due_students_with_issued_levels(env):
    first, second, third = env["students"]
    set_rules(env, ABSENCE, 3, 5, 10)
    absence_days(env, first, 5)
    absence_days(env, second, 2)  # دون الحد
    morning_late(env, third, 3, start_day=DAY + timedelta(days=20))
    issue(env, first, ABSENCE, WarningLevel.LEVEL_1)

    result = eligibility_dashboard(school=env["school"], status_filter="due")
    rows = {(row["student_id"], row["warning_type"]): row for row in result["results"]}
    absence_row = rows[(first.id, ABSENCE)]
    assert absence_row["current_value"] == 5
    assert absence_row["highest_due_level"] == WarningLevel.LEVEL_2
    assert absence_row["issued_levels"] == [WarningLevel.LEVEL_1]
    assert absence_row["issued_warnings"] == [
        {
            "id": StudentWarning.objects.get(student=first).id,
            "level": WarningLevel.LEVEL_1,
            "document": None,
        }
    ]
    assert (second.id, ABSENCE) not in rows  # لم يصل الحد
    assert (third.id, MORNING) in rows
    assert result["summary"][ABSENCE]["due_students"] == 1
    assert result["summary"][MORNING]["due_students"] == 1


@pytest.mark.django_db
def test_dashboard_query_count_is_bounded(env, django_assert_max_num_queries):
    from tests.attendance_helpers import make_students

    extra = make_students(env["school"], env["section"], env["year"], 20, prefix="31100")
    set_rules(env, ABSENCE, 1, 2, 3)
    for student in extra[:5]:
        absence_days(env, student, 1)
    eligibility_dashboard(school=env["school"])  # تهيئة القواعد
    with django_assert_max_num_queries(12):
        result = eligibility_dashboard(school=env["school"], status_filter="due")
    assert result["count"] >= 5
