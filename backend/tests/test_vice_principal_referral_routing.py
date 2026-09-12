"""اختبارات المسار الديناميكي: معلم ← وكيل النطاق ← مرشد مختار."""

import pytest
from django.db import DatabaseError, transaction

from academics.models import AcademicYear, AcademicYearStatus
from common.errors import ApiError
from referrals.api.serializers import serialize_referral_detail
from referrals.models import (
    ReferralCategory,
    ReferralEventType,
    ReferralReason,
    ReferralStatus,
)
from referrals.selectors import can_view_referral, referral_kpis, visible_referrals
from referrals.services.referrals import (
    acknowledge_referral,
    assign_counselor,
    close_referral,
    create_referral,
    start_vice_review,
)
from staff.models import StaffProfile, VicePrincipalScopeAssignment
from staff.services.vice_principal_scopes import set_vice_principal_scopes
from students.models import Grade, Section
from tests.attendance_helpers import make_students


@pytest.fixture
def routing_env(make_school, make_user, make_membership):
    school = make_school()
    year = AcademicYear.objects.create(
        school=school,
        name="2026/2027",
        start_date="2026-08-01",
        end_date="2027-06-25",
        status=AcademicYearStatus.ACTIVE,
    )
    grade_one = Grade.objects.create(
        school=school, name="الأول الثانوي", code="G1", sequence=1
    )
    grade_two = Grade.objects.create(
        school=school, name="الثاني الثانوي", code="G2", sequence=2
    )
    section_one = Section.objects.create(
        school=school, grade=grade_one, code="1", name="1"
    )
    section_two = Section.objects.create(
        school=school, grade=grade_two, code="1", name="1"
    )
    students_one = make_students(school, section_one, year, 2, prefix="71100")
    students_two = make_students(school, section_two, year, 1, prefix="71200")
    return {
        "school": school,
        "year": year,
        "grade_one": grade_one,
        "grade_two": grade_two,
        "section_one": section_one,
        "section_two": section_two,
        "students_one": students_one,
        "students_two": students_two,
        "teacher": make_membership(make_user("0551710001"), school, ["TEACHER"]),
        "vice_one": make_membership(
            make_user("0551710002"), school, ["VICE_PRINCIPAL"]
        ),
        "vice_two": make_membership(
            make_user("0551710003"), school, ["VICE_PRINCIPAL"]
        ),
        "manager": make_membership(
            make_user("0551710004"), school, ["SCHOOL_MANAGER"]
        ),
        "counselor_one": make_membership(
            make_user("0551710005"), school, ["COUNSELOR"]
        ),
        "counselor_two": make_membership(
            make_user("0551710006"), school, ["COUNSELOR"]
        ),
    }


def teacher_referral(env, student, *, category=ReferralCategory.ACADEMIC):
    reason = (
        ReferralReason.ACADEMIC_WEAKNESS
        if category == ReferralCategory.ACADEMIC
        else ReferralReason.SLEEPING_IN_CLASS
    )
    return create_referral(
        school=env["school"],
        membership=env["teacher"],
        roles=["TEACHER"],
        student=student,
        category=category,
        reason_code=reason,
        description="ملاحظة واضحة تحتاج إلى متابعة.",
    )


@pytest.mark.django_db
def test_grade_routing_with_more_than_one_vice_and_section_override(routing_env):
    env = routing_env
    VicePrincipalScopeAssignment.objects.create(
        school=env["school"],
        grade=env["grade_one"],
        vice_principal_membership=env["vice_one"],
    )
    VicePrincipalScopeAssignment.objects.create(
        school=env["school"],
        grade=env["grade_two"],
        vice_principal_membership=env["vice_two"],
    )

    first = teacher_referral(env, env["students_one"][0])
    second = teacher_referral(env, env["students_two"][0])
    assert first.assigned_vice_membership_id == env["vice_one"].id
    assert second.assigned_vice_membership_id == env["vice_two"].id

    # الفصل المحدد أكثر دقة من الصف الكامل ويأخذ الأولوية في الإحالات الجديدة.
    VicePrincipalScopeAssignment.objects.create(
        school=env["school"],
        section=env["section_one"],
        vice_principal_membership=env["vice_two"],
    )
    overridden = teacher_referral(
        env,
        env["students_one"][1],
        category=ReferralCategory.CLASSROOM_BEHAVIOR,
    )
    assert overridden.assigned_vice_membership_id == env["vice_two"].id


@pytest.mark.django_db
def test_only_responsible_vice_can_process_then_counselor_can_see(routing_env):
    env = routing_env
    VicePrincipalScopeAssignment.objects.create(
        school=env["school"],
        grade=env["grade_one"],
        vice_principal_membership=env["vice_one"],
    )
    referral = teacher_referral(env, env["students_one"][0])

    assert can_view_referral(
        referral=referral,
        membership=env["vice_one"],
        roles=["VICE_PRINCIPAL"],
    )
    assert not can_view_referral(
        referral=referral,
        membership=env["vice_two"],
        roles=["VICE_PRINCIPAL"],
    )
    assert not can_view_referral(
        referral=referral,
        membership=env["counselor_one"],
        roles=["COUNSELOR"],
    )
    with pytest.raises(ApiError) as denied:
        start_vice_review(
            referral_id=referral.id,
            school=env["school"],
            membership=env["vice_two"],
        )
    assert denied.value.code == "REFERRAL_PERMISSION_DENIED"

    start_vice_review(
        referral_id=referral.id,
        school=env["school"],
        membership=env["vice_one"],
    )
    assign_counselor(
        referral_id=referral.id,
        school=env["school"],
        membership=env["vice_one"],
        counselor_id=env["counselor_one"].id,
    )
    referral.refresh_from_db()
    assert referral.status == ReferralStatus.REFERRED
    assert can_view_referral(
        referral=referral,
        membership=env["counselor_one"],
        roles=["COUNSELOR"],
    )
    assert not can_view_referral(
        referral=referral,
        membership=env["counselor_two"],
        roles=["COUNSELOR"],
    )

    acknowledge_referral(
        referral_id=referral.id,
        school=env["school"],
        membership=env["counselor_one"],
        roles=["COUNSELOR"],
    )
    close_referral(
        referral_id=referral.id,
        school=env["school"],
        membership=env["counselor_one"],
        reason="اكتملت خطة المتابعة.",
    )
    referral.refresh_from_db()
    assert referral.status == ReferralStatus.CLOSED
    assert list(
        referral.events.order_by("created_at", "id").values_list(
            "event_type", flat=True
        )
    ) == [
        ReferralEventType.CREATED,
        ReferralEventType.ROUTED_TO_VICE,
        ReferralEventType.VICE_REVIEW_STARTED,
        ReferralEventType.FORWARDED_TO_COUNSELOR,
        ReferralEventType.ACKNOWLEDGED,
        ReferralEventType.CLOSED,
    ]


@pytest.mark.django_db
def test_scope_transfer_requires_confirmation_and_does_not_rewrite_history(routing_env):
    env = routing_env
    set_vice_principal_scopes(
        school=env["school"],
        membership=env["vice_one"],
        grade_ids=[env["grade_one"].id],
        section_ids=[],
        actor=env["manager"].user,
    )
    historical = teacher_referral(env, env["students_one"][0])

    with pytest.raises(ApiError) as conflict:
        set_vice_principal_scopes(
            school=env["school"],
            membership=env["vice_two"],
            grade_ids=[env["grade_one"].id],
            section_ids=[],
            actor=env["manager"].user,
        )
    assert conflict.value.code == "VICE_PRINCIPAL_SCOPE_REASSIGNMENT_REQUIRED"

    set_vice_principal_scopes(
        school=env["school"],
        membership=env["vice_two"],
        grade_ids=[env["grade_one"].id],
        section_ids=[],
        actor=env["manager"].user,
        confirm_reassignment=True,
    )
    new_referral = teacher_referral(
        env,
        env["students_one"][1],
        category=ReferralCategory.CLASSROOM_BEHAVIOR,
    )
    historical.refresh_from_db()
    assert historical.assigned_vice_membership_id == env["vice_one"].id
    assert new_referral.assigned_vice_membership_id == env["vice_two"].id


@pytest.mark.django_db
def test_missing_scope_becomes_manager_exception_without_counselor_exposure(routing_env):
    env = routing_env
    referral = teacher_referral(env, env["students_one"][0])
    assert referral.status == ReferralStatus.PENDING_VICE
    assert referral.assigned_vice_membership_id is None
    assert not visible_referrals(
        school=env["school"],
        membership=env["vice_one"],
        roles=["VICE_PRINCIPAL"],
    ).filter(id=referral.id).exists()
    assert not visible_referrals(
        school=env["school"],
        membership=env["counselor_one"],
        roles=["COUNSELOR"],
    ).filter(id=referral.id).exists()
    manager_kpis = referral_kpis(
        school=env["school"],
        membership=env["manager"],
        roles=["SCHOOL_MANAGER"],
    )
    assert manager_kpis["unassigned_vice_count"] == 1

    payload = serialize_referral_detail(
        referral,
        membership=env["manager"],
        roles=["SCHOOL_MANAGER"],
    )
    assert payload["can_assign_vice_principal"] is True
    assert payload["can_start_vice_review"] is False
    assert payload["can_forward_to_counselor"] is False

    with pytest.raises(ApiError) as start_error:
        start_vice_review(
            referral_id=referral.id,
            school=env["school"],
            membership=env["manager"],
            is_manager=True,
        )
    assert start_error.value.code == "REFERRAL_VICE_PRINCIPAL_REQUIRED"

    with pytest.raises(ApiError) as forward_error:
        assign_counselor(
            referral_id=referral.id,
            school=env["school"],
            membership=env["manager"],
            roles=["SCHOOL_MANAGER"],
            counselor_id=env["counselor_one"].id,
        )
    assert forward_error.value.code == "REFERRAL_VICE_PRINCIPAL_REQUIRED"


@pytest.mark.django_db
def test_manager_configures_vice_scope_through_staff_api_atomically(role_client):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    grade = Grade.objects.create(
        school=school, name="الأول الثانوي", code="G1", sequence=1
    )
    section = Section.objects.create(
        school=school, grade=grade, code="1", name="1"
    )
    first = manager.post(
        "/api/v1/staff/",
        {
            "display_name": "الوكيل الأول",
            "mobile": "0551710021",
            "role": "VICE_PRINCIPAL",
            "vice_principal_grade_ids": [grade.id],
            "vice_principal_section_ids": [],
        },
        content_type="application/json",
    )
    assert first.status_code == 201
    assert first.json()["vice_principal_scopes"] == [
        {"kind": "GRADE", "id": grade.id, "name": grade.name}
    ]

    blocked = manager.post(
        "/api/v1/staff/",
        {
            "display_name": "الوكيل الثاني",
            "mobile": "0551710022",
            "role": "VICE_PRINCIPAL",
            "vice_principal_grade_ids": [grade.id],
            "vice_principal_section_ids": [section.id],
        },
        content_type="application/json",
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "VICE_PRINCIPAL_SCOPE_REASSIGNMENT_REQUIRED"
    assert not StaffProfile.objects.filter(display_name="الوكيل الثاني").exists()

    moved = manager.post(
        "/api/v1/staff/",
        {
            "display_name": "الوكيل الثاني",
            "mobile": "0551710022",
            "role": "VICE_PRINCIPAL",
            "vice_principal_grade_ids": [grade.id],
            "vice_principal_section_ids": [section.id],
            "confirm_scope_reassignment": True,
        },
        content_type="application/json",
    )
    assert moved.status_code == 201
    assert VicePrincipalScopeAssignment.objects.get(
        school=school, grade=grade
    ).vice_principal_membership.staff_profile.id == moved.json()["id"]


@pytest.mark.django_db(transaction=True)
def test_database_rejects_cross_school_vice_scope(
    make_school, make_user, make_membership
):
    school_one = make_school("مدرسة نطاق أ")
    school_two = make_school("مدرسة نطاق ب")
    grade_two = Grade.objects.create(
        school=school_two, name="الأول الثانوي", code="G1", sequence=1
    )
    vice_one = make_membership(
        make_user("0551710031"), school_one, ["VICE_PRINCIPAL"]
    )

    with pytest.raises(DatabaseError, match="cross-school foreign key rejected"):
        with transaction.atomic():
            VicePrincipalScopeAssignment.objects.create(
                school=school_one,
                grade=grade_two,
                vice_principal_membership=vice_one,
            )
