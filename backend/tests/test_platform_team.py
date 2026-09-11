import pytest
from rest_framework.test import APIClient

from accounts.api.serializers import build_me_payload
from accounts.models import User
from platform_team.access import PlatformCapability
from platform_team.models import PlatformStaffMembership, PlatformStaffRole, PlatformStaffStatus

pytestmark = pytest.mark.django_db


def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def make_owner(mobile="+966511111111"):
    return User.objects.create_superuser(
        mobile=mobile, password="OwnerPass!42", first_name="مالك المنصة"
    )


def test_owner_can_create_platform_employee_without_granting_superuser():
    owner = make_owner()
    response = auth_client(owner).post(
        "/api/v1/platform/team/",
        {
            "name": "سارة الدعم",
            "mobile": "0522222222",
            "role": PlatformStaffRole.SUPPORT,
            "job_title": "أخصائية نجاح المدارس",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["temporary_password"]
    employee = User.objects.get(mobile="+966522222222")
    assert employee.is_superuser is False
    assert employee.is_staff is False
    assert employee.must_change_password is True
    assert response.data["member"]["role"] == PlatformStaffRole.SUPPORT
    assert PlatformCapability.TEAM_MANAGE not in response.data["member"]["capabilities"]


def test_employee_capabilities_are_enforced_on_existing_platform_endpoints():
    owner = make_owner()
    support = User.objects.create_user(mobile="+966533333333", password="StrongPass!42")
    PlatformStaffMembership.objects.create(
        user=support, role=PlatformStaffRole.SUPPORT, created_by=owner
    )
    client = auth_client(support)

    assert client.get("/api/v1/platform/overview/").status_code == 200
    assert client.get("/api/v1/platform/schools/").status_code == 200
    assert client.get("/api/v1/platform/plans/").status_code == 403
    assert client.post("/api/v1/platform/team/", {}, format="json").status_code == 403


def test_suspended_employee_loses_platform_access_immediately():
    owner = make_owner()
    employee = User.objects.create_user(mobile="+966544444444", password="StrongPass!42")
    membership = PlatformStaffMembership.objects.create(
        user=employee, role=PlatformStaffRole.OPERATIONS_MANAGER, created_by=owner
    )
    client = auth_client(owner)

    response = client.post(f"/api/v1/platform/team/{employee.id}/suspend/", {}, format="json")
    assert response.status_code == 200
    membership.refresh_from_db()
    assert membership.status == PlatformStaffStatus.SUSPENDED
    assert auth_client(employee).get("/api/v1/platform/overview/").status_code == 403


def test_owner_is_visible_but_protected_from_team_mutations():
    owner = make_owner()
    client = auth_client(owner)

    listing = client.get("/api/v1/platform/team/")
    assert listing.status_code == 200
    assert listing.data["members"][0]["is_owner"] is True
    response = client.post(f"/api/v1/platform/team/{owner.id}/suspend/", {}, format="json")
    assert response.status_code == 409
    assert response.data["code"] == "PLATFORM_OWNER_PROTECTED"


def test_platform_account_is_exposed_in_me_and_can_be_updated():
    owner = make_owner()
    payload = build_me_payload(owner, [], None)
    assert payload["platform_role"] == "OWNER"
    assert payload["is_platform_owner"] is True
    assert PlatformCapability.TEAM_MANAGE in payload["platform_capabilities"]

    response = auth_client(owner).patch(
        "/api/v1/platform/account/",
        {"name": "فهد الفهد", "mobile": "0511111111"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["name"] == "فهد الفهد"

    rejected = auth_client(owner).patch(
        "/api/v1/platform/account/",
        {"name": "فهد الفهد", "mobile": "0577777777"},
        format="json",
    )
    assert rejected.status_code == 400
    assert rejected.data["code"] == "INVALID_CURRENT_PASSWORD"


def test_school_account_cannot_be_promoted_to_platform_employee(make_school, make_user):
    from memberships.models import SchoolMembership

    owner = make_owner()
    school = make_school()
    school_user = make_user(mobile="+966555555555")
    SchoolMembership.objects.create(user=school_user, school=school)

    response = auth_client(owner).post(
        "/api/v1/platform/team/",
        {"name": "موظف مدرسة", "mobile": school_user.mobile, "role": PlatformStaffRole.SUPPORT},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["code"] == "SCHOOL_ACCOUNT_NOT_ALLOWED"


def test_platform_employee_cannot_be_assigned_as_school_manager(make_school):
    owner = make_owner()
    school = make_school()
    employee = User.objects.create_user(mobile="+966566666666", password="StrongPass!42")
    PlatformStaffMembership.objects.create(
        user=employee,
        role=PlatformStaffRole.SUPPORT,
        status=PlatformStaffStatus.SUSPENDED,
        created_by=owner,
    )

    response = auth_client(owner).post(
        f"/api/v1/platform/schools/{school.id}/managers/",
        {"name": "موظف منصة", "mobile": employee.mobile},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["code"] == "PLATFORM_ACCOUNT_NOT_ALLOWED"
