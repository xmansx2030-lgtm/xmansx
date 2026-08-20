"""اختبارات نطاق إحالات الطلاب (م13) — الإحالة طلب متابعة لا إنذار ولا تشخيص."""

import pytest

from common.errors import ApiError
from memberships.models import MembershipStatus
from referrals.models import (
    ReferralCategory,
    ReferralEventType,
    ReferralObservationType,
    ReferralReason,
    ReferralSourceType,
    ReferralStatus,
    StudentReferral,
    StudentReferralEvent,
)
from referrals.selectors import (
    can_view_referral,
    referral_kpis,
    teacher_referrals,
    visible_referrals,
)
from referrals.services.referrals import (
    acknowledge_referral,
    add_contribution,
    assign_counselor,
    close_referral,
    create_referral,
    find_open_duplicate,
    resolve_source_type,
)
from tests.attendance_helpers import make_students


@pytest.fixture
def env(make_school, make_user, make_membership):
    """مدرسة بأدوارها الكاملة + طالبان — بلا بيانات حضور (لا يحتاجها معظم الاختبار)."""
    from academics.models import AcademicYear, AcademicYearStatus
    from students.models import Grade, Section

    school = make_school()
    year = AcademicYear.objects.create(
        school=school, name="2026/2027", start_date="2026-08-01",
        end_date="2027-06-25", status=AcademicYearStatus.ACTIVE,
    )
    grade = Grade.objects.create(school=school, name="الأول الثانوي", code="G1", sequence=1)
    section = Section.objects.create(school=school, grade=grade, code="1", name="1")
    students = make_students(school, section, year, 2, prefix="50100")

    return {
        "school": school,
        "year": year,
        "section": section,
        "students": students,
        "teacher": make_membership(make_user("0551300001"), school, ["TEACHER"]),
        "teacher2": make_membership(make_user("0551300002"), school, ["TEACHER"]),
        "vice": make_membership(make_user("0551300003"), school, ["VICE_PRINCIPAL"]),
        "manager": make_membership(make_user("0551300004"), school, ["SCHOOL_MANAGER"]),
        "counselor": make_membership(make_user("0551300005"), school, ["COUNSELOR"]),
        "counselor2": make_membership(make_user("0551300006"), school, ["COUNSELOR"]),
    }


def teacher_referral(env, student=None, *, reason=ReferralReason.ACADEMIC_WEAKNESS,
                     category=ReferralCategory.ACADEMIC, membership=None, **kwargs):
    return create_referral(
        school=env["school"],
        membership=membership or env["teacher"],
        roles=["TEACHER"],
        student=student or env["students"][0],
        category=category,
        reason_code=reason,
        description=kwargs.pop("description", "نام الطالب في الحصة ثلاث مرات هذا الأسبوع."),
        **kwargs,
    )


def vice_referral(env, student=None, **kwargs):
    return create_referral(
        school=env["school"],
        membership=env["vice"],
        roles=["VICE_PRINCIPAL"],
        student=student or env["students"][0],
        category=kwargs.pop("category", ReferralCategory.ATTENDANCE),
        reason_code=kwargs.pop("reason_code", ReferralReason.REPEATED_ABSENCE),
        description=kwargs.pop("description", "تكرر غيابه خمسة أيام."),
        **kwargs,
    )


# ---------- الإنشاء (البنود 93-97) ----------


@pytest.mark.django_db
def test_teacher_academic_referral(env):
    referral = teacher_referral(env)
    assert referral.status == ReferralStatus.NEW
    assert referral.source_type == ReferralSourceType.TEACHER
    assert referral.assigned_counselor_membership_id is None
    assert referral.events.filter(event_type=ReferralEventType.CREATED).exists()


@pytest.mark.django_db
def test_teacher_classroom_referral(env):
    referral = teacher_referral(
        env,
        category=ReferralCategory.CLASSROOM_BEHAVIOR,
        reason=ReferralReason.SLEEPING_IN_CLASS,
    )
    assert referral.category == ReferralCategory.CLASSROOM_BEHAVIOR
    assert referral.reason_code == ReferralReason.SLEEPING_IN_CLASS


@pytest.mark.django_db
def test_vice_attendance_referral(env):
    referral = vice_referral(env)
    assert referral.source_type == ReferralSourceType.VICE_PRINCIPAL
    assert referral.category == ReferralCategory.ATTENDANCE
    # لقطة فئة المواظبة تحمل المؤشرات
    assert "unexcused_full_absence_days" in referral.snapshot_data


@pytest.mark.django_db
def test_teacher_cannot_use_attendance_category(env):
    """فئة المواظبة قرار إداري — المعلم يحيل لما يلاحظه في صفه (بند 121)."""
    with pytest.raises(ApiError) as exc:
        teacher_referral(
            env,
            category=ReferralCategory.ATTENDANCE,
            reason=ReferralReason.REPEATED_ABSENCE,
        )
    assert exc.value.code == "INVALID_REFERRAL_CATEGORY"


@pytest.mark.django_db
def test_reason_must_belong_to_category(env):
    with pytest.raises(ApiError) as exc:
        teacher_referral(
            env,
            category=ReferralCategory.ACADEMIC,
            reason=ReferralReason.SLEEPING_IN_CLASS,
        )
    assert exc.value.code == "INVALID_REFERRAL_REASON"


@pytest.mark.django_db
def test_other_reason_requires_description(env):
    with pytest.raises(ApiError) as exc:
        teacher_referral(env, reason=ReferralReason.OTHER_ACADEMIC, description="   ")
    assert exc.value.code == "INVALID_REFERRAL_REASON"
    # مع وصف: يمر
    assert teacher_referral(
        env, reason=ReferralReason.OTHER_ACADEMIC, description="يحتاج متابعة في مادة محددة."
    ).id


@pytest.mark.django_db
def test_no_diagnosis_fields_in_schema(env):
    """سياسة «لا تشخيص»: لا حقول طبية/نفسية في أي من نماذج الإحالة (بند 97)."""
    forbidden = {"diagnosis", "medical", "psych", "disorder", "condition", "treatment"}
    for model in (StudentReferral, StudentReferralEvent):
        names = {f.name.lower() for f in model._meta.fields}
        assert not any(word in name for name in names for word in forbidden)


@pytest.mark.django_db
def test_source_type_precedence(env):
    """مستخدم بأدوار متعددة يُسجَّل بأعلى صلاحياته — snapshot لا يتغير لاحقًا."""
    assert resolve_source_type(["TEACHER", "SCHOOL_MANAGER"]) == (
        ReferralSourceType.SCHOOL_MANAGER
    )
    assert resolve_source_type(["TEACHER", "VICE_PRINCIPAL"]) == (
        ReferralSourceType.VICE_PRINCIPAL
    )
    assert resolve_source_type(["TEACHER"]) == ReferralSourceType.TEACHER
    with pytest.raises(ApiError):
        resolve_source_type(["COUNSELOR"])


# ---------- اللقطة مقابل الحالي (بند 96 والسيناريو 157) ----------


@pytest.mark.django_db
def test_snapshot_frozen_when_attendance_changes(make_school, make_user, make_membership):
    """اللقطة تبقى كما كانت لحظة الإحالة ولو تحسنت مؤشرات الطالب بعدها."""
    from excuses.selectors import count_unexcused_full_absence_days
    from referrals.services.snapshots import attendance_metrics
    from tests.excuse_env import DAY, DAY2, approve, build_env, excuse_for, full_day_absent

    school = make_school()
    env = build_env(
        school=school,
        teacher_membership=make_membership(make_user("0551301001"), school, ["TEACHER"]),
        vice_membership=make_membership(
            make_user("0551301002"), school, ["VICE_PRINCIPAL"]
        ),
        prefix="50200",
    )
    student = env["students"][0]
    full_day_absent(env, student, day=DAY)
    full_day_absent(env, student, day=DAY2)
    assert count_unexcused_full_absence_days(school=school, student=student) == 2

    referral = create_referral(
        school=school, membership=env["vice"], roles=["VICE_PRINCIPAL"], student=student,
        category=ReferralCategory.ATTENDANCE,
        reason_code=ReferralReason.REPEATED_ABSENCE,
        description="غياب متكرر يحتاج متابعة.",
    )
    assert referral.snapshot_data["unexcused_full_absence_days"] == 2

    # يوم يصبح بعذر معتمد → المؤشر الحالي ينخفض واللقطة لا تتحرك
    approve(env, excuse_for(env, student, [{"attendance_date": DAY}]))
    referral.refresh_from_db()
    assert referral.snapshot_data["unexcused_full_absence_days"] == 2
    current = attendance_metrics(school=school, student=student)
    assert current["unexcused_full_absence_days"] == 1


# ---------- التكرار (البنود 98-101) ----------


@pytest.mark.django_db
def test_duplicate_open_referral_detected(env):
    first = teacher_referral(env)
    with pytest.raises(ApiError) as exc:
        teacher_referral(env, membership=env["teacher2"])
    assert exc.value.code == "DUPLICATE_OPEN_REFERRAL"
    assert exc.value.error_details["existing_referral_id"] == first.id
    assert exc.value.error_details["recommended_action"] == "ADD_CONTRIBUTION"


@pytest.mark.django_db
def test_contribution_instead_of_duplicate(env):
    """حالة واحدة بملاحظتين من معلمين مختلفين بدل إحالتين (بند 36)."""
    referral = teacher_referral(env)
    add_contribution(
        referral_id=referral.id, school=env["school"], membership=env["teacher2"],
        observation_type=ReferralObservationType.ACADEMIC_OBSERVATION,
        notes="انخفضت مشاركته في حصص اللغة هذا الأسبوع.",
    )
    assert referral.contributions.count() == 1
    assert StudentReferral.objects.count() == 1
    assert referral.events.filter(
        event_type=ReferralEventType.CONTRIBUTION_ADDED
    ).exists()


@pytest.mark.django_db
def test_new_referral_allowed_after_close(env):
    first = teacher_referral(env)
    close_referral(
        referral_id=first.id, school=env["school"], membership=env["counselor"],
        reason="تمت المتابعة.",
    )
    second = teacher_referral(env, membership=env["teacher2"])
    assert second.id != first.id


@pytest.mark.django_db
def test_different_category_is_independent(env):
    teacher_referral(env)
    other = teacher_referral(
        env,
        category=ReferralCategory.CLASSROOM_BEHAVIOR,
        reason=ReferralReason.SLEEPING_IN_CLASS,
        membership=env["teacher2"],
    )
    assert other.category == ReferralCategory.CLASSROOM_BEHAVIOR
    assert StudentReferral.objects.count() == 2


@pytest.mark.django_db
def test_duplicate_scoped_to_student(env):
    teacher_referral(env, student=env["students"][0])
    second = teacher_referral(env, student=env["students"][1], membership=env["teacher2"])
    assert second.student_id == env["students"][1].id


@pytest.mark.django_db
def test_manager_may_force_duplicate_teacher_may_not(env):
    teacher_referral(env)
    # المعلم يُرد بسبب التكرار الفعلي (الراية تُتجاهل لمن لا يملكها) — والرد
    # يخلو من can_force فلا تعرض واجهته خيارًا لا يملكه
    with pytest.raises(ApiError) as exc:
        teacher_referral(env, membership=env["teacher2"], allow_duplicate=True)
    assert exc.value.code == "DUPLICATE_OPEN_REFERRAL"
    assert "can_force" not in exc.value.error_details

    forced = create_referral(
        school=env["school"], membership=env["manager"], roles=["SCHOOL_MANAGER"],
        student=env["students"][0], category=ReferralCategory.ACADEMIC,
        reason_code=ReferralReason.ACADEMIC_WEAKNESS, description="حالة مستقلة.",
        allow_duplicate=True,
    )
    assert forced.id


# ---------- التعيين (البنود 102-105) ----------


@pytest.mark.django_db
def test_assign_active_counselor(env):
    referral = teacher_referral(env)
    assign_counselor(
        referral_id=referral.id, school=env["school"], membership=env["vice"],
        counselor_id=env["counselor"].id,
    )
    referral.refresh_from_db()
    assert referral.assigned_counselor_membership_id == env["counselor"].id
    assert referral.events.filter(event_type=ReferralEventType.ASSIGNED).exists()


@pytest.mark.django_db
def test_foreign_counselor_rejected(env, make_school, make_user, make_membership):
    other_school = make_school()
    foreign = make_membership(make_user("0551300099"), other_school, ["COUNSELOR"])
    referral = teacher_referral(env)
    with pytest.raises(ApiError) as exc:
        assign_counselor(
            referral_id=referral.id, school=env["school"], membership=env["vice"],
            counselor_id=foreign.id,
        )
    assert exc.value.code == "INVALID_COUNSELOR_ASSIGNMENT"


@pytest.mark.django_db
def test_suspended_counselor_rejected(env):
    env["counselor"].status = MembershipStatus.SUSPENDED
    env["counselor"].save(update_fields=["status"])
    referral = teacher_referral(env)
    with pytest.raises(ApiError) as exc:
        assign_counselor(
            referral_id=referral.id, school=env["school"], membership=env["vice"],
            counselor_id=env["counselor"].id,
        )
    assert exc.value.code == "INVALID_COUNSELOR_ASSIGNMENT"


@pytest.mark.django_db
def test_non_counselor_membership_rejected(env):
    referral = teacher_referral(env)
    with pytest.raises(ApiError) as exc:
        assign_counselor(
            referral_id=referral.id, school=env["school"], membership=env["vice"],
            counselor_id=env["teacher2"].id,  # معلم لا مرشد
        )
    assert exc.value.code == "INVALID_COUNSELOR_ASSIGNMENT"


@pytest.mark.django_db
def test_reassignment_keeps_history(env):
    referral = teacher_referral(env)
    assign_counselor(
        referral_id=referral.id, school=env["school"], membership=env["manager"],
        counselor_id=env["counselor"].id,
    )
    assign_counselor(
        referral_id=referral.id, school=env["school"], membership=env["manager"],
        counselor_id=env["counselor2"].id,
    )
    referral.refresh_from_db()
    assert referral.assigned_counselor_membership_id == env["counselor2"].id
    reassign = referral.events.get(event_type=ReferralEventType.REASSIGNED)
    assert reassign.metadata_safe["previous_counselor_membership_id"] == (
        env["counselor"].id
    )


# ---------- الاستلام (البنود 106-108) ----------


@pytest.mark.django_db
def test_assigned_counselor_acknowledges(env):
    referral = teacher_referral(env)
    assign_counselor(
        referral_id=referral.id, school=env["school"], membership=env["vice"],
        counselor_id=env["counselor"].id,
    )
    acknowledge_referral(
        referral_id=referral.id, school=env["school"], membership=env["counselor"],
        roles=["COUNSELOR"],
    )
    referral.refresh_from_db()
    assert referral.status == ReferralStatus.ACKNOWLEDGED
    assert referral.accepted_at is not None


@pytest.mark.django_db
def test_other_counselor_cannot_acknowledge(env):
    """مرشد لا يسحب حالة زميله (بند 55)."""
    referral = teacher_referral(env)
    assign_counselor(
        referral_id=referral.id, school=env["school"], membership=env["vice"],
        counselor_id=env["counselor"].id,
    )
    with pytest.raises(ApiError) as exc:
        acknowledge_referral(
            referral_id=referral.id, school=env["school"], membership=env["counselor2"],
            roles=["COUNSELOR"],
        )
    assert exc.value.code == "REFERRAL_PERMISSION_DENIED"


@pytest.mark.django_db
def test_unassigned_claim_is_atomic(env):
    """استلام حالة غير معينة يجعل المستلم هو المعيّن — والثاني يُرفض."""
    referral = teacher_referral(env)
    acknowledge_referral(
        referral_id=referral.id, school=env["school"], membership=env["counselor"],
        roles=["COUNSELOR"],
    )
    referral.refresh_from_db()
    assert referral.assigned_counselor_membership_id == env["counselor"].id

    with pytest.raises(ApiError) as exc:
        acknowledge_referral(
            referral_id=referral.id, school=env["school"], membership=env["counselor2"],
            roles=["COUNSELOR"],
        )
    assert exc.value.code == "REFERRAL_ALREADY_ACKNOWLEDGED"


@pytest.mark.django_db
def test_double_acknowledge_rejected(env):
    referral = teacher_referral(env)
    acknowledge_referral(
        referral_id=referral.id, school=env["school"], membership=env["counselor"],
        roles=["COUNSELOR"],
    )
    with pytest.raises(ApiError) as exc:
        acknowledge_referral(
            referral_id=referral.id, school=env["school"], membership=env["counselor"],
            roles=["COUNSELOR"],
        )
    assert exc.value.code == "REFERRAL_ALREADY_ACKNOWLEDGED"


# ---------- الإغلاق والإلغاء ----------


@pytest.mark.django_db
def test_close_then_no_more_contributions(env):
    referral = teacher_referral(env)
    close_referral(
        referral_id=referral.id, school=env["school"], membership=env["counselor"],
        reason="عولجت مع ولي الأمر.",
    )
    referral.refresh_from_db()
    assert referral.status == ReferralStatus.CLOSED
    assert referral.closed_at is not None
    with pytest.raises(ApiError) as exc:
        add_contribution(
            referral_id=referral.id, school=env["school"], membership=env["teacher"],
            observation_type=ReferralObservationType.OTHER_OBSERVATION, notes="متأخر",
        )
    assert exc.value.code == "REFERRAL_ALREADY_CLOSED"


@pytest.mark.django_db
def test_cancel_marks_cancelled_not_deleted(env):
    referral = teacher_referral(env)
    close_referral(
        referral_id=referral.id, school=env["school"], membership=env["teacher"],
        reason="أنشئت بالخطأ.", cancel=True,
    )
    referral.refresh_from_db()
    assert referral.status == ReferralStatus.CANCELLED
    assert StudentReferral.objects.filter(id=referral.id).exists()  # لا حذف نهائي


@pytest.mark.django_db
def test_close_twice_rejected(env):
    referral = teacher_referral(env)
    close_referral(
        referral_id=referral.id, school=env["school"], membership=env["manager"],
        reason="أُغلقت.",
    )
    with pytest.raises(ApiError) as exc:
        close_referral(
            referral_id=referral.id, school=env["school"], membership=env["manager"],
            reason="مرة أخرى.",
        )
    assert exc.value.code == "REFERRAL_ALREADY_CLOSED"


# ---------- النطاق والخصوصية (البنود 109-116) ----------


@pytest.mark.django_db
def test_teacher_sees_only_own_referrals(env):
    mine = teacher_referral(env)
    other = teacher_referral(
        env, student=env["students"][1], membership=env["teacher2"]
    )
    visible = teacher_referrals(school=env["school"], membership=env["teacher"])
    assert list(visible.values_list("id", flat=True)) == [mine.id]
    assert not can_view_referral(
        referral=other, membership=env["teacher"], roles=["TEACHER"]
    )


@pytest.mark.django_db
def test_teacher_sees_referral_he_contributed_to(env):
    referral = teacher_referral(env, membership=env["teacher2"])
    add_contribution(
        referral_id=referral.id, school=env["school"], membership=env["teacher"],
        observation_type=ReferralObservationType.CLASSROOM_OBSERVATION,
        notes="لوحظ نفس السلوك في حصتي.",
    )
    assert can_view_referral(
        referral=referral, membership=env["teacher"], roles=["TEACHER"]
    )
    assert teacher_referrals(
        school=env["school"], membership=env["teacher"]
    ).filter(id=referral.id).exists()


@pytest.mark.django_db
def test_counselor_scope_excludes_other_counselor_cases(env):
    mine = teacher_referral(env)
    assign_counselor(
        referral_id=mine.id, school=env["school"], membership=env["vice"],
        counselor_id=env["counselor"].id,
    )
    theirs = teacher_referral(
        env, student=env["students"][1], membership=env["teacher2"]
    )
    assign_counselor(
        referral_id=theirs.id, school=env["school"], membership=env["vice"],
        counselor_id=env["counselor2"].id,
    )
    unassigned = create_referral(
        school=env["school"], membership=env["vice"], roles=["VICE_PRINCIPAL"],
        student=env["students"][0], category=ReferralCategory.ATTENDANCE,
        reason_code=ReferralReason.REPEATED_ABSENCE, description="غياب.",
    )
    visible = set(
        visible_referrals(
            school=env["school"], membership=env["counselor"], roles=["COUNSELOR"]
        ).values_list("id", flat=True)
    )
    assert visible == {mine.id, unassigned.id}  # لا حالة زميله


@pytest.mark.django_db
def test_manager_sees_all(env):
    first = teacher_referral(env)
    second = teacher_referral(
        env, student=env["students"][1], membership=env["teacher2"]
    )
    visible = visible_referrals(
        school=env["school"], membership=env["manager"], roles=["SCHOOL_MANAGER"]
    )
    assert set(visible.values_list("id", flat=True)) == {first.id, second.id}


@pytest.mark.django_db
def test_kpis_scoped_to_role(env):
    referral = teacher_referral(env)
    assign_counselor(
        referral_id=referral.id, school=env["school"], membership=env["vice"],
        counselor_id=env["counselor"].id,
    )
    teacher_referral(env, student=env["students"][1], membership=env["teacher2"])

    manager_kpis = referral_kpis(
        school=env["school"], membership=env["manager"], roles=["SCHOOL_MANAGER"]
    )
    assert manager_kpis["new_count"] == 2
    assert manager_kpis["unassigned_count"] == 1

    counselor2_kpis = referral_kpis(
        school=env["school"], membership=env["counselor2"], roles=["COUNSELOR"]
    )
    assert counselor2_kpis["new_count"] == 1  # غير المعينة فقط


@pytest.mark.django_db
def test_duplicate_lookup_ignores_other_school(env, make_school, make_user, make_membership):
    """التكرار يُفحص داخل المدرسة فقط."""
    other_school = make_school()
    assert (
        find_open_duplicate(
            school=other_school,
            student=env["students"][0],
            category=ReferralCategory.ACADEMIC,
        )
        is None
    )


# ---------- الحذف النهائي (بند 87) ----------


@pytest.mark.django_db
def test_purge_deletes_referrals(env):
    from students.services.purge import purge_student

    student = env["students"][0]
    referral = teacher_referral(env, student=student)
    add_contribution(
        referral_id=referral.id, school=env["school"], membership=env["teacher2"],
        observation_type=ReferralObservationType.OTHER_OBSERVATION, notes="ملاحظة.",
    )
    student.status = "WITHDRAWN"
    student.save(update_fields=["status"])

    deleted, _, _ = purge_student(student)
    assert deleted > 0
    assert not StudentReferral.objects.filter(id=referral.id).exists()
    assert not StudentReferralEvent.objects.filter(referral_id=referral.id).exists()
