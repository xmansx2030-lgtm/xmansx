"""A removed child's school never turns its global owner into a school-reset account."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, connection, transaction
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from common.errors import ApiError
from common.tenant_rls import clear_tenant_context, tenant_context
from memberships.models import SchoolMembershipRole
from parents.email_recovery_models import AccountRecoveryEmail, AccountRecoveryEmailDelivery
from parents.email_recovery_provider import EmailDeliveryResult
from parents.email_recovery_services import recovery_email_hash, require_verified_recovery_email
from parents.email_recovery_tasks import send_parent_recovery_email
from parents.models import GuardianStudentRelation
from parents.security import encrypt_value
from platform_team.models import PlatformStaffMembership
from staff.models import StaffProfile
from tests.attendance_helpers import setup_attendance_env
from tests.test_parent_independent_account_security import admin_site

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "Retained-Global-Owner-2026!"
NEW_PASSWORD = "New-Independent-Owner-2026!"


@contextmanager
def restricted_role():
    role = connection.ops.quote_name(f"parent_email_boundary_{uuid4().hex}")
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {role} NOSUPERUSER NOBYPASSRLS")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            cursor.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"
            )
            cursor.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
            cursor.execute(f"SET ROLE {role}")
        clear_tenant_context()
        with override_settings(DATABASE_RLS_ENFORCED=True):
            yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP OWNED BY {role}")
            cursor.execute(f"DROP ROLE IF EXISTS {role}")
        clear_tenant_context()


@pytest.fixture
def retained_account(make_school, make_membership):
    family_school = make_school("مدرسة الأسرة المحذوفة")
    employer_school = make_school("مدرسة المعلم الباقية")
    owner = User.objects.create_user(
        mobile="0551800501", password=PASSWORD, is_superuser=True, is_staff=True
    )
    guardian = User.objects.create_user(mobile="0551800502", password=PASSWORD)
    manager = User.objects.create_user(mobile="0551800503", password=PASSWORD)
    membership = make_membership(guardian, employer_school, ["TEACHER"])
    profile = StaffProfile.objects.create(
        school=employer_school, membership=membership, display_name="معلم ولي أمر سابق"
    )
    make_membership(manager, employer_school, ["SCHOOL_MANAGER"])
    student = setup_attendance_env(family_school, students_count=1)["students"][0]
    GuardianStudentRelation.objects.create(
        user=guardian,
        school=family_school,
        student=student,
        status="ACTIVE",
        contact_bound=False,
        approved_by=owner,
        approved_at=timezone.now(),
    )
    AccountRecoveryEmail.objects.create(
        user=guardian,
        current_email_encrypted=encrypt_value("retained@example.invalid"),
        current_email_hash=recovery_email_hash("retained@example.invalid"),
        verified_at=timezone.now(),
    )
    platform = Client()
    platform.force_login(owner)
    staff = Client()
    staff.force_login(manager)
    staff_session = staff.session
    staff_session["active_school_id"] = employer_school.pk
    staff_session.save()
    with restricted_role():
        response = platform.delete(
            f"/api/v1/platform/schools/{family_school.pk}/",
            {"confirmation_name": family_school.name, "acknowledge_permanent_deletion": True},
            content_type="application/json",
        )
        assert response.status_code == 200, response.content
        with tenant_context(user_id=guardian.pk):
            assert not GuardianStudentRelation.objects.filter(user=guardian).exists()
            assert AccountRecoveryEmail.objects.filter(user=guardian).exists()
        yield {
            "user": guardian,
            "owner": owner,
            "manager": manager,
            "school": employer_school,
            "membership": membership,
            "profile": profile,
            "platform": platform,
            "staff": staff,
        }


def assert_original_account(env):
    env["user"].refresh_from_db()
    assert env["user"].check_password(PASSWORD)
    assert env["user"].mobile == "+966551800502"
    assert not env["user"].must_change_password


def test_school_cannot_reset_email_bound_teacher_after_last_child_school_is_purged(
    retained_account,
):
    env = retained_account
    response = env["staff"].post(f"/api/v1/staff/{env['profile'].pk}/reset-password/")
    assert response.status_code == 409, response.content
    assert response.json()["code"] == "GUARDIAN_ACCOUNT_PASSWORD_RESET_NOT_ALLOWED"
    assert_original_account(env)


@override_settings(ROOT_URLCONF="tests.test_parent_independent_account_security")
def test_admin_password_reset_and_mobile_save_block_retained_recovery_credentials(retained_account):
    env = retained_account
    response = env["platform"].post(
        reverse("independent_parent_admin:auth_user_password_change", args=[env["user"].pk]),
        {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD, "usable_password": "true"},
    )
    assert response.status_code == 403
    env["user"].mobile = "+966551800509"
    with pytest.raises(PermissionDenied):
        admin_site._registry[User].save_model(
            SimpleNamespace(user=env["owner"]), env["user"], None, True
        )
    assert "mobile" in admin_site._registry[User].get_readonly_fields(
        SimpleNamespace(user=env["owner"]), env["user"]
    )
    assert_original_account(env)


def test_platform_manager_reset_and_mobile_change_block_retained_recovery_credentials(
    retained_account,
):
    env = retained_account
    with tenant_context(user_id=env["owner"].pk, bypass=True):
        SchoolMembershipRole.objects.filter(membership=env["membership"]).update(
            role="SCHOOL_MANAGER"
        )
    path = f"/api/v1/platform/schools/{env['school'].pk}/managers/{env['membership'].pk}/"
    reset = env["platform"].post(
        path + "reset-password/",
        {"confirm_shared_account_impact": True},
        content_type="application/json",
    )
    assert (
        reset.status_code == 409
        and reset.json()["code"] == "GUARDIAN_ACCOUNT_PASSWORD_RESET_NOT_ALLOWED"
    )
    update = env["platform"].patch(
        path,
        {"mobile": "0551800509", "confirm_shared_account_impact": True},
        content_type="application/json",
    )
    assert update.status_code == 409 and update.json()["code"] == "GUARDIAN_MOBILE_REVIEW_REQUIRED"
    assert_original_account(env)


def test_platform_team_reset_mobile_and_self_mobile_block_retained_recovery_credentials(
    retained_account,
):
    env = retained_account
    with tenant_context(user_id=env["owner"].pk, bypass=True):
        env["membership"].delete()
        PlatformStaffMembership.objects.create(user=env["user"], role="SUPPORT")
    path = f"/api/v1/platform/team/{env['user'].pk}/"
    response = env["platform"].post(path + "reset-password/", {}, content_type="application/json")
    assert (
        response.status_code == 409
        and response.json()["code"] == "GUARDIAN_ACCOUNT_PASSWORD_RESET_NOT_ALLOWED"
    )
    update = env["platform"].patch(path, {"mobile": "0551800509"}, content_type="application/json")
    assert update.status_code == 409 and update.json()["code"] == "GUARDIAN_MOBILE_REVIEW_REQUIRED"
    personal = Client()
    personal.force_login(env["user"])
    result = personal.patch(
        "/api/v1/platform/account/",
        {"mobile": "0551800509", "current_password": PASSWORD},
        content_type="application/json",
    )
    assert result.status_code == 409 and result.json()["code"] == "GUARDIAN_MOBILE_REVIEW_REQUIRED"
    assert_original_account(env)


@pytest.mark.parametrize("method", ["update", "bulk_update"])
def test_database_guard_blocks_retained_account_mobile_changes_without_service_layer(
    retained_account,
    method,
):
    env = retained_account
    with tenant_context(school_id=env["school"].pk, user_id=env["manager"].pk):
        with pytest.raises(DatabaseError), transaction.atomic():
            if method == "update":
                User.objects.filter(pk=env["user"].pk).update(mobile="+966551800509")
            else:
                env["user"].mobile = "+966551800509"
                User.objects.bulk_update([env["user"]], ["mobile"])
    assert_original_account(env)


def test_never_parent_teacher_reset_and_mobile_update_remain_available(retained_account):
    env = retained_account
    ordinary = User.objects.create_user(mobile="0551800504", password=PASSWORD)
    with tenant_context(user_id=env["owner"].pk, bypass=True):
        from memberships.models import SchoolMembership

        membership = SchoolMembership.objects.create(user=ordinary, school=env["school"])
        SchoolMembershipRole.objects.create(membership=membership, role="TEACHER")
        profile = StaffProfile.objects.create(
            school=env["school"], membership=membership, display_name="معلم دون اعتماد عالمي للأسرة"
        )
    result = env["staff"].post(f"/api/v1/staff/{profile.pk}/reset-password/")
    assert result.status_code == 200
    ordinary.refresh_from_db()
    assert ordinary.must_change_password and ordinary.check_password(
        result.json()["temporary_password"]
    )
    with tenant_context(school_id=env["school"].pk, user_id=env["manager"].pk):
        assert User.objects.filter(pk=ordinary.pk).update(mobile="+966551800508") == 1


def test_owned_email_gate_is_fresh_and_restores_foreign_school_context(retained_account):
    env = retained_account
    with tenant_context(school_id=env["school"].pk, user_id=env["manager"].pk):
        require_verified_recovery_email(env["user"])
        with pytest.raises(ApiError) as foreign:
            require_verified_recovery_email(env["manager"])
        assert foreign.value.code == "EMAIL_VERIFICATION_REQUIRED"
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_user, current_setting('app.current_school_id',true), "
                "current_setting('app.current_user_id',true), "
                "current_setting('app.rls_bypass',true)"
            )
            role_name, school, actor, bypass = cursor.fetchone()
        assert (school, actor, bypass) == (str(env["school"].pk), str(env["manager"].pk), "off")
        # Only the database infrastructure owner withdraws this synthetic proof;
        # application school/platform roles cannot edit a verified email.
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
        try:
            AccountRecoveryEmail.objects.filter(user=env["user"]).update(
                verified_at=None, current_email_hash=None, current_email_encrypted=""
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute(f"SET ROLE {connection.ops.quote_name(role_name)}")
        with pytest.raises(ApiError) as revoked:
            require_verified_recovery_email(env["user"])
        assert revoked.value.code == "EMAIL_VERIFICATION_REQUIRED"


@override_settings(PARENT_RECOVERY_EMAIL_ENABLED=True)
def test_retained_teacher_parent_can_recover_self_after_school_purge_without_school_reset(
    retained_account,
):
    env = retained_account
    owner_session = Client()
    owner_session.force_login(env["user"])
    with tenant_context(user_id=env["owner"].pk, bypass=True):
        membership_before = type(env["membership"]).objects.values().get(pk=env["membership"].pk)
        employment_before = StaffProfile.objects.values().get(pk=env["profile"].pk)
    with tenant_context(user_id=env["user"].pk):
        email_before = AccountRecoveryEmail.objects.values().get(user=env["user"])
    with patch("parents.email_recovery_services._dispatch"):
        requested = Client().post(
            "/api/v1/auth/parent-password-recovery/",
            {"mobile": env["user"].mobile},
            content_type="application/json",
        )
    assert requested.status_code == 202
    with tenant_context(user_id=env["user"].pk):
        delivery = AccountRecoveryEmailDelivery.objects.get(
            user=env["user"], purpose="PASSWORD_RESET"
        )
    with patch(
        "parents.email_recovery_tasks.send_recovery_email",
        return_value=EmailDeliveryResult("SUBMITTED_TO_PROVIDER", provider_reference=str(uuid4())),
    ) as provider:
        assert send_parent_recovery_email.run(str(delivery.pk)) == "submitted_to_provider"
    token = provider.call_args.kwargs["token"]
    reset = Client().post(
        "/api/v1/auth/parent-password-recovery/complete/",
        {"token": token, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
        content_type="application/json",
    )
    assert reset.status_code == 200, reset.content
    assert owner_session.get("/api/v1/auth/me/").status_code == 403
    env["user"].refresh_from_db()
    assert env["user"].check_password(NEW_PASSWORD)
    assert env["user"].mobile == "+966551800502"
    with tenant_context(user_id=env["owner"].pk, bypass=True):
        assert (
            type(env["membership"]).objects.values().get(pk=env["membership"].pk)
            == membership_before
        )
        assert StaffProfile.objects.values().get(pk=env["profile"].pk) == employment_before
    with tenant_context(user_id=env["user"].pk):
        assert AccountRecoveryEmail.objects.values().get(user=env["user"]) == email_before
        assert not GuardianStudentRelation.objects.filter(user=env["user"]).exists()
    school_reset = env["staff"].post(f"/api/v1/staff/{env['profile'].pk}/reset-password/")
    assert school_reset.status_code == 409
    env["user"].refresh_from_db()
    assert env["user"].check_password(NEW_PASSWORD)
