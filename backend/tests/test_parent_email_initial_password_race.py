"""An authenticated temporary-password snapshot cannot overwrite email recovery."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import connection, connections
from django.test import Client

from accounts.api import views as auth_views
from parents import email_recovery_services as service
from parents.email_recovery_models import AccountRecoveryEmailDelivery
from parents.email_recovery_provider import EmailDeliveryResult
from parents.email_recovery_tasks import send_parent_recovery_email
from parents.models import GuardianStudentRelation
from tests import test_parent_email_recovery as recovery_tests
from tests.test_parent_email_credential_boundary import restricted_role

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = recovery_tests.PASSWORD
email_env = recovery_tests.email_env
OWNER_PASSWORD = "Owner-Initial-Setup-2026!"
RECOVERED_PASSWORD = "Owner-Email-Recovered-2026!"
STALE_PASSWORD = "School-Known-Stale-Request-2026!"
INITIAL = "/api/v1/auth/change-initial-password/"
EMAIL = "/api/v1/parent/recovery-email/"
RESET = "/api/v1/auth/parent-password-recovery/"


def post(client, path, data):
    return client.post(path, data, content_type="application/json")


def test_stale_initial_password_request_cannot_overwrite_completed_verified_email_recovery(
    email_env,
):
    env = email_env
    env["user"].must_change_password = True
    env["user"].save(update_fields=["must_change_password"])
    owner = Client()
    owner.force_login(env["user"])
    stale = Client()
    stale.force_login(env["user"])
    paused = Event()
    resume = Event()
    original_validation = auth_views._validate_new_password
    relations_before = list(GuardianStudentRelation.objects.filter(user=env["user"]).values())

    def pause_validation(user, password):
        if password == STALE_PASSWORD:
            paused.set()
            assert resume.wait(timeout=15)
        return original_validation(user, password)

    with restricted_role():
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            role_name = connection.ops.quote_name(cursor.fetchone()[0])

        def attempt_stale_change():
            connections.close_all()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"SET ROLE {role_name}")
                response = post(
                    stale,
                    INITIAL,
                    {
                        "current_password": PASSWORD,
                        "new_password": STALE_PASSWORD,
                        "confirm_password": STALE_PASSWORD,
                    },
                )
                return response.status_code, stale.get("/api/v1/auth/me/").status_code
            finally:
                connections.close_all()

        with patch.object(auth_views, "_validate_new_password", side_effect=pause_validation):
            with ThreadPoolExecutor(max_workers=1) as executor:
                stale_future = executor.submit(attempt_stale_change)
                try:
                    assert paused.wait(timeout=10)
                    setup = post(
                        owner,
                        INITIAL,
                        {
                            "current_password": PASSWORD,
                            "new_password": OWNER_PASSWORD,
                            "confirm_password": OWNER_PASSWORD,
                        },
                    )
                    assert setup.status_code == 200, setup.content
                    enrollment = post(
                        owner,
                        EMAIL,
                        {
                            "email": "initial-owner@example.invalid",
                            "current_password": OWNER_PASSWORD,
                        },
                    )
                    assert enrollment.status_code == 200, enrollment.content
                    with service.email_scope(user_id=env["user"].pk):
                        verification = AccountRecoveryEmailDelivery.objects.get(
                            user=env["user"], purpose="RECOVERY_EMAIL_VERIFICATION"
                        )
                    with patch(
                        "parents.email_recovery_tasks.send_recovery_email",
                        return_value=EmailDeliveryResult(
                            "SUBMITTED_TO_PROVIDER", provider_reference=str(uuid4())
                        ),
                    ) as provider:
                        assert (
                            send_parent_recovery_email.run(str(verification.pk))
                            == "submitted_to_provider"
                        )
                    verification_token = provider.call_args.kwargs["token"]
                    assert (
                        post(owner, EMAIL + "verify/", {"token": verification_token}).status_code
                        == 200
                    )
                    assert post(Client(), RESET, {"mobile": env["user"].mobile}).status_code == 202
                    with service.email_scope(user_id=env["user"].pk):
                        recovery = AccountRecoveryEmailDelivery.objects.get(
                            user=env["user"], purpose="PASSWORD_RESET"
                        )
                    with patch(
                        "parents.email_recovery_tasks.send_recovery_email",
                        return_value=EmailDeliveryResult(
                            "SUBMITTED_TO_PROVIDER", provider_reference=str(uuid4())
                        ),
                    ) as provider:
                        assert (
                            send_parent_recovery_email.run(str(recovery.pk))
                            == "submitted_to_provider"
                        )
                    recovered = post(
                        Client(),
                        RESET + "complete/",
                        {
                            "token": provider.call_args.kwargs["token"],
                            "new_password": RECOVERED_PASSWORD,
                            "confirm_password": RECOVERED_PASSWORD,
                        },
                    )
                    assert recovered.status_code == 200, recovered.content
                finally:
                    resume.set()
                status, stale_session_status = stale_future.result(timeout=10)
        assert status in {403, 409}
        assert stale_session_status == 403
        assert owner.get("/api/v1/auth/me/").status_code == 403
    env["user"].refresh_from_db()
    assert env["user"].check_password(RECOVERED_PASSWORD)
    assert not env["user"].must_change_password
    assert (
        list(GuardianStudentRelation.objects.filter(user=env["user"]).values()) == relations_before
    )
