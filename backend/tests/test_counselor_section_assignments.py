"""توزيع الفصول على المرشدين والتوجيه التلقائي للإحالات."""

import pytest

from academics.models import AcademicYear, AcademicYearStatus
from referrals.models import ReferralCategory, ReferralReason
from referrals.services.referrals import create_referral
from staff.models import CounselorSectionAssignment, StaffProfile
from staff.services.counselor_sections import set_counselor_sections
from students.models import Grade, Section
from tests.attendance_helpers import make_students

STAFF_URL = "/api/v1/staff/"


def make_sections(school, count=3):
    grade = Grade.objects.create(
        school=school, name="الأول الثانوي", code="G1", sequence=1
    )
    return [
        Section.objects.create(
            school=school, grade=grade, name=str(index), code=str(index)
        )
        for index in range(1, count + 1)
    ]


def add_counselor(client, mobile, section_ids=None, confirm=False):
    body = {
        "display_name": f"مرشد {mobile[-2:]}",
        "mobile": mobile,
        "role": "COUNSELOR",
        "confirm_section_reassignment": confirm,
    }
    if section_ids is not None:
        body["counselor_section_ids"] = section_ids
    return client.post(STAFF_URL, body, content_type="application/json")


@pytest.mark.django_db
def test_adding_counselor_with_no_selection_assigns_all_sections(role_client):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    sections = make_sections(school)

    response = add_counselor(manager, "0557710001")

    assert response.status_code == 201
    assert response.json()["counselor_section_count"] == 3
    assert CounselorSectionAssignment.objects.filter(
        school=school,
        counselor_membership__staff_profile__id=response.json()["id"],
    ).count() == len(sections)


@pytest.mark.django_db
def test_manager_selects_specific_sections_and_edits_them_later(role_client):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    first, second, third = make_sections(school)
    created = add_counselor(manager, "0557710002", [first.id, second.id])
    staff_id = created.json()["id"]

    updated = manager.patch(
        f"{STAFF_URL}{staff_id}/counselor-sections/",
        {"counselor_section_ids": [third.id]},
        content_type="application/json",
    )

    assert updated.status_code == 200
    assert [item["id"] for item in updated.json()["counselor_sections"]] == [third.id]


@pytest.mark.django_db
def test_section_transfer_requires_explicit_confirmation_and_creation_is_atomic(
    role_client,
):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    section = make_sections(school, count=1)[0]
    first = add_counselor(manager, "0557710003", [section.id])
    first_staff_id = first.json()["id"]

    blocked = add_counselor(manager, "0557710004", [section.id])

    assert blocked.status_code == 409
    assert blocked.json()["code"] == "COUNSELOR_SECTION_REASSIGNMENT_REQUIRED"
    assert blocked.json()["details"]["conflicts"][0]["section_id"] == section.id
    assert not StaffProfile.objects.filter(display_name="مرشد 04").exists()

    moved = add_counselor(manager, "0557710004", [section.id], confirm=True)
    assert moved.status_code == 201
    assignment = CounselorSectionAssignment.objects.get(section=section)
    assert assignment.counselor_membership.staff_profile.id == moved.json()["id"]
    assert assignment.counselor_membership.staff_profile.id != first_staff_id


@pytest.mark.django_db
def test_vice_principal_cannot_change_counselor_sections(
    role_client, make_user, make_membership
):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=school)
    section = make_sections(school, count=1)[0]
    counselor = make_membership(make_user("0557710005"), school, ["COUNSELOR"])
    profile = StaffProfile.objects.create(
        school=school, membership=counselor, display_name="مرشد المدرسة"
    )

    assert manager.patch(
        f"{STAFF_URL}{profile.id}/counselor-sections/",
        {"counselor_section_ids": [section.id]},
        content_type="application/json",
    ).status_code == 200
    assert vice.patch(
        f"{STAFF_URL}{profile.id}/counselor-sections/",
        {"counselor_section_ids": []},
        content_type="application/json",
    ).status_code == 403


@pytest.mark.django_db
def test_teacher_referral_routes_to_the_active_counselor_for_student_section(
    make_school, make_user, make_membership
):
    school = make_school()
    section = make_sections(school, count=1)[0]
    year = AcademicYear.objects.create(
        school=school,
        name="2026/2027",
        start_date="2026-08-01",
        end_date="2027-06-25",
        status=AcademicYearStatus.ACTIVE,
    )
    student = make_students(school, section, year, 1, prefix="77100")[0]
    manager = make_membership(make_user("0557710010"), school, ["SCHOOL_MANAGER"])
    teacher = make_membership(make_user("0557710011"), school, ["TEACHER"])
    counselor = make_membership(make_user("0557710012"), school, ["COUNSELOR"])
    set_counselor_sections(
        school=school,
        membership=counselor,
        section_ids=[section.id],
        actor=manager.user,
    )

    referral = create_referral(
        school=school,
        membership=teacher,
        roles=["TEACHER"],
        student=student,
        category=ReferralCategory.ACADEMIC,
        reason_code=ReferralReason.ACADEMIC_WEAKNESS,
        description="تراجع ملحوظ في أداء الطالب.",
    )

    assert referral.assigned_counselor_membership_id == counselor.id
    assigned_event = referral.events.get(event_type="ASSIGNED")
    assert assigned_event.metadata_safe["automatic"] is True


@pytest.mark.django_db
def test_changing_section_owner_does_not_rewrite_existing_referrals(
    make_school, make_user, make_membership
):
    school = make_school()
    section = make_sections(school, count=1)[0]
    year = AcademicYear.objects.create(
        school=school,
        name="2026/2027",
        start_date="2026-08-01",
        end_date="2027-06-25",
        status=AcademicYearStatus.ACTIVE,
    )
    student = make_students(school, section, year, 1, prefix="77200")[0]
    manager = make_membership(make_user("0557720010"), school, ["SCHOOL_MANAGER"])
    teacher = make_membership(make_user("0557720011"), school, ["TEACHER"])
    first = make_membership(make_user("0557720012"), school, ["COUNSELOR"])
    second = make_membership(make_user("0557720013"), school, ["COUNSELOR"])
    set_counselor_sections(
        school=school, membership=first, section_ids=[section.id], actor=manager.user
    )
    referral = create_referral(
        school=school,
        membership=teacher,
        roles=["TEACHER"],
        student=student,
        category=ReferralCategory.ACADEMIC,
        reason_code=ReferralReason.ACADEMIC_WEAKNESS,
        description="ضعف دراسي.",
    )

    set_counselor_sections(
        school=school,
        membership=second,
        section_ids=[section.id],
        actor=manager.user,
        confirm_reassignment=True,
    )

    referral.refresh_from_db()
    assert referral.assigned_counselor_membership_id == first.id
    assert CounselorSectionAssignment.objects.get(section=section).counselor_membership_id == (
        second.id
    )
