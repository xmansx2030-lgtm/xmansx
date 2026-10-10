"""Personal password changes preserve account scope and stale-session boundaries."""

from unittest.mock import patch

import pytest
from django.test import Client

from accounts.api import views
from accounts.models import User
from audit.models import AuditAction, AuditLog
from tests.conftest import PASSWORD

pytestmark = pytest.mark.django_db
PATH = "/api/v1/auth/change-password/"
NEW_PASSWORD = "My-New-Private-Password-2026!"


def post(client, **overrides):
    data = {
        "current_password": PASSWORD,
        "new_password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD,
        **overrides,
    }
    return client.post(PATH, data, content_type="application/json")


@pytest.mark.parametrize("role", ["SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR", "TEACHER",
                                 "GATE_GUARD"])
def test_own_password_keeps_current_session_and_identity_and_invalidates_other_sessions(
    role_client, role, make_user,
):
    client, school, user = role_client([role])
    other_user = make_user("0552223344")
    other_password = other_user.password
    other_session = Client()
    other_session.force_login(user)
    old_session_key = client.session.session_key
    before = client.get("/api/v1/auth/me/").json()

    # An injected target cannot select another account; the authenticated owner wins.
    response = post(client, user_id=other_user.id, school_id=school.id + 100)
    assert response.status_code == 200, response.content
    user.refresh_from_db()
    other_user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    assert not user.check_password(PASSWORD)
    assert other_user.password == other_password
    assert client.session.session_key != old_session_key
    after = client.get("/api/v1/auth/me/")
    assert after.status_code == 200
    assert after.json() == before
    assert other_session.get("/api/v1/auth/me/").status_code == 403
    event = AuditLog.objects.get(action=AuditAction.ACCOUNT_PASSWORD_CHANGED, actor=user)
    assert event.metadata == {}
    assert NEW_PASSWORD not in response.content.decode()


@pytest.mark.parametrize("overrides", [
    {"current_password": "Incorrect-Password!"},
    {"confirm_password": "Does-Not-Match!"},
    {"new_password": "short", "confirm_password": "short"},
    {"new_password": "123456789", "confirm_password": "123456789"},
    {"new_password": PASSWORD, "confirm_password": PASSWORD},
    {"new_password": "password", "confirm_password": "password"},
    {"new_password": "x" * 129, "confirm_password": "x" * 129},
])
def test_rejected_password_never_changes_hash_or_records_success(role_client, overrides):
    client, _, user = role_client(["TEACHER"])
    old_hash = user.password
    response = post(client, **overrides)
    assert response.status_code == 400, response.content
    user.refresh_from_db()
    assert user.password == old_hash
    assert not AuditLog.objects.filter(action=AuditAction.ACCOUNT_PASSWORD_CHANGED).exists()
    assert client.get("/api/v1/auth/me/").status_code == 200


def test_requires_auth_and_csrf(role_client):
    assert post(Client()).status_code == 403
    _, _, user = role_client(["TEACHER"])
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(user)
    assert post(csrf_client).status_code == 403
    csrf_client.get("/api/v1/auth/csrf/")
    token = csrf_client.cookies["csrftoken"].value
    response = csrf_client.post(PATH, {
        "current_password": PASSWORD, "new_password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD,
    }, content_type="application/json", HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 200, response.content


def test_does_not_bypass_initial_password_or_platform_account_flow(role_client):
    client, _, user = role_client(["TEACHER"])
    user.must_change_password = True
    user.save(update_fields=["must_change_password"])
    response = post(client)
    assert response.status_code == 403
    assert response.json()["code"] == "INITIAL_PASSWORD_CHANGE_REQUIRED"
    user.must_change_password = False
    user.save(update_fields=["must_change_password"])
    from platform_team.models import PlatformStaffMembership, PlatformStaffRole

    PlatformStaffMembership.objects.create(user=user, role=PlatformStaffRole.SUPPORT)
    assert post(client).status_code == 403
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


def test_shared_account_rate_limit_is_bounded(role_client):
    client, _, user = role_client(["TEACHER"])
    for _ in range(10):
        assert post(client, current_password="Incorrect-Password!").status_code == 400
    assert post(client).status_code == 429
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


def test_stale_authenticated_snapshot_cannot_overwrite_a_new_password(role_client):
    client, _, user = role_client(["TEACHER"])
    recovered_password = "Already-Recovered-Private-Password!"
    original_validation = views._validate_new_password
    changed = False

    def concurrent_change(account, password):
        nonlocal changed
        if not changed:
            changed = True
            recovered = User.objects.get(pk=account.pk)
            recovered.set_password(recovered_password)
            recovered.save(update_fields=["password"])
        original_validation(account, password)

    with patch.object(views, "_validate_new_password", side_effect=concurrent_change):
        response = post(client)
    assert response.status_code == 403, response.content
    assert response.json()["code"] == "SESSION_CREDENTIALS_CHANGED"
    user.refresh_from_db()
    assert user.check_password(recovered_password)
    assert not user.check_password(NEW_PASSWORD)
    assert not AuditLog.objects.filter(action=AuditAction.ACCOUNT_PASSWORD_CHANGED).exists()


def test_password_change_errors_never_expose_credentials_to_error_tracking():
    from operations.error_tracking import before_send

    secret = "Private-Password-Never-Log!"
    event = {
        "request": {"url": f"https://example.invalid{PATH}",
                    "data": {"current_password": secret}},
        "exception": {"values": [{"value": secret, "stacktrace": {
            "frames": [{"module": "accounts.api.views", "vars": {"current": secret}}],
        }}]},
        "extra": {"new_password": secret, "confirm_password": secret},
    }
    assert secret not in str(before_send(event, {}))
