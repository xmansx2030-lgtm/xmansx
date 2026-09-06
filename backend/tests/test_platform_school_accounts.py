import pytest

from accounts.models import User
from memberships.models import MembershipStatus, SchoolRole
from schools.models import SchoolStatus


@pytest.fixture
def platform_admin(make_user):
    return make_user("0550099001", is_staff=True, is_superuser=True)


@pytest.mark.django_db
def test_platform_school_detail_exposes_and_updates_operational_account_data(
    client, make_school, make_user, make_membership, platform_admin
):
    school = make_school("مدرسة الإدارة")
    manager = make_user("0550099002", first_name="المدير الأول")
    membership = make_membership(manager, school, [SchoolRole.SCHOOL_MANAGER])
    client.force_login(platform_admin)

    detail = client.get(f"/api/v1/platform/schools/{school.id}/")

    assert detail.status_code == 200
    payload = detail.json()
    assert payload["created_at"]
    assert payload["managers"] == [
        {
            "membership_id": membership.id,
            "user_id": manager.id,
            "name": "المدير الأول",
            "mobile": "+966550099002",
            "membership_status": MembershipStatus.ACTIVE,
            "account_active": True,
            "must_change_password": False,
            "last_login": None,
            "joined_at": payload["managers"][0]["joined_at"],
            "shared_with_other_schools": False,
        }
    ]

    updated = client.patch(
        f"/api/v1/platform/schools/{school.id}/",
        {"name": "مدرسة الإدارة المطورة", "school_status": SchoolStatus.SUSPENDED},
        content_type="application/json",
    )

    assert updated.status_code == 200
    school.refresh_from_db()
    assert school.name == "مدرسة الإدارة المطورة"
    assert school.status == SchoolStatus.SUSPENDED


@pytest.mark.django_db
def test_platform_admin_adds_edits_and_resets_school_manager_credentials(
    client, make_school, platform_admin
):
    school = make_school("مدرسة الحسابات")
    client.force_login(platform_admin)

    created = client.post(
        f"/api/v1/platform/schools/{school.id}/managers/",
        {"name": "مدير الحسابات", "mobile": "0550099003"},
        content_type="application/json",
    )

    assert created.status_code == 201
    created_payload = created.json()
    temporary_password = created_payload["temporary_password"]
    membership_id = created_payload["manager"]["membership_id"]
    assert temporary_password
    manager = User.objects.get(mobile="+966550099003")
    assert manager.check_password(temporary_password)
    assert manager.must_change_password is True

    updated = client.patch(
        f"/api/v1/platform/schools/{school.id}/managers/{membership_id}/",
        {"name": "مدير المدرسة الجديد", "mobile": "0550099004"},
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "مدير المدرسة الجديد"
    assert updated.json()["mobile"] == "+966550099004"

    reset = client.post(
        f"/api/v1/platform/schools/{school.id}/managers/{membership_id}/reset-password/"
    )
    assert reset.status_code == 200
    new_password = reset.json()["temporary_password"]
    assert new_password and new_password != temporary_password
    manager.refresh_from_db()
    assert manager.check_password(new_password)
    assert manager.must_change_password is True


@pytest.mark.django_db
def test_platform_manager_suspend_preserves_last_manager_safety(
    client, make_school, make_user, make_membership, platform_admin
):
    school = make_school("مدرسة الحماية")
    first = make_user("0550099005", first_name="المدير الأساسي")
    first_membership = make_membership(first, school, [SchoolRole.SCHOOL_MANAGER])
    client.force_login(platform_admin)

    blocked = client.post(
        f"/api/v1/platform/schools/{school.id}/managers/{first_membership.id}/suspend/"
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "LAST_SCHOOL_MANAGER_REQUIRED"

    second = client.post(
        f"/api/v1/platform/schools/{school.id}/managers/",
        {"name": "المدير البديل", "mobile": "0550099006"},
        content_type="application/json",
    )
    assert second.status_code == 201

    suspended = client.post(
        f"/api/v1/platform/schools/{school.id}/managers/{first_membership.id}/suspend/"
    )
    assert suspended.status_code == 200
    assert suspended.json()["membership_status"] == MembershipStatus.SUSPENDED

    reactivated = client.post(
        f"/api/v1/platform/schools/{school.id}/managers/{first_membership.id}/reactivate/"
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["membership_status"] == MembershipStatus.ACTIVE
