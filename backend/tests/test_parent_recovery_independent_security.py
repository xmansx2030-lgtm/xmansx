"""Independent regressions for recovery and global guardian credential boundaries."""

from contextlib import contextmanager
from uuid import uuid4

import pytest
from django.db import connection
from django.test import Client, override_settings
from django.utils import timezone

from common.security.identifiers import (
    encrypt_national_id,
    mask_national_id,
    national_id_lookup_hash,
)
from common.tenant_rls import clear_tenant_context, tenant_context
from memberships.models import SchoolMembership
from parents.models import GuardianStudentRelation
from platform_team.models import PlatformStaffMembership, PlatformStaffRole
from students.models import Student

pytestmark = pytest.mark.django_db
NEW_PASSWORD = "Independent-Recovery-Password-2026!"


def _central_actor(make_user, role):
    actor = make_user("0550089202", is_superuser=role == "OWNER")
    if role != "OWNER":
        PlatformStaffMembership.objects.create(user=actor, role=role, status="ACTIVE")
    client = Client()
    client.force_login(actor)
    return actor, client


def _relation(school, guardian, approver, status="ACTIVE"):
    identifier = "1066900234"
    student = Student.objects.create(
        school=school,
        full_name="طالب حساب الاستعادة",
        national_id_encrypted=encrypt_national_id(identifier),
        national_id_lookup_hash=national_id_lookup_hash(identifier),
        national_id_masked=mask_national_id(identifier),
        guardian_name="ولي صاحب الحساب",
        guardian_mobile=guardian.mobile,
    )
    return GuardianStudentRelation.objects.create(
        school=school,
        student=student,
        user=guardian,
        status=status,
        approved_by=approver,
        approved_at=timezone.now(),
        contact_revision=student.guardian_contact_revision,
    )


def _add_existing_guardian_to_team(client, guardian):
    response = client.post(
        "/api/v1/platform/team/",
        {"name": "حساب ولي موظف منصة", "mobile": guardian.mobile, "role": "SUPPORT"},
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    assert response.json()["temporary_password"] is None
    assert response.json()["member"]["user_id"] == guardian.pk


@pytest.mark.parametrize("status", ["ACTIVE", "SUSPENDED_CONTACT_REVIEW", "REVOKED"])
@pytest.mark.parametrize("actor_role", [PlatformStaffRole.OPERATIONS_MANAGER, "OWNER"])
def test_platform_team_cannot_adopt_then_reset_existing_guardian_global_account(
    make_school, make_user, status, actor_role
):
    guardian = make_user("0550089201")
    actor, client = _central_actor(make_user, actor_role)
    relation = _relation(make_school(), guardian, actor, status)
    assert not SchoolMembership.objects.filter(user=guardian).exists()
    owner_client = Client()
    owner_client.force_login(guardian)
    original_hash = guardian.password
    original_auth_hash = owner_client.session["_auth_user_hash"]
    original_session = owner_client.session.session_key
    _add_existing_guardian_to_team(client, guardian)

    response = client.post(
        f"/api/v1/platform/team/{guardian.pk}/reset-password/",
        {},
        content_type="application/json",
    )

    assert response.status_code == 409, response.content
    assert response.json()["code"] == "GUARDIAN_ACCOUNT_PASSWORD_RESET_NOT_ALLOWED"
    assert "temporary_password" not in response.json()
    guardian.refresh_from_db()
    relation.refresh_from_db()
    assert guardian.password == original_hash and not guardian.must_change_password
    assert guardian.mobile == "+966550089201"
    assert relation.user_id == guardian.pk and relation.status == status
    assert not SchoolMembership.objects.filter(user=guardian).exists()
    assert owner_client.get("/api/v1/auth/me/").status_code == 200
    assert owner_client.session.session_key == original_session
    assert owner_client.session["_auth_user_hash"] == original_auth_hash


@pytest.mark.parametrize("actor_role", [PlatformStaffRole.OPERATIONS_MANAGER, "OWNER"])
def test_ordinary_platform_staff_password_reset_keeps_legacy_behavior(make_user, actor_role):
    employee = make_user("0550089201")
    _, client = _central_actor(make_user, actor_role)
    PlatformStaffMembership.objects.create(user=employee, role="SUPPORT", status="ACTIVE")

    response = client.post(
        f"/api/v1/platform/team/{employee.pk}/reset-password/",
        {},
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    temporary_password = response.json()["temporary_password"]
    assert temporary_password
    employee.refresh_from_db()
    assert employee.check_password(temporary_password)
    assert employee.must_change_password
    assert employee.mobile == "+966550089201"


def test_existing_employee_guardian_team_reset_preserves_employment_and_global_hash(
    make_school, make_user, make_membership
):
    guardian = make_user("0550089201")
    actor, client = _central_actor(make_user, "OWNER")
    employment = make_membership(guardian, make_school("مدرسة العمل"), ["TEACHER"])
    relation = _relation(make_school("مدرسة الابن"), guardian, actor)
    PlatformStaffMembership.objects.create(user=guardian, role="SUPPORT", status="ACTIVE")
    original_hash = guardian.password

    response = client.post(
        f"/api/v1/platform/team/{guardian.pk}/reset-password/",
        {},
        content_type="application/json",
    )

    assert response.status_code == 409, response.content
    guardian.refresh_from_db()
    employment.refresh_from_db()
    relation.refresh_from_db()
    assert guardian.password == original_hash
    assert employment.user_id == guardian.pk and employment.status == "ACTIVE"
    assert relation.user_id == guardian.pk and relation.status == "ACTIVE"


def test_guardian_platform_owner_self_service_still_requires_current_password(
    make_school, make_user
):
    guardian = make_user("0550089201")
    approver = make_user("0550089202")
    relation = _relation(make_school(), guardian, approver)
    PlatformStaffMembership.objects.create(user=guardian, role="SUPPORT", status="ACTIVE")
    client = Client()
    client.force_login(guardian)
    original_hash = guardian.password
    path = "/api/v1/platform/account/change-password/"
    denied = client.post(
        path,
        {"current_password": "wrong", "new_password": NEW_PASSWORD,
         "confirm_password": NEW_PASSWORD},
        content_type="application/json",
    )
    assert denied.status_code == 400
    guardian.refresh_from_db()
    assert guardian.password == original_hash
    allowed = client.post(
        path,
        {"current_password": "Str0ng-Pass-2026", "new_password": NEW_PASSWORD,
         "confirm_password": NEW_PASSWORD},
        content_type="application/json",
    )
    assert allowed.status_code == 200, allowed.content
    guardian.refresh_from_db()
    relation.refresh_from_db()
    assert guardian.check_password(NEW_PASSWORD)
    assert guardian.mobile == "+966550089201"
    assert relation.user_id == guardian.pk and relation.status == "ACTIVE"
    assert client.get("/api/v1/auth/me/").status_code == 200


@contextmanager
def _restricted_role():
    role = connection.ops.quote_name(f"independent_recovery_rls_{uuid4().hex}")
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {role} NOSUPERUSER NOBYPASSRLS")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            cursor.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"
            )
            cursor.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
            cursor.execute(f"SET ROLE {role}")
            cursor.execute(
                "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
            assert cursor.fetchone() == (False, False)
        clear_tenant_context()
        with override_settings(DATABASE_RLS_ENFORCED=True):
            yield role
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP OWNED BY {role}")
            cursor.execute(f"DROP ROLE IF EXISTS {role}")
        clear_tenant_context()


@pytest.mark.django_db(transaction=True)
def test_team_guardian_reset_checks_global_subject_under_actual_nonbypass_rls(
    make_school, make_user
):
    guardian = make_user("0550089201")
    actor, client = _central_actor(make_user, PlatformStaffRole.OPERATIONS_MANAGER)
    relation = _relation(make_school("مدرسة العلاقة المخفية"), guardian, actor, "REVOKED")
    unrelated_school = make_school("مدرسة أخرى")
    original_hash = guardian.password

    with _restricted_role():
        with tenant_context(school_id=unrelated_school.pk, user_id=actor.pk):
            assert not GuardianStudentRelation.objects.filter(pk=relation.pk).exists()
        _add_existing_guardian_to_team(client, guardian)
        response = client.post(
            f"/api/v1/platform/team/{guardian.pk}/reset-password/",
            {},
            content_type="application/json",
        )
        assert response.status_code == 409, response.content
        assert response.json()["code"] == "GUARDIAN_ACCOUNT_PASSWORD_RESET_NOT_ALLOWED"
        guardian.refresh_from_db()
        assert guardian.password == original_hash and not guardian.must_change_password
        with tenant_context(user_id=guardian.pk):
            relation.refresh_from_db()
            assert relation.user_id == guardian.pk and relation.status == "REVOKED"
