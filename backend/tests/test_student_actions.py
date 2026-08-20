"""اختبارات الإجراءات الطلابية (م12) — التسجيل، ربط الإنذار، الإلغاء، عدم مس المصادر."""

from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone as dj_timezone

from common.errors import ApiError
from student_actions.models import StudentAction, StudentActionStatus, StudentActionType
from student_actions.services import cancel_student_action, create_student_action
from student_warnings.models import StudentWarning, WarningLevel, WarningRuleType, WarningStatus
from tests.excuse_env import build_env

pytestmark = pytest.mark.django_db


@pytest.fixture
def env(make_school, make_user, make_membership):
    school = make_school()
    return build_env(
        school=school,
        teacher_membership=make_membership(make_user("0550001200"), school, ["TEACHER"]),
        vice_membership=make_membership(make_user("0550001201"), school, ["VICE_PRINCIPAL"]),
        prefix="30200",
    )


def make_warning(env, student, *, level=WarningLevel.LEVEL_1) -> StudentWarning:
    return StudentWarning.objects.create(
        school=env["school"],
        student=student,
        academic_year=env["year"],
        warning_type=WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE,
        level=level,
        status=WarningStatus.ISSUED,
        threshold_at_issue=3,
        metric_value_at_issue=5,
        student_name_snapshot=student.full_name,
        grade_name_snapshot="الأول الثانوي",
        section_name_snapshot="1",
        national_id_masked_snapshot=student.national_id_masked,
        unexcused_full_absence_days_at_issue=5,
        issued_by_membership=env["vice"],
        issued_at=dj_timezone.now(),
    )


def test_vice_records_parent_contact(env):
    student = env["students"][0]
    action = create_student_action(
        school=env["school"],
        membership=env["vice"],
        student=student,
        action_type=StudentActionType.PARENT_CONTACT,
        notes="تم التواصل وأفاد بحضوره الأحد.",
    )
    assert action.status == StudentActionStatus.COMPLETED
    assert action.performed_by_membership_id == env["vice"].id
    assert action.warning_id is None


@pytest.mark.parametrize(
    "action_type",
    [
        StudentActionType.PARENT_CONTACT,
        StudentActionType.STUDENT_MEETING,
        StudentActionType.PARENT_MEETING,
        StudentActionType.COMMITMENT_TAKEN,
        StudentActionType.WARNING_DELIVERED,
        StudentActionType.ADMINISTRATIVE_NOTE,
        StudentActionType.OTHER,
    ],
)
def test_all_mvp_action_types_supported(env, action_type):
    action = create_student_action(
        school=env["school"],
        membership=env["vice"],
        student=env["students"][0],
        action_type=action_type,
    )
    assert action.action_type == action_type


def test_action_links_to_warning_of_same_student(env):
    student = env["students"][0]
    warning = make_warning(env, student)
    action = create_student_action(
        school=env["school"],
        membership=env["vice"],
        student=student,
        action_type=StudentActionType.WARNING_DELIVERED,
        warning_id=warning.id,
    )
    assert action.warning_id == warning.id


def test_action_cannot_link_warning_of_another_student(env):
    warning = make_warning(env, env["students"][0])
    with pytest.raises(ApiError) as exc:
        create_student_action(
            school=env["school"],
            membership=env["vice"],
            student=env["students"][1],  # طالب آخر
            action_type=StudentActionType.WARNING_DELIVERED,
            warning_id=warning.id,
        )
    assert exc.value.code == "INVALID_ACTION_WARNING_LINK"
    assert StudentAction.objects.count() == 0


def test_action_cannot_link_warning_of_another_school(
    env, make_school, make_user, make_membership
):
    other_school = make_school()
    other = build_env(
        school=other_school,
        teacher_membership=make_membership(make_user("0550001210"), other_school, ["TEACHER"]),
        vice_membership=make_membership(
            make_user("0550001211"), other_school, ["VICE_PRINCIPAL"]
        ),
        prefix="30300",
    )
    foreign_warning = make_warning(other, other["students"][0])
    with pytest.raises(ApiError) as exc:
        create_student_action(
            school=env["school"],
            membership=env["vice"],
            student=env["students"][0],
            action_type=StudentActionType.WARNING_DELIVERED,
            warning_id=foreign_warning.id,
        )
    assert exc.value.code == "INVALID_ACTION_WARNING_LINK"


def test_future_action_rejected(env):
    with pytest.raises(ApiError) as exc:
        create_student_action(
            school=env["school"],
            membership=env["vice"],
            student=env["students"][0],
            action_type=StudentActionType.PARENT_CONTACT,
            performed_at=dj_timezone.now() + timedelta(days=2),
        )
    assert exc.value.code == "VALIDATION_ERROR"


def test_cancel_keeps_row_and_records_reason(env):
    action = create_student_action(
        school=env["school"],
        membership=env["vice"],
        student=env["students"][0],
        action_type=StudentActionType.PARENT_CONTACT,
    )
    cancelled = cancel_student_action(
        school=env["school"], membership=env["vice"], action=action, reason="سجل بالخطأ"
    )
    assert cancelled.status == StudentActionStatus.CANCELLED
    assert cancelled.cancellation_reason == "سجل بالخطأ"
    assert cancelled.cancelled_at is not None
    # لا حذف نهائي: الصف باقٍ (البند 102)
    assert StudentAction.objects.filter(id=action.id).exists()


def test_cancel_twice_rejected(env):
    action = create_student_action(
        school=env["school"],
        membership=env["vice"],
        student=env["students"][0],
        action_type=StudentActionType.PARENT_CONTACT,
    )
    cancel_student_action(
        school=env["school"], membership=env["vice"], action=action, reason="خطأ"
    )
    with pytest.raises(ApiError) as exc:
        cancel_student_action(
            school=env["school"], membership=env["vice"], action=action, reason="مرة أخرى"
        )
    assert exc.value.code == "STUDENT_ACTION_ALREADY_CANCELLED"


def test_action_does_not_touch_warning_or_attendance(env):
    """الإجراء تسجيل فقط: الإنذار وبيانات الحضور تبقى كما هي (البند 2)."""
    from attendance.models import AttendanceMark

    student = env["students"][0]
    warning = make_warning(env, student)
    before = (warning.metric_value_at_issue, warning.status, AttendanceMark.objects.count())
    create_student_action(
        school=env["school"],
        membership=env["vice"],
        student=student,
        action_type=StudentActionType.WARNING_DELIVERED,
        warning_id=warning.id,
    )
    warning.refresh_from_db()
    assert (warning.metric_value_at_issue, warning.status, AttendanceMark.objects.count()) == before


def test_actions_are_ordered_chronologically_for_profile(env):
    """السيناريو 158: تواصل ← تعهد ← تسليم إنذار يظهر بالترتيب الزمني."""
    student = env["students"][0]
    base = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)
    for index, action_type in enumerate(
        [
            StudentActionType.PARENT_CONTACT,
            StudentActionType.COMMITMENT_TAKEN,
            StudentActionType.WARNING_DELIVERED,
        ]
    ):
        create_student_action(
            school=env["school"],
            membership=env["vice"],
            student=student,
            action_type=action_type,
            performed_at=base + timedelta(days=index),
        )
    rows = list(
        StudentAction.objects.filter(student=student).order_by("performed_at").values_list(
            "action_type", flat=True
        )
    )
    assert rows == [
        StudentActionType.PARENT_CONTACT,
        StudentActionType.COMMITMENT_TAKEN,
        StudentActionType.WARNING_DELIVERED,
    ]
