"""Old school accounts complete their own email without a password or role reset."""

from unittest.mock import patch

import pytest
from django.test import Client

from accounts.models import User
from common.tenant_rls import tenant_context
from memberships.middleware import ACTIVE_SCHOOL_SESSION_KEY
from memberships.models import SchoolRole
from parents.email_recovery_models import AccountRecoveryEmail, AccountRecoveryEmailDelivery
from platform_team.models import PlatformStaffMembership
from tests.test_parent_email_credential_boundary import restricted_role
from tests.test_school_account_email import verify

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "School-Original-Password-2026!"
EMAIL_PATH = "/api/v1/parent/recovery-email/"


@pytest.fixture
def old_school_account(make_school, make_membership, settings):
    settings.SCHOOL_ACCOUNT_EMAIL_RECOVERY_ENABLED = True
    settings.PARENT_RECOVERY_EMAIL_ENABLED = True
    user = User.objects.create_user("0552900901", password=PASSWORD,
                                    email="legacy@example.invalid")
    school = make_school("مدرسة الحسابات القديمة")
    membership = make_membership(user, school, [SchoolRole.TEACHER])
    client = Client()
    client.force_login(user)
    with patch("parents.email_recovery_services._dispatch"):
        yield user, membership, client


def flags(client):
    result = client.get("/api/v1/auth/me/")
    assert result.status_code == 200, result.content
    return result.json()


@pytest.mark.parametrize("role", SchoolRole.values)
def test_old_account_is_prompted_on_next_login_without_mutating_account(old_school_account, role):
    user, membership, _ = old_school_account
    membership.roles.update(role=role)
    password_hash = user.password
    result = Client().post("/api/v1/auth/login/", {
        "mobile": user.mobile, "password": PASSWORD,
    }, content_type="application/json")
    assert result.status_code == 200, result.content
    data = result.json()
    assert data["school_email_completion_required"] is True
    assert data["school_email_verification_pending"] is False
    assert data["must_change_password"] is False
    assert "email" not in data and "legacy@example.invalid" not in result.content.decode()
    user.refresh_from_db()
    membership.refresh_from_db()
    assert user.password == password_hash and user.email == "legacy@example.invalid"
    assert membership.status == "ACTIVE" and membership.role_codes() == [role]
    assert not AccountRecoveryEmail.objects.filter(user=user).exists()


def test_email_entry_unlocks_work_pending_verification_without_changing_password(
    old_school_account,
):
    user, membership, client = old_school_account
    password_hash = user.password
    response = client.post(EMAIL_PATH, {
        "email": "personal@example.invalid", "current_password": PASSWORD,
    }, content_type="application/json")
    assert response.status_code == 200, response.content
    data = flags(client)
    assert data["school_email_completion_required"] is False
    assert data["school_email_verification_pending"] is True
    switched = client.post("/api/v1/session/active-school/", {
        "school_id": membership.school_id,
    }, content_type="application/json")
    assert switched.status_code == 200, switched.content
    assert switched.json()["school_email_verification_pending"] is True
    user.refresh_from_db()
    membership.refresh_from_db()
    assert user.password == password_hash and not user.must_change_password
    assert membership.status == "ACTIVE"
    item = AccountRecoveryEmail.objects.get(user=user)
    assert item.verified_at is None and item.pending_email_hash
    # A declared delivery failure still retains the nomination; no new email form.
    AccountRecoveryEmailDelivery.objects.filter(user=user).update(status="FAILED")
    assert flags(client)["school_email_verification_pending"] is True


def test_invalid_password_does_not_complete_the_step(old_school_account):
    user, _, client = old_school_account
    result = client.post(EMAIL_PATH, {
        "email": "personal@example.invalid", "current_password": "wrong-password",
    }, content_type="application/json")
    assert result.status_code == 403, result.content
    assert flags(client)["school_email_completion_required"] is True
    assert not AccountRecoveryEmail.objects.filter(user=user).exists()


def test_verified_old_account_stops_the_prompt_and_notice(old_school_account):
    user, _, client = old_school_account
    verify(user, client)
    data = flags(client)
    assert data["school_email_completion_required"] is False
    assert data["school_email_verification_pending"] is False
    # Changing a candidate does not invalidate the already verified credential.
    result = client.post(EMAIL_PATH, {
        "email": "updated@example.invalid", "current_password": PASSWORD,
    }, content_type="application/json")
    assert result.status_code == 200, result.content
    assert flags(client)["school_email_completion_required"] is False


@pytest.mark.parametrize("setting_name", ["PARENT_RECOVERY_EMAIL_ENABLED",
                                          "SCHOOL_ACCOUNT_EMAIL_RECOVERY_ENABLED"])
def test_disabled_service_does_not_block_old_accounts(old_school_account, settings, setting_name):
    _, _, client = old_school_account
    setattr(settings, setting_name, False)
    data = flags(client)
    assert data["school_email_completion_required"] is False
    assert data["school_email_verification_pending"] is False


@pytest.mark.parametrize("privilege", ["is_staff", "is_superuser", "platform_membership"])
def test_platform_privilege_is_excluded_from_school_onboarding(old_school_account, privilege):
    user, _, client = old_school_account
    if privilege == "platform_membership":
        PlatformStaffMembership.objects.create(user=user, role="SUPPORT")
    else:
        User.objects.filter(pk=user.pk).update(**{privilege: True})
    assert flags(client)["school_email_completion_required"] is False


def test_initial_password_requirement_has_priority(old_school_account):
    user, _, client = old_school_account
    User.objects.filter(pk=user.pk).update(email="", must_change_password=True)
    data = flags(client)
    assert data["must_change_password"] and data["requires_initial_email"]
    assert data["school_email_completion_required"] is False


def test_no_school_membership_does_not_prompt(old_school_account):
    _, membership, client = old_school_account
    membership.status = "LEFT"
    membership.save()
    assert flags(client)["school_email_completion_required"] is False


def test_real_rls_owner_status_cannot_be_satisfied_by_another_account(
    old_school_account, make_school, make_membership,
):
    user, _, client = old_school_account
    foreign = User.objects.create_user("0552900902", password=PASSWORD)
    make_membership(foreign, make_school("مدرسة أخرى"), [SchoolRole.TEACHER])
    other = Client()
    other.force_login(foreign)
    verify(foreign, other)
    with restricted_role(), tenant_context(user_id=user.pk):
        data = flags(client)
        assert data["school_email_completion_required"] is True
        assert data["school_email_verification_pending"] is False
        assert not AccountRecoveryEmail.objects.filter(user=foreign).exists()


@pytest.mark.parametrize("verified", [False, True])
def test_real_rls_active_school_keeps_owned_email_state(old_school_account, verified):
    user, membership, client = old_school_account
    if verified:
        verify(user, client)
    else:
        result = client.post(EMAIL_PATH, {
            "email": "personal@example.invalid", "current_password": PASSWORD,
        }, content_type="application/json")
        assert result.status_code == 200, result.content
    session = client.session
    session[ACTIVE_SCHOOL_SESSION_KEY] = membership.school_id
    session.save()

    with restricted_role():
        data = flags(client)
        assert data["active_school"]["id"] == membership.school_id
        assert data["school_email_completion_required"] is False
        assert data["school_email_verification_pending"] is (not verified)
        status = client.get(EMAIL_PATH)
        assert status.status_code == 200, status.content
        assert status.json()["verified"] is verified
        switched = client.post("/api/v1/session/active-school/", {
            "school_id": membership.school_id,
        }, content_type="application/json")
        assert switched.status_code == 200, switched.content
        assert switched.json()["school_email_completion_required"] is False
        assert switched.json()["school_email_verification_pending"] is (not verified)
