"""اختبارات نطاق الحالات الإرشادية (م14) — الفتح واللقطة والجلسات والخطط والإغلاق."""

from datetime import date, timedelta

import pytest
from django.utils import timezone as dj_timezone

from common.errors import ApiError
from counseling.models import (
    ActivityStatus,
    ActivityType,
    CaseClosureReason,
    CaseEventType,
    CaseStatus,
    CounselorCase,
    FollowUpRequestStatus,
    FollowUpRequestType,
    GoalStatus,
    GoalType,
    ImprovementStatus,
    PlanStatus,
    SessionStatus,
    SessionType,
    TeacherImprovementStatus,
)
from counseling.services.cases import (
    change_case_status,
    close_case,
    open_counselor_case,
    reassign_case,
    reopen_case,
)
from counseling.services.plans import (
    add_activity,
    add_goal,
    change_plan_status,
    complete_activity,
    create_plan,
    update_goal_status,
)
from counseling.services.sessions import add_session, void_session
from counseling.services.teacher_requests import (
    request_teacher_follow_up,
    respond_to_request,
    teacher_request_for,
)
from referrals.models import ReferralCategory, ReferralReason
from referrals.services.referrals import acknowledge_referral, create_referral
from student_actions.models import StudentAction, StudentActionType
from tests.excuse_env import DAY, DAY2, build_env, full_day_absent

pytestmark = pytest.mark.django_db

COUNSELOR = ["COUNSELOR"]
MANAGER = ["SCHOOL_MANAGER"]
VICE = ["VICE_PRINCIPAL"]


@pytest.fixture
def env(make_school, make_user, make_membership):
    school = make_school()
    environment = build_env(
        school=school,
        teacher_membership=make_membership(make_user("0551400001"), school, ["TEACHER"]),
        vice_membership=make_membership(make_user("0551400002"), school, ["VICE_PRINCIPAL"]),
        prefix="32000",
    )
    environment["manager"] = make_membership(make_user("0551400003"), school, MANAGER)
    environment["counselor"] = make_membership(make_user("0551400004"), school, COUNSELOR)
    environment["counselor2"] = make_membership(make_user("0551400005"), school, COUNSELOR)
    environment["teacher2"] = make_membership(make_user("0551400006"), school, ["TEACHER"])
    return environment


def make_referral(env, student, *, membership=None, roles=None, acknowledge=True):
    referral = create_referral(
        school=env["school"],
        membership=membership or env["vice"],
        roles=roles or VICE,
        student=student,
        category=ReferralCategory.ATTENDANCE,
        reason_code=ReferralReason.REPEATED_ABSENCE,
        description="غياب متكرر يحتاج متابعة إرشادية مستمرة.",
        assigned_counselor_id=env["counselor"].id,
    )
    if acknowledge:
        acknowledge_referral(
            referral_id=referral.id,
            school=env["school"],
            membership=env["counselor"],
            roles=COUNSELOR,
        )
        referral.refresh_from_db()
    return referral


def open_case(env, student, **kwargs):
    referral = kwargs.pop("referral", None) or make_referral(env, student)
    return open_counselor_case(
        school=env["school"],
        membership=kwargs.pop("membership", env["counselor"]),
        roles=kwargs.pop("roles", COUNSELOR),
        referral_id=referral.id,
        **kwargs,
    )


# ---------------------------------------------------------------- فتح الحالة


def test_counselor_opens_case_from_acknowledged_referral(env):
    student = env["students"][0]
    case = open_case(env, student)
    assert case.status == CaseStatus.OPEN
    assert case.assigned_counselor_membership_id == env["counselor"].id
    assert case.opened_by_membership_id == env["counselor"].id
    assert case.events.filter(event_type=CaseEventType.CASE_OPENED).count() == 1


def test_case_cannot_open_before_acknowledgement(env):
    student = env["students"][0]
    referral = make_referral(env, student, acknowledge=False)
    with pytest.raises(ApiError) as exc:
        open_case(env, student, referral=referral)
    assert exc.value.code == "REFERRAL_NOT_ACKNOWLEDGED"


def test_other_counselor_cannot_open_case(env):
    """البند 109: مرشد آخر لا يفتح ملف زميله."""
    student = env["students"][0]
    referral = make_referral(env, student)
    with pytest.raises(ApiError) as exc:
        open_case(env, student, referral=referral, membership=env["counselor2"])
    assert exc.value.code == "CASE_PERMISSION_DENIED"


def test_double_open_creates_single_case(env):
    """البندان 14-15: القيد الفريد هو الحكم، لا الفحص التطبيقي."""
    student = env["students"][0]
    referral = make_referral(env, student)
    open_case(env, student, referral=referral)
    with pytest.raises(ApiError) as exc:
        open_case(env, student, referral=referral)
    assert exc.value.code == "CASE_ALREADY_OPEN"
    assert CounselorCase.objects.filter(primary_referral=referral).count() == 1


def test_second_live_case_for_same_student_blocked_with_existing_id(env):
    """البند 81: إحالة ثانية لا تفتح ملفًا ثانيًا تلقائيًا."""
    student = env["students"][0]
    first = open_case(env, student)
    second_referral = create_referral(
        school=env["school"],
        membership=env["vice"],
        roles=VICE,
        student=student,
        category=ReferralCategory.ACADEMIC,
        reason_code=ReferralReason.ACADEMIC_WEAKNESS,
        description="ضعف دراسي يحتاج متابعة إرشادية.",
        assigned_counselor_id=env["counselor"].id,
    )
    acknowledge_referral(
        referral_id=second_referral.id,
        school=env["school"],
        membership=env["counselor"],
        roles=COUNSELOR,
    )
    with pytest.raises(ApiError) as exc:
        open_case(env, student, referral=second_referral)
    assert exc.value.code == "OPEN_CASE_EXISTS"
    assert exc.value.error_details["existing_case_id"] == first.id


# ---------------------------------------------------------------- اللقطة


def test_snapshot_frozen_while_current_metrics_move(env):
    """البند 112: عند الفتح 5 أيام ثم تنخفض — اللقطة لا تتحرك."""
    from counseling.services.snapshots import current_case_metrics
    from excuses.services.coverage import approve_excuse, resolve_coverage_plan
    from excuses.services.excuses import create_excuse

    student = env["students"][0]
    for day in (DAY, DAY2):
        full_day_absent(env, student, day=day)
    case = open_case(env, student)
    assert case.snapshot_data["unexcused_full_absence_days"] == 2
    assert case.snapshot_data["student_name"] == student.full_name
    # لا PII زائدة في اللقطة (البند 17)
    assert "national_id" not in case.snapshot_data
    assert "guardian_mobile" not in case.snapshot_data

    excuse = create_excuse(
        school=env["school"], membership=env["vice"], student=student,
        reason_type="MEDICAL_REPORT", notes="", targets=[{"attendance_date": DAY}],
    )
    approve_excuse(
        excuse_id=excuse.id, school=env["school"], membership=env["vice"],
        preview_hash=resolve_coverage_plan(excuse)["preview_hash"],
    )
    case.refresh_from_db()
    assert case.snapshot_data["unexcused_full_absence_days"] == 2
    current = current_case_metrics(school=env["school"], student=student)
    assert current["unexcused_full_absence_days"] == 1


# ---------------------------------------------------------------- الجلسات


@pytest.mark.parametrize(
    "session_type",
    [SessionType.STUDENT_MEETING, SessionType.PARENT_MEETING, SessionType.CASE_REVIEW],
)
def test_sessions_of_each_type(env, session_type):
    case = open_case(env, env["students"][0])
    session = add_session(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        session_type=session_type, summary="ملخص الجلسة التربوية.",
        observations="ملاحظات", outcome="نتيجة",
    )
    assert session.status == SessionStatus.RECORDED
    assert case.events.filter(event_type=CaseEventType.SESSION_ADDED).count() == 1


def test_meeting_session_records_one_administrative_action(env):
    """البنود 86-88: سجل إداري واحد متوافق، والتفصيل يبقى في الجلسة."""
    case = open_case(env, env["students"][0])
    add_session(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        session_type=SessionType.STUDENT_MEETING, summary="مقابلة الطالب.",
    )
    # الإحالة الإدارية سجلت إجراءها (تكامل م12+م13)؛ الجلسة تضيف إجراءها هي فقط
    actions = StudentAction.objects.filter(
        student=case.student, action_type=StudentActionType.STUDENT_MEETING
    )
    assert actions.count() == 1
    # لا نص إرشادي داخل السجل الإداري
    assert "مقابلة الطالب." not in actions.first().notes


def test_case_review_session_creates_no_administrative_action(env):
    case = open_case(env, env["students"][0])
    add_session(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        session_type=SessionType.CASE_REVIEW, summary="مراجعة داخلية.",
    )
    # مراجعة داخلية ليست إجراءً إداريًا — لا يضاف شيء فوق إجراء الإحالة
    assert (
        StudentAction.objects.filter(student=case.student)
        .exclude(action_type=StudentActionType.REFERRED_TO_COUNSELOR)
        .count()
        == 0
    )


def test_session_void_keeps_the_row(env):
    case = open_case(env, env["students"][0])
    session = add_session(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        session_type=SessionType.PHONE_CALL, summary="اتصال بولي الأمر.",
    )
    voided = void_session(
        session=session, membership=env["counselor"], roles=COUNSELOR, reason="سجلت بالخطأ"
    )
    assert voided.status == SessionStatus.VOIDED
    assert voided.void_reason == "سجلت بالخطأ"
    assert case.sessions.count() == 1


def test_other_counselor_cannot_add_session(env):
    case = open_case(env, env["students"][0])
    with pytest.raises(ApiError) as exc:
        add_session(
            case=case, membership=env["counselor2"], roles=COUNSELOR,
            session_type=SessionType.STUDENT_MEETING, summary="محاولة",
        )
    assert exc.value.code == "CASE_PERMISSION_DENIED"


# ---------------------------------------------------------------- الخطط والأهداف


def test_plan_lifecycle_and_single_active_plan(env):
    case = open_case(env, env["students"][0])
    plan = create_plan(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        title="خطة متابعة الحضور", start_date=date(2026, 8, 1),
    )
    assert plan.status == PlanStatus.DRAFT

    change_plan_status(
        plan=plan, membership=env["counselor"], roles=COUNSELOR, new_status=PlanStatus.ACTIVE
    )
    plan.refresh_from_db()
    assert plan.status == PlanStatus.ACTIVE and plan.activated_at is not None

    # البند 118: خطة نشطة ثانية ممنوعة
    with pytest.raises(ApiError) as exc:
        create_plan(
            case=case, membership=env["counselor"], roles=COUNSELOR,
            title="خطة ثانية", start_date=date(2026, 8, 2), activate=True,
        )
    assert exc.value.code == "ACTIVE_PLAN_EXISTS"

    change_plan_status(
        plan=plan, membership=env["counselor"], roles=COUNSELOR,
        new_status=PlanStatus.COMPLETED,
    )
    plan.refresh_from_db()
    assert plan.status == PlanStatus.COMPLETED and plan.completed_at is not None
    # وبعد إكمالها يمكن تفعيل خطة جديدة
    second = create_plan(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        title="خطة تالية", start_date=date(2026, 9, 1), activate=True,
    )
    assert second.status == PlanStatus.ACTIVE


def test_quantitative_and_qualitative_goals(env):
    case = open_case(env, env["students"][0])
    plan = create_plan(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        title="خطة", start_date=date(2026, 8, 1), activate=True,
    )
    numeric = add_goal(
        plan=plan, membership=env["counselor"], roles=COUNSELOR,
        goal_type=GoalType.MORNING_LATENESS, title="خفض التأخر الصباحي",
        baseline_value=6, target_value=1, unit="مرات",
    )
    qualitative = add_goal(
        plan=plan, membership=env["counselor"], roles=COUNSELOR,
        goal_type=GoalType.PARTICIPATION, title="رفع المشاركة داخل الفصل",
        description="ملاحظة نوعية بلا رقم",
    )
    assert (numeric.baseline_value, numeric.target_value) == (6, 1)
    assert qualitative.baseline_value is None and qualitative.target_value is None

    update_goal_status(
        goal=numeric, membership=env["counselor"], roles=COUNSELOR,
        new_status=GoalStatus.COMPLETED,
    )
    numeric.refresh_from_db()
    assert numeric.status == GoalStatus.COMPLETED and numeric.completed_at is not None
    assert case.events.filter(event_type=CaseEventType.GOAL_COMPLETED).count() == 1


def test_activity_completion(env):
    case = open_case(env, env["students"][0])
    plan = create_plan(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        title="خطة", start_date=date(2026, 8, 1), activate=True,
    )
    activity = add_activity(
        plan=plan, membership=env["counselor"], roles=COUNSELOR,
        activity_type=ActivityType.STUDENT_CHECK_IN, title="متابعة أسبوعية",
        due_date=date(2026, 8, 10),
    )
    assert activity.status == ActivityStatus.PENDING
    completed = complete_activity(
        activity=activity, membership=env["counselor"], roles=COUNSELOR
    )
    assert completed.status == ActivityStatus.COMPLETED
    assert completed.completed_by_membership_id == env["counselor"].id
    with pytest.raises(ApiError) as exc:
        complete_activity(activity=completed, membership=env["counselor"], roles=COUNSELOR)
    assert exc.value.code == "ACTIVITY_ALREADY_FINISHED"


# ---------------------------------------------------------------- طلبات المعلمين


def test_teacher_follow_up_round_trip(env):
    case = open_case(env, env["students"][0])
    follow_up = request_teacher_follow_up(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        teacher_membership_id=env["teacher"].id,
        request_type=FollowUpRequestType.CLASSROOM_BEHAVIOR,
        question="كيف كان تفاعله خلال الأسبوع؟",
        due_date=date(2026, 8, 20),
    )
    assert follow_up.status == FollowUpRequestStatus.PENDING

    response = respond_to_request(
        school=env["school"], membership=env["teacher"], request_id=follow_up.id,
        observation="تحسن واضح في الالتزام.",
        improvement_status=TeacherImprovementStatus.IMPROVED,
    )
    follow_up.refresh_from_db()
    assert follow_up.status == FollowUpRequestStatus.ANSWERED
    assert follow_up.responded_at is not None
    assert response.improvement_status == TeacherImprovementStatus.IMPROVED
    assert case.events.filter(
        event_type=CaseEventType.TEACHER_RESPONSE_RECEIVED
    ).count() == 1


def test_request_to_foreign_school_teacher_rejected(
    env, make_school, make_user, make_membership
):
    """البند 123: معلم مدرسة أخرى ليس خيارًا."""
    other_school = make_school()
    foreign_teacher = make_membership(make_user("0551400010"), other_school, ["TEACHER"])
    case = open_case(env, env["students"][0])
    with pytest.raises(ApiError) as exc:
        request_teacher_follow_up(
            case=case, membership=env["counselor"], roles=COUNSELOR,
            teacher_membership_id=foreign_teacher.id,
            request_type=FollowUpRequestType.PARTICIPATION, question="سؤال",
        )
    assert exc.value.code == "TEACHER_NOT_FOUND"


def test_teacher_cannot_reach_another_teachers_request(env):
    """البندان 98-99: المعرف ليس مفتاحًا — الحل عبر عضوية المعلم نفسه."""
    case = open_case(env, env["students"][0])
    follow_up = request_teacher_follow_up(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        teacher_membership_id=env["teacher"].id,
        request_type=FollowUpRequestType.HOMEWORK, question="سؤال",
    )
    with pytest.raises(ApiError) as exc:
        teacher_request_for(
            school=env["school"], membership=env["teacher2"], request_id=follow_up.id
        )
    assert exc.value.code == "FOLLOW_UP_REQUEST_NOT_FOUND"
    assert exc.value.status_code == 404

    with pytest.raises(ApiError):
        respond_to_request(
            school=env["school"], membership=env["teacher2"], request_id=follow_up.id,
            observation="محاولة", improvement_status=TeacherImprovementStatus.IMPROVED,
        )


def test_response_is_immutable(env):
    """البند 127: لا رد ثانٍ يعدل الأول صامتًا."""
    case = open_case(env, env["students"][0])
    follow_up = request_teacher_follow_up(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        teacher_membership_id=env["teacher"].id,
        request_type=FollowUpRequestType.PARTICIPATION, question="سؤال",
    )
    respond_to_request(
        school=env["school"], membership=env["teacher"], request_id=follow_up.id,
        observation="ملاحظة أولى", improvement_status=TeacherImprovementStatus.UNCHANGED,
    )
    with pytest.raises(ApiError) as exc:
        respond_to_request(
            school=env["school"], membership=env["teacher"], request_id=follow_up.id,
            observation="ملاحظة ثانية", improvement_status=TeacherImprovementStatus.IMPROVED,
        )
    assert exc.value.code == "FOLLOW_UP_ALREADY_ANSWERED"


# ---------------------------------------------------------------- الحالة والإغلاق


def test_status_flow_and_invalid_transition(env):
    case = open_case(env, env["students"][0])
    change_case_status(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        new_status=CaseStatus.UNDER_ASSESSMENT,
    )
    change_case_status(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        new_status=CaseStatus.FOLLOW_UP_ACTIVE,
    )
    assert case.status == CaseStatus.FOLLOW_UP_ACTIVE
    with pytest.raises(ApiError) as exc:
        change_case_status(
            case=case, membership=env["counselor"], roles=COUNSELOR,
            new_status=CaseStatus.OPEN,
        )
    assert exc.value.code == "INVALID_CASE_STATUS_TRANSITION"


def test_close_requires_reason_and_tidies_the_case(env):
    """البندان 49 و52: سبب إلزامي، والخطة النشطة والطلبات المعلقة تُرتب."""
    case = open_case(env, env["students"][0])
    plan = create_plan(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        title="خطة", start_date=date(2026, 8, 1), activate=True,
    )
    activity = add_activity(
        plan=plan, membership=env["counselor"], roles=COUNSELOR,
        activity_type=ActivityType.FOLLOW_UP_MEETING, title="لقاء",
    )
    follow_up = request_teacher_follow_up(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        teacher_membership_id=env["teacher"].id,
        request_type=FollowUpRequestType.CUSTOM, question="سؤال",
    )
    change_case_status(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        new_status=CaseStatus.FOLLOW_UP_ACTIVE,
    )
    change_case_status(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        new_status=CaseStatus.RESOLVED,
    )

    with pytest.raises(ApiError) as exc:
        close_case(
            case=case, membership=env["counselor"], roles=COUNSELOR, closure_reason="",
        )
    assert exc.value.code == "CASE_CLOSURE_REASON_REQUIRED"

    closed = close_case(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        closure_reason=CaseClosureReason.GOALS_MET,
        outcome_summary="تحسن ملحوظ في الالتزام.",
        improvement_status=ImprovementStatus.IMPROVED,
    )
    plan.refresh_from_db()
    activity.refresh_from_db()
    follow_up.refresh_from_db()
    assert closed.status == CaseStatus.CLOSED and closed.closed_at is not None
    assert plan.status == PlanStatus.COMPLETED
    assert activity.status == ActivityStatus.CANCELLED
    assert follow_up.status == FollowUpRequestStatus.CANCELLED
    assert closed.improvement_status == ImprovementStatus.IMPROVED


def test_reopen_requires_reason_and_logs_timeline(env):
    case = open_case(env, env["students"][0])
    close_case(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        closure_reason=CaseClosureReason.IMPROVED,
    )
    with pytest.raises(ApiError) as exc:
        reopen_case(case=case, membership=env["counselor"], roles=COUNSELOR, reason=" ")
    assert exc.value.code == "CASE_REOPEN_REASON_REQUIRED"

    reopened = reopen_case(
        case=case, membership=env["counselor"], roles=COUNSELOR, reason="عاد الغياب"
    )
    assert reopened.status == CaseStatus.OPEN
    assert reopened.closed_at is None and reopened.closure_reason == ""
    assert case.events.filter(event_type=CaseEventType.CASE_REOPENED).count() == 1


def test_closed_case_rejects_new_content(env):
    case = open_case(env, env["students"][0])
    close_case(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        closure_reason=CaseClosureReason.IMPROVED,
    )
    with pytest.raises(ApiError) as exc:
        add_session(
            case=case, membership=env["counselor"], roles=COUNSELOR,
            session_type=SessionType.STUDENT_MEETING, summary="بعد الإغلاق",
        )
    assert exc.value.code == "CASE_CLOSED"


def test_manager_reassigns_counselor_and_counselor_cannot(env):
    case = open_case(env, env["students"][0])
    with pytest.raises(ApiError) as exc:
        reassign_case(
            case=case, membership=env["counselor"], roles=COUNSELOR,
            counselor_id=env["counselor2"].id,
        )
    assert exc.value.code == "CASE_PERMISSION_DENIED"

    reassign_case(
        case=case, membership=env["manager"], roles=MANAGER,
        counselor_id=env["counselor2"].id,
    )
    case.refresh_from_db()
    assert case.assigned_counselor_membership_id == env["counselor2"].id
    assert case.events.filter(event_type=CaseEventType.COUNSELOR_REASSIGNED).count() == 1


# ---------------------------------------------------------------- الحذف النهائي


def test_purge_steps_registered_before_referrals(env):
    from students.services.purge import PURGE_STEPS

    labels = [label for label, _ in PURGE_STEPS]
    for expected in (
        "ردود متابعة المعلمين", "طلبات متابعة المعلمين", "إجراءات المتابعة",
        "أهداف المتابعة", "خطط المتابعة", "الجلسات الإرشادية",
        "أحداث الحالات الإرشادية", "الحالات الإرشادية",
    ):
        assert expected in labels, expected
    assert labels.index("ردود متابعة المعلمين") < labels.index("طلبات متابعة المعلمين")
    assert labels.index("خطط المتابعة") < labels.index("الحالات الإرشادية")
    # الحالة تُحذف قبل الإحالة (‏primary_referral بـPROTECT)
    assert labels.index("الحالات الإرشادية") < labels.index("إحالات الطالب")


def test_dashboard_kpis_scope_by_role(env):
    from counseling.selectors import counselor_dashboard_kpis

    case = open_case(env, env["students"][0])
    change_case_status(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        new_status=CaseStatus.FOLLOW_UP_ACTIVE,
    )
    request_teacher_follow_up(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        teacher_membership_id=env["teacher"].id,
        request_type=FollowUpRequestType.CUSTOM, question="سؤال",
    )
    mine = counselor_dashboard_kpis(
        school=env["school"], membership=env["counselor"], roles=COUNSELOR
    )
    assert mine["open_cases"] == 1
    assert mine["follow_up_active"] == 1
    assert mine["waiting_teacher_response"] == 1

    # مرشد آخر لا يرى حالة زميله في مؤشراته (البند 97)
    other = counselor_dashboard_kpis(
        school=env["school"], membership=env["counselor2"], roles=COUNSELOR
    )
    assert other["open_cases"] == 0
    assert other["waiting_teacher_response"] == 0

    manager_view = counselor_dashboard_kpis(
        school=env["school"], membership=env["manager"], roles=MANAGER
    )
    assert manager_view["open_cases"] == 1


def test_due_activities_counter(env):
    from counseling.selectors import counselor_dashboard_kpis

    case = open_case(env, env["students"][0])
    plan = create_plan(
        case=case, membership=env["counselor"], roles=COUNSELOR,
        title="خطة", start_date=date(2026, 8, 1), activate=True,
    )
    add_activity(
        plan=plan, membership=env["counselor"], roles=COUNSELOR,
        activity_type=ActivityType.STUDENT_CHECK_IN, title="مستحق",
        due_date=dj_timezone.localdate() - timedelta(days=1),
    )
    add_activity(
        plan=plan, membership=env["counselor"], roles=COUNSELOR,
        activity_type=ActivityType.STUDENT_CHECK_IN, title="لاحق",
        due_date=dj_timezone.localdate() + timedelta(days=7),
    )
    kpis = counselor_dashboard_kpis(
        school=env["school"], membership=env["counselor"], roles=COUNSELOR
    )
    assert kpis["due_activities"] == 1
