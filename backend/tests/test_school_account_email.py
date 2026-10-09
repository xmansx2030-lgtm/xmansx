"""School enrollment, privileged verified-email recovery and transactional mail."""

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.utils import timezone

from accounts.models import User
from common.tenant_rls import tenant_context
from memberships.models import MembershipStatus, SchoolRole
from parents import email_recovery_services as recovery
from parents.email_recovery_models import AccountRecoveryEmail, AccountRecoveryEmailDelivery
from platform_team.models import PlatformStaffMembership
from subscriptions import email_services as mail
from subscriptions.email_provider import DeliveryResult
from subscriptions.models import SubscriptionEmailDelivery, SubscriptionEventType
from subscriptions.services import subscriptions
from tests.test_parent_email_credential_boundary import restricted_role
from tests.test_self_registration import make_plan, payload

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "School-Original-Password-2026!"
NEW_PASSWORD = "School-Updated-Password-2026!"
EMAIL_PATH = "/api/v1/parent/recovery-email/"
RESET_PATH = "/api/v1/auth/parent-password-recovery/"


def post(client, path, data):
    return client.post(path, data, content_type="application/json")


@pytest.fixture
def school_email_env(make_user, make_membership, make_school, settings):
    settings.SCHOOL_ACCOUNT_EMAIL_RECOVERY_ENABLED = True
    settings.PARENT_RECOVERY_EMAIL_ENABLED = True
    settings.SUBSCRIPTION_EMAIL_ENABLED = True
    user = User.objects.create_user("0552900801", password=PASSWORD)
    school = make_school("مدرسة البريد")
    membership = make_membership(user, school, [SchoolRole.SCHOOL_MANAGER])
    client = Client()
    client.force_login(user)
    with patch("parents.email_recovery_services._dispatch"):
        yield user, school, membership, client


def verify(user, client):
    response = post(client, EMAIL_PATH, {"email": "owner@example.invalid",
                                        "current_password": PASSWORD})
    assert response.status_code == 200, response.content
    with recovery.email_scope(user_id=user.pk):
        delivery = AccountRecoveryEmailDelivery.objects.filter(user=user).latest("created_at")
    prepared = recovery.prepare_email_delivery(delivery.pk)
    assert prepared is not None
    recovery.finalize_email_delivery(delivery.pk, "SUBMITTED_TO_PROVIDER",
                                     provider_reference=str(uuid4()))
    result = post(client, EMAIL_PATH + "verify/", {"token": prepared["token"]})
    assert result.status_code == 200, result.content


@pytest.mark.parametrize("email", [None, "", "bad-address", "bad\n@example.invalid"])
def test_school_registration_rejects_missing_or_invalid_email(client, email):
    data = payload(make_plan())
    if email is None:
        data.pop("manager_email")
    else:
        data["manager_email"] = email
    result = post(client, "/api/v1/auth/register-school/", data)
    assert result.status_code == 400
    from schools.models import School

    assert not School.objects.exists()


def test_registration_nominates_but_does_not_verify_recovery_email(settings, client):
    settings.SCHOOL_ACCOUNT_EMAIL_RECOVERY_ENABLED = True
    settings.PARENT_RECOVERY_EMAIL_ENABLED = True
    with patch("parents.email_recovery_services._dispatch"):
        result = post(client, "/api/v1/auth/register-school/", payload(make_plan()))
    assert result.status_code == 201, result.content
    user = User.objects.get(pk=result.json()["id"])
    assert user.email == "manager@example.invalid"
    item = AccountRecoveryEmail.objects.get(user=user)
    assert item.verified_at is None and item.pending_email_hash
    assert not SubscriptionEmailDelivery.objects.exists()


@pytest.mark.parametrize("email", [None, "", "invalid", {"unexpected": "value"}])
def test_initial_password_change_is_atomic_when_email_invalid(
    make_user, make_membership, make_school, email,
):
    user = User.objects.create_user("0552900802", password=PASSWORD, must_change_password=True)
    make_membership(user, make_school(), [SchoolRole.TEACHER])
    client = Client()
    client.force_login(user)
    data = {"current_password": PASSWORD, "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD}
    if email is not None:
        data["email"] = email
    result = post(client, "/api/v1/auth/change-initial-password/", data)
    assert result.status_code == 400, result.content
    user.refresh_from_db()
    assert user.check_password(PASSWORD) and user.must_change_password and not user.email


def test_teacher_first_login_collects_email_and_keeps_session(
    make_user, make_membership, make_school, settings,
):
    settings.SCHOOL_ACCOUNT_EMAIL_RECOVERY_ENABLED = True
    user = User.objects.create_user("0552900803", password=PASSWORD, must_change_password=True)
    make_membership(user, make_school(), [SchoolRole.TEACHER])
    client = Client()
    client.force_login(user)
    assert client.get("/api/v1/auth/me/").json()["requires_initial_email"] is True
    result = post(client, "/api/v1/auth/change-initial-password/", {
        "current_password": PASSWORD, "new_password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD, "email": " teacher@EXAMPLE.invalid ",
    })
    assert result.status_code == 200, result.content
    user.refresh_from_db()
    assert user.email == "teacher@example.invalid" and user.check_password(NEW_PASSWORD)
    assert not user.must_change_password
    assert client.get("/api/v1/auth/me/").status_code == 200
    assert AccountRecoveryEmail.objects.get(user=user).verified_at is None


@pytest.mark.parametrize("role", SchoolRole.values)
def test_each_school_role_can_recover_with_verified_email_only(
    school_email_env, role,
):
    user, school, membership, client = school_email_env
    membership.roles.update(role=role)
    verify(user, client)
    with patch("parents.email_recovery_services._dispatch"):
        result = post(Client(), RESET_PATH, {"mobile": user.mobile})
    assert result.status_code == 202
    delivery = AccountRecoveryEmailDelivery.objects.filter(
        user=user, purpose="PASSWORD_RESET",
    ).latest("created_at")
    prepared = recovery.prepare_email_delivery(delivery.pk)
    assert prepared
    recovery.finalize_email_delivery(delivery.pk, "SUBMITTED_TO_PROVIDER",
                                     provider_reference=str(uuid4()))
    result = post(Client(), RESET_PATH + "complete/", {
        "token": prepared["token"], "new_password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD,
    })
    assert result.status_code == 200, result.content
    assert post(Client(), RESET_PATH + "complete/", {
        "token": prepared["token"], "new_password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD,
    }).status_code == 400
    user.refresh_from_db()
    membership.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    assert membership.status == MembershipStatus.ACTIVE and membership.school_id == school.pk
    assert client.get("/api/v1/auth/me/").status_code in (401, 403)


@pytest.mark.parametrize("platform_kind", ["superuser", "staff", "support"])
def test_platform_accounts_remain_excluded(school_email_env, platform_kind):
    user, _, _, client = school_email_env
    verify(user, client)
    if platform_kind == "support":
        PlatformStaffMembership.objects.create(user=user, role="SUPPORT")
    else:
        setattr(user, "is_superuser" if platform_kind == "superuser" else "is_staff", True)
        user.save()
    with patch("parents.email_recovery_services._dispatch"):
        assert post(Client(), RESET_PATH, {"mobile": user.mobile}).status_code == 202
    assert not AccountRecoveryEmailDelivery.objects.filter(
        user=user, purpose="PASSWORD_RESET",
    ).exists()


def contract(env):
    user, school, _, client = env
    subscription = subscriptions.start_trial(school=school, plan_id=make_plan().pk, actor=user)
    verify(user, client)
    return subscription


def test_verified_manager_gets_one_details_message_and_no_credentials(school_email_env):
    subscription = contract(school_email_env)
    user = school_email_env[0]
    mail.queue_initial_manager_details(user)
    mail.queue_initial_manager_details(user)
    rows = SubscriptionEmailDelivery.objects.all()
    assert rows.count() == 1
    row = rows.get()
    assert row.kind == "DETAILS" and row.recipient_id == user.pk
    assert "email" not in row.snapshot and PASSWORD not in str(row.snapshot)
    assert row.snapshot["school_name"] == subscription.school.name


@pytest.mark.parametrize("days,kind", [(7, "REMINDER_7"), (3, "REMINDER_7"), (1, "REMINDER_1")])
def test_reminders_deduplicate_and_respect_current_contract(school_email_env, days, kind):
    subscription = contract(school_email_env)
    subscription.ends_at = timezone.now() + timedelta(days=days)
    subscription.trial_ends_at = subscription.ends_at
    subscription.save()
    mail.queue_reminders()
    mail.queue_reminders()
    assert SubscriptionEmailDelivery.objects.filter(kind=kind).count() == 1


@pytest.mark.parametrize("change", ["suspended", "demoted", "mail_changed", "contract_changed"])
def test_queued_mail_rechecks_recipient_and_contract(school_email_env, change):
    subscription = contract(school_email_env)
    _, _, membership, _ = school_email_env
    row = SubscriptionEmailDelivery.objects.get()
    if change == "suspended":
        membership.status = MembershipStatus.SUSPENDED
        membership.save()
    elif change == "demoted":
        membership.roles.update(role=SchoolRole.TEACHER)
    elif change == "mail_changed":
        from tests.parent_email_helpers import provision_verified_recovery_email

        provision_verified_recovery_email(school_email_env[0], "new@example.invalid")
    else:
        subscription.ends_at += timedelta(days=1)
        subscription.save()
    with patch("subscriptions.email_provider.send_subscription_email") as sender:
        assert mail.send_delivery(row.pk) == "cancelled"
        sender.assert_not_called()


@pytest.mark.parametrize("status", ["SUBMITTED_TO_PROVIDER", "FAILED", "UNKNOWN"])
def test_provider_outcomes_and_repeated_tasks_never_duplicate(school_email_env, status):
    contract(school_email_env)
    row = SubscriptionEmailDelivery.objects.get()
    with patch("subscriptions.email_provider.send_subscription_email",
               return_value=DeliveryResult(status)) as sender:
        assert mail.send_delivery(row.pk) == status
        assert mail.send_delivery(row.pk) == "ignored"
        assert sender.call_count == 1
        assert sender.call_args.kwargs["recipient"] == "owner@example.invalid"


def test_lifecycle_event_queues_after_commit_and_rolls_back_with_contract(school_email_env):
    subscription = contract(school_email_env)
    before = SubscriptionEmailDelivery.objects.count()
    with pytest.raises(RuntimeError), transaction.atomic():
        subscriptions.log_event(subscription=subscription,
                                event_type=SubscriptionEventType.EXTENDED)
        raise RuntimeError("rollback")
    assert SubscriptionEmailDelivery.objects.count() == before


def test_outbox_has_force_rls_and_rejects_other_school_reference(school_email_env, make_school):
    subscription = contract(school_email_env)
    row = SubscriptionEmailDelivery.objects.get()
    foreign = make_school("مدرسة أخرى")
    with restricted_role():
        with tenant_context(school_id=foreign.pk):
            assert not SubscriptionEmailDelivery.objects.filter(pk=row.pk).exists()
        with tenant_context(school_id=subscription.school_id):
            assert SubscriptionEmailDelivery.objects.filter(pk=row.pk).exists()
        with tenant_context(bypass=True), pytest.raises(DatabaseError), transaction.atomic():
            SubscriptionEmailDelivery.objects.filter(pk=row.pk).update(school=foreign)
    with connection.cursor() as cursor:
        cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                       "WHERE oid='subscriptions_subscriptionemaildelivery'::regclass")
        assert cursor.fetchone() == (True, True)


def test_manager_enrollment_and_mail_work_under_real_restricted_role(school_email_env):
    user, school, _, client = school_email_env
    subscription = subscriptions.start_trial(school=school, plan_id=make_plan().pk, actor=user)
    with restricted_role():
        verify(user, client)
        with tenant_context(school_id=school.pk, user_id=user.pk):
            row = SubscriptionEmailDelivery.objects.get(subscription=subscription)
            with patch("subscriptions.email_provider.send_subscription_email",
                       return_value=DeliveryResult("SUBMITTED_TO_PROVIDER")):
                assert mail.send_delivery(row.pk) == "SUBMITTED_TO_PROVIDER"
        assert post(Client(), RESET_PATH, {"mobile": user.mobile}).status_code == 202
        with recovery.email_scope(user_id=user.pk):
            assert AccountRecoveryEmailDelivery.objects.filter(
                user=user, purpose="PASSWORD_RESET",
            ).count() == 1


def test_password_recovery_preserves_suspended_membership(school_email_env):
    user, _, membership, client = school_email_env
    verify(user, client)
    membership.status = MembershipStatus.SUSPENDED
    membership.save()
    post(Client(), RESET_PATH, {"mobile": user.mobile})
    delivery = AccountRecoveryEmailDelivery.objects.filter(
        user=user, purpose="PASSWORD_RESET",
    ).latest("created_at")
    prepared = recovery.prepare_email_delivery(delivery.pk)
    recovery.finalize_email_delivery(delivery.pk, "SUBMITTED_TO_PROVIDER",
                                     provider_reference=str(uuid4()))
    result = post(Client(), RESET_PATH + "complete/", {
        "token": prepared["token"], "new_password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD,
    })
    assert result.status_code == 200
    membership.refresh_from_db()
    assert membership.status == MembershipStatus.SUSPENDED


def test_changed_platform_privilege_invalidates_issued_school_reset(school_email_env):
    user, _, _, client = school_email_env
    verify(user, client)
    post(Client(), RESET_PATH, {"mobile": user.mobile})
    delivery = AccountRecoveryEmailDelivery.objects.filter(
        user=user, purpose="PASSWORD_RESET",
    ).latest("created_at")
    prepared = recovery.prepare_email_delivery(delivery.pk)
    recovery.finalize_email_delivery(delivery.pk, "SUBMITTED_TO_PROVIDER",
                                     provider_reference=str(uuid4()))
    PlatformStaffMembership.objects.create(user=user, role="SUPPORT")
    result = post(Client(), RESET_PATH + "complete/", {
        "token": prepared["token"], "new_password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD,
    })
    assert result.status_code == 400
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


def test_scheduler_recovers_pending_and_marks_stale_sending_unknown(school_email_env):
    from subscriptions.tasks import process_manager_emails

    contract(school_email_env)
    row = SubscriptionEmailDelivery.objects.get()
    with patch("subscriptions.tasks.send_manager_email.delay") as dispatch:
        assert process_manager_emails.run() == 1
        dispatch.assert_called_once_with(str(row.pk))
    SubscriptionEmailDelivery.objects.filter(pk=row.pk).update(
        status="SENDING", updated_at=timezone.now() - timedelta(minutes=11),
    )
    with patch("subscriptions.tasks.send_manager_email.delay") as dispatch:
        assert process_manager_emails.run() == 0
        dispatch.assert_not_called()
    row.refresh_from_db()
    assert row.status == "UNKNOWN" and row.error_code == "STALE_SENDING"


def test_lifecycle_grace_and_expiry_notify_once(school_email_env):
    subscription = contract(school_email_env)
    now = timezone.now()
    subscription.starts_at = now - timedelta(days=30)
    subscription.ends_at = now - timedelta(days=1)
    subscription.trial_ends_at = subscription.ends_at
    subscription.grace_ends_at = now + timedelta(days=1)
    subscription.save()
    subscriptions.sync_expirations(now=now)
    subscriptions.sync_expirations(now=now)
    assert SubscriptionEmailDelivery.objects.filter(kind="GRACE_STARTED").count() == 1
    subscriptions.sync_expirations(now=now + timedelta(days=2))
    subscriptions.sync_expirations(now=now + timedelta(days=2))
    assert SubscriptionEmailDelivery.objects.filter(kind="EXPIRED").count() == 1


def test_concurrent_workers_claim_one_delivery(school_email_env):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connections

    from subscriptions.tasks import send_manager_email

    contract(school_email_env)
    row = SubscriptionEmailDelivery.objects.get()
    started, release = Event(), Event()

    def provider(**kwargs):
        started.set()
        assert release.wait(10)
        return DeliveryResult("SUBMITTED_TO_PROVIDER")

    def run():
        try:
            return send_manager_email.run(str(row.pk))
        finally:
            connections.close_all()

    with patch(
        "subscriptions.email_provider.send_subscription_email", side_effect=provider,
    ) as send:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(run)
            try:
                assert started.wait(10)
                second = pool.submit(run)
                assert second.result(timeout=10) == "ignored"
            finally:
                release.set()
            assert first.result(timeout=10) == "SUBMITTED_TO_PROVIDER"
        assert send.call_count == 1


def test_operator_can_retry_known_failures_but_never_unknown(school_email_env):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    contract(school_email_env)
    row = SubscriptionEmailDelivery.objects.get()
    SubscriptionEmailDelivery.objects.filter(pk=row.pk).update(status="UNKNOWN")
    with pytest.raises(CommandError):
        call_command("subscription_email_status", retry_failed=row.pk)
    SubscriptionEmailDelivery.objects.filter(pk=row.pk).update(status="FAILED")
    call_command("subscription_email_status", retry_failed=row.pk)
    row.refresh_from_db()
    assert row.status == "PENDING"
