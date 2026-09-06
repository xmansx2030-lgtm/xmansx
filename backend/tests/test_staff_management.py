"""اختبارات: الدليل، الأدوار، الإيقاف، الدعوات، كلمة المرور الأولية، العزل."""

import pytest
from django.test import Client

from accounts.models import User
from audit.models import AuditAction, AuditLog
from memberships.models import MembershipStatus, SchoolMembership
from staff.models import StaffProfile
from tests.conftest import PASSWORD

STAFF_URL = "/api/v1/staff/"


def _make_staff(school, user, roles, display_name="موظف", status=MembershipStatus.ACTIVE):
    from memberships.models import SchoolMembershipRole

    membership = SchoolMembership.objects.create(user=user, school=school, status=status)
    for role in roles:
        SchoolMembershipRole.objects.create(membership=membership, role=role)
    profile = StaffProfile.objects.create(
        school=school, membership=membership, display_name=display_name
    )
    return membership, profile


# ---------- StaffProfile ----------


@pytest.mark.django_db
def test_same_user_different_profiles_per_school(make_user, make_school):
    user = make_user("0558880001")
    a, b = make_school(), make_school()
    _, profile_a = _make_staff(a, user, ["TEACHER"], display_name="أحمد الغامدي")
    _, profile_b = _make_staff(b, user, ["TEACHER"], display_name="أ. أحمد")
    assert profile_a.display_name != profile_b.display_name
    assert profile_a.school_id != profile_b.school_id


@pytest.mark.django_db
def test_one_profile_per_membership(make_user, make_school):
    from django.db import IntegrityError, transaction

    user = make_user("0558880002")
    school = make_school()
    membership, _ = _make_staff(school, user, ["TEACHER"])
    with pytest.raises(IntegrityError), transaction.atomic():
        StaffProfile.objects.create(school=school, membership=membership, display_name="آخر")


# ---------- Directory ----------


@pytest.mark.django_db
def test_manager_creates_staff_manually_with_one_time_password(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    response = client.post(
        STAFF_URL,
        {
            "display_name": "معلم يدوي",
            "mobile": "0557771111",
            "employee_number": "T-900",
            "job_title": "معلم رياضيات",
            "role": "TEACHER",
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["display_name"] == "معلم يدوي"
    assert body["temporary_password"] == "0557771111"
    assert body["invitation_sent"] is False
    user = User.objects.get(mobile="+966557771111")
    assert user.must_change_password is True
    assert user.check_password(body["temporary_password"])
    assert StaffProfile.objects.get(school=school, membership__user=user).source == "MANUAL"


@pytest.mark.django_db
def test_manual_staff_invites_existing_account(role_client, make_user):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    existing = make_user("0557772222")
    response = client.post(
        STAFF_URL,
        {"display_name": "موظف مدعو", "mobile": "0557772222", "role": "COUNSELOR"},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["temporary_password"] is None
    assert response.json()["invitation_sent"] is True
    membership = SchoolMembership.objects.get(school=school, user=existing)
    assert membership.status == MembershipStatus.INVITED
    assert membership.role_codes() == ["COUNSELOR"]


@pytest.mark.django_db
def test_directory_masks_mobile_in_list_full_in_detail(role_client, make_user):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    user = make_user("0558880003")
    _, profile = _make_staff(school, user, ["TEACHER"], display_name="معلم القائمة")

    listed = client.get(STAFF_URL).json()["results"]
    row = next(r for r in listed if r["display_name"] == "معلم القائمة")
    assert "+966558880003" not in row["mobile"]
    assert row["mobile"].endswith("0003")

    detail = client.get(f"{STAFF_URL}{profile.id}/").json()
    assert detail["mobile"] == "+966558880003"  # الكامل للمدير في التفاصيل فقط


@pytest.mark.django_db
def test_vice_reads_directory_but_no_detail_or_manage(role_client, make_user, make_school):
    school = make_school()
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=school)
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=school)
    user = make_user("0558880004")
    _, profile = _make_staff(school, user, ["TEACHER"])

    assert vice.get(STAFF_URL).status_code == 200
    assert vice.get(f"{STAFF_URL}{profile.id}/").status_code == 403
    assert vice.post(
        f"{STAFF_URL}{profile.id}/roles/", {"role": "COUNSELOR"},
        content_type="application/json",
    ).status_code == 403


@pytest.mark.django_db
def test_teacher_and_counselor_denied_directory(role_client, make_school):
    school = make_school()
    teacher, _, _ = role_client(["TEACHER"], school=school)
    counselor, _, _ = role_client(["COUNSELOR"], school=school)
    assert teacher.get(STAFF_URL).status_code == 403
    assert counselor.get(STAFF_URL).status_code == 403


@pytest.mark.django_db
def test_directory_query_count(role_client, make_user, django_assert_max_num_queries):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    for i in range(20):
        _make_staff(school, make_user(f"05588801{i:02d}"), ["TEACHER"], f"موظف {i}")
    with django_assert_max_num_queries(10):
        response = client.get(STAFF_URL)
    assert response.status_code == 200


# ---------- Roles & suspension ----------


@pytest.mark.django_db
def test_role_add_remove_with_guards(role_client, make_user):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    user = make_user("0558880005")
    _, profile = _make_staff(school, user, ["TEACHER"])

    add = client.post(
        f"{STAFF_URL}{profile.id}/roles/", {"role": "COUNSELOR"},
        content_type="application/json",
    )
    assert add.status_code == 200
    assert sorted(add.json()["roles"]) == ["COUNSELOR", "TEACHER"]

    again = client.post(
        f"{STAFF_URL}{profile.id}/roles/", {"role": "COUNSELOR"},
        content_type="application/json",
    )
    assert again.json()["code"] == "ROLE_ALREADY_ASSIGNED"

    remove = client.delete(f"{STAFF_URL}{profile.id}/roles/COUNSELOR/")
    assert remove.status_code == 200
    missing = client.delete(f"{STAFF_URL}{profile.id}/roles/COUNSELOR/")
    assert missing.json()["code"] == "ROLE_NOT_ASSIGNED"

    # آخر دور: يرفض مع توجيه للإيقاف
    last = client.delete(f"{STAFF_URL}{profile.id}/roles/TEACHER/")
    assert last.json()["code"] == "LAST_ROLE_SUSPEND_INSTEAD"


@pytest.mark.django_db
def test_last_manager_protection(role_client):
    """المدير الوحيد: لا إزالة دوره ولا إيقافه."""
    client, school, manager_user = role_client(["SCHOOL_MANAGER"])
    membership = SchoolMembership.objects.get(user=manager_user, school=school)
    profile = StaffProfile.objects.create(
        school=school, membership=membership, display_name="المدير"
    )
    remove = client.delete(f"{STAFF_URL}{profile.id}/roles/SCHOOL_MANAGER/")
    assert remove.status_code == 409
    assert remove.json()["code"] == "LAST_SCHOOL_MANAGER_REQUIRED"

    suspend = client.post(f"{STAFF_URL}{profile.id}/suspend/")
    assert suspend.status_code == 409
    assert suspend.json()["code"] == "LAST_SCHOOL_MANAGER_REQUIRED"


@pytest.mark.django_db
def test_suspend_does_not_affect_other_schools(role_client, make_user, make_membership,
                                                make_school):
    client, school_a, _ = role_client(["SCHOOL_MANAGER"])
    school_b = make_school()
    user = make_user("0558880006")
    _, profile_a = _make_staff(school_a, user, ["TEACHER"])
    membership_b = make_membership(user, school_b, ["TEACHER"])

    assert client.post(f"{STAFF_URL}{profile_a.id}/suspend/").status_code == 200
    membership_b.refresh_from_db()
    assert membership_b.status == MembershipStatus.ACTIVE  # مدرسة B لم تتأثر
    user.refresh_from_db()
    assert user.is_active is True  # الحساب العالمي لم يمس

    assert client.post(f"{STAFF_URL}{profile_a.id}/activate/").status_code == 200


@pytest.mark.django_db
def test_manager_permanently_deletes_staff_from_school_only(
    role_client, make_user, make_membership, make_school
):
    client, school_a, _ = role_client(["SCHOOL_MANAGER"])
    school_b = make_school()
    user = make_user("0558880060")
    membership_a, profile_a = _make_staff(school_a, user, ["TEACHER"])
    membership_b = make_membership(user, school_b, ["TEACHER"])

    response = client.delete(f"{STAFF_URL}{profile_a.id}/")

    assert response.status_code == 204
    assert not StaffProfile.objects.filter(id=profile_a.id).exists()
    membership_a.refresh_from_db()
    assert membership_a.status == MembershipStatus.LEFT
    assert membership_a.roles.count() == 0
    membership_b.refresh_from_db()
    assert membership_b.status == MembershipStatus.ACTIVE
    user.refresh_from_db()
    assert user.is_active is True


@pytest.mark.django_db
def test_permanent_delete_is_only_available_on_staff_detail_url(role_client, make_user):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    _, profile = _make_staff(school, make_user("0558880062"), ["TEACHER"])

    response = client.delete(f"{STAFF_URL}{profile.id}/suspend/")

    assert response.status_code == 405
    assert StaffProfile.objects.filter(id=profile.id).exists()


@pytest.mark.django_db
def test_deleted_staff_can_be_added_again_by_invitation(role_client, make_user):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    user = make_user("0558880061")
    membership, profile = _make_staff(school, user, ["TEACHER"], "موظف سابق")
    assert client.delete(f"{STAFF_URL}{profile.id}/").status_code == 204

    response = client.post(
        STAFF_URL,
        {"display_name": "موظف عائد", "mobile": "0558880061", "role": "TEACHER"},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["invitation_sent"] is True
    membership.refresh_from_db()
    assert membership.status == MembershipStatus.INVITED
    assert membership.role_codes() == ["TEACHER"]
    assert StaffProfile.objects.filter(membership=membership, display_name="موظف عائد").exists()


@pytest.mark.django_db
def test_manager_cannot_delete_self_from_staff(role_client):
    client, school, manager_user = role_client(["SCHOOL_MANAGER"])
    membership = SchoolMembership.objects.get(user=manager_user, school=school)
    profile = StaffProfile.objects.create(
        school=school, membership=membership, display_name="المدير الحالي"
    )

    response = client.delete(f"{STAFF_URL}{profile.id}/")

    assert response.status_code == 409
    assert response.json()["code"] == "SELF_STAFF_DELETE_NOT_ALLOWED"
    assert StaffProfile.objects.filter(id=profile.id).exists()


@pytest.mark.django_db
def test_staff_tenant_isolation(role_client, make_user):
    manager_a, _, _ = role_client(["SCHOOL_MANAGER"])
    manager_b, school_b, _ = role_client(["SCHOOL_MANAGER"])
    user = make_user("0558880007")
    _, foreign_profile = _make_staff(school_b, user, ["TEACHER"])

    assert manager_a.get(f"{STAFF_URL}{foreign_profile.id}/").status_code == 404
    assert manager_a.patch(
        f"{STAFF_URL}{foreign_profile.id}/", {"display_name": "اختراق"},
        content_type="application/json",
    ).status_code == 404
    assert manager_a.post(
        f"{STAFF_URL}{foreign_profile.id}/roles/", {"role": "TEACHER"},
        content_type="application/json",
    ).status_code == 404
    assert manager_a.post(f"{STAFF_URL}{foreign_profile.id}/suspend/").status_code == 404
    assert manager_a.delete(f"{STAFF_URL}{foreign_profile.id}/").status_code == 404


# ---------- Manager password reset ----------


@pytest.mark.django_db
def test_manager_resets_teacher_password_to_mobile_and_forces_change(role_client, make_user):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    teacher = make_user("0558880070")
    _, profile = _make_staff(school, teacher, ["TEACHER"], "معلم كلمة المرور")

    response = client.post(f"{STAFF_URL}{profile.id}/reset-password/")

    assert response.status_code == 200
    assert response.json() == {
        "temporary_password": "0558880070",
        "must_change_password": True,
    }
    teacher.refresh_from_db()
    assert teacher.must_change_password is True
    assert teacher.check_password("0558880070")
    assert not teacher.check_password(PASSWORD)
    login = Client().post(
        "/api/v1/auth/login/",
        {"mobile": "0558880070", "password": "0558880070"},
        content_type="application/json",
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True
    assert AuditLog.objects.filter(
        action=AuditAction.STAFF_PASSWORD_RESET,
        school=school,
        target_id=str(profile.membership_id),
    ).exists()


@pytest.mark.django_db
def test_password_reset_requires_manager_same_school_and_teacher_role(
    role_client, make_user, make_school
):
    school = make_school()
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=school)
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=school)
    _, counselor_profile = _make_staff(
        school, make_user("0558880071"), ["COUNSELOR"], "مرشد فقط"
    )
    _, other_school, _ = role_client(["SCHOOL_MANAGER"])
    _, foreign_teacher = _make_staff(
        other_school, make_user("0558880072"), ["TEACHER"], "معلم مدرسة أخرى"
    )

    assert vice.post(
        f"{STAFF_URL}{counselor_profile.id}/reset-password/"
    ).status_code == 403
    teacher_required = manager.post(
        f"{STAFF_URL}{counselor_profile.id}/reset-password/"
    )
    assert teacher_required.status_code == 409
    assert teacher_required.json()["code"] == "TEACHER_ROLE_REQUIRED"
    assert manager.post(
        f"{STAFF_URL}{foreign_teacher.id}/reset-password/"
    ).status_code == 404


@pytest.mark.django_db
def test_manager_cannot_reset_password_for_teacher_shared_with_another_school(
    role_client, make_user, make_membership, make_school
):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    teacher = make_user("0558880073")
    _, profile = _make_staff(school, teacher, ["TEACHER"], "معلم مشترك")
    make_membership(teacher, make_school(), ["TEACHER"])

    response = manager.post(f"{STAFF_URL}{profile.id}/reset-password/")

    assert response.status_code == 409
    assert response.json()["code"] == "SHARED_ACCOUNT_PASSWORD_RESET_NOT_ALLOWED"
    teacher.refresh_from_db()
    assert teacher.check_password(PASSWORD)
    assert teacher.must_change_password is False


# ---------- Invitations ----------


@pytest.mark.django_db
def test_invitation_accept_flow(make_user, make_membership, make_school, login_client):
    user = make_user("0558880008")
    school_a, school_b = make_school("مدرسته"), make_school("الداعية")
    make_membership(user, school_a, ["TEACHER"])
    invited = SchoolMembership.objects.create(
        user=user, school=school_b, status=MembershipStatus.INVITED
    )
    from memberships.models import SchoolMembershipRole

    SchoolMembershipRole.objects.create(membership=invited, role="TEACHER")

    client, login = login_client("0558880008")
    body = login.json()
    assert len(body["invitations"]) == 1
    assert body["invitations"][0]["school"]["name"] == "الداعية"

    accept = client.post(f"/api/v1/auth/invitations/{invited.id}/accept/")
    assert accept.status_code == 200
    accepted_body = accept.json()
    assert accepted_body["invitations"] == []
    assert len(accepted_body["memberships"]) == 2  # المدرستان في الـ Switcher

    again = client.post(f"/api/v1/auth/invitations/{invited.id}/accept/")
    assert again.json()["code"] == "INVITATION_ALREADY_ACCEPTED"


@pytest.mark.django_db
def test_invitation_decline_flow(make_user, make_membership, make_school, login_client):
    user = make_user("0558880009")
    make_membership(user, make_school(), ["TEACHER"])
    school_b = make_school()
    invited = SchoolMembership.objects.create(
        user=user, school=school_b, status=MembershipStatus.INVITED
    )
    client, _ = login_client("0558880009")
    decline = client.post(f"/api/v1/auth/invitations/{invited.id}/decline/")
    assert decline.status_code == 200
    invited.refresh_from_db()
    assert invited.status == MembershipStatus.DECLINED  # لا حذف

    again = client.post(f"/api/v1/auth/invitations/{invited.id}/decline/")
    assert again.json()["code"] == "INVITATION_ALREADY_DECLINED"


@pytest.mark.django_db
def test_cannot_touch_others_invitation(make_user, make_membership, make_school, login_client):
    victim = make_user("0558880010")
    school = make_school()
    invited = SchoolMembership.objects.create(
        user=victim, school=school, status=MembershipStatus.INVITED
    )
    attacker = make_user("0558880011")
    make_membership(attacker, make_school(), ["TEACHER"])
    client, _ = login_client("0558880011")
    response = client.post(f"/api/v1/auth/invitations/{invited.id}/accept/")
    assert response.status_code == 404
    assert response.json()["code"] == "INVITATION_NOT_FOUND"


# ---------- Initial password ----------


@pytest.mark.django_db
def test_initial_password_change_full_flow(make_user, make_membership, make_school):
    user = User.objects.create_user(
        mobile="0558880012", password="Temp-12345", must_change_password=True
    )
    make_membership(user, make_school(), ["TEACHER"])

    client = Client()
    login = client.post(
        "/api/v1/auth/login/",
        {"mobile": "0558880012", "password": "Temp-12345"},
        content_type="application/json",
    )
    assert login.json()["must_change_password"] is True

    # البوابة: endpoint مدرسي محجوب قبل التغيير
    blocked = client.get("/api/v1/students/")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "INITIAL_PASSWORD_CHANGE_REQUIRED"

    # كلمة حالية خاطئة
    wrong = client.post(
        "/api/v1/auth/change-initial-password/",
        {"current_password": "خطأ", "new_password": "Jadeed-9x", "confirm_password": "Jadeed-9x"},
        content_type="application/json",
    )
    assert wrong.json()["code"] == "INVALID_CURRENT_PASSWORD"

    # كلمة ضعيفة
    weak = client.post(
        "/api/v1/auth/change-initial-password/",
        {"current_password": "Temp-12345", "new_password": "1234", "confirm_password": "1234"},
        content_type="application/json",
    )
    assert weak.status_code == 400

    # نجاح
    change = client.post(
        "/api/v1/auth/change-initial-password/",
        {
            "current_password": "Temp-12345",
            "new_password": "Jadeed-9x!",
            "confirm_password": "Jadeed-9x!",
        },
        content_type="application/json",
    )
    assert change.status_code == 200
    assert change.json()["must_change_password"] is False
    # الجلسة بقيت صالحة بعد التغيير (update_session_auth_hash)
    assert client.get("/api/v1/auth/me/").status_code == 200
    assert client.get("/api/v1/students/").status_code == 403  # الآن حسب الدور لا البوابة

    # القديمة توقفت والجديدة تعمل
    fresh = Client()
    old = fresh.post(
        "/api/v1/auth/login/",
        {"mobile": "0558880012", "password": "Temp-12345"},
        content_type="application/json",
    )
    assert old.status_code == 401
    new = fresh.post(
        "/api/v1/auth/login/",
        {"mobile": "0558880012", "password": "Jadeed-9x!"},
        content_type="application/json",
    )
    assert new.status_code == 200
    assert new.json()["must_change_password"] is False


@pytest.mark.django_db
def test_change_initial_password_only_for_temp_accounts(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    response = client.post(
        "/api/v1/auth/change-initial-password/",
        {
            "current_password": PASSWORD,
            "new_password": "Aaaa-1234",
            "confirm_password": "Aaaa-1234",
        },
        content_type="application/json",
    )
    assert response.status_code == 409  # لا كلمة مؤقتة لديه
