"""Real PostgreSQL ownership, replay, atomicity and credential-preservation checks."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import DatabaseError, connection, connections, transaction
from django.test import Client, override_settings
from django.utils import timezone

from accounts.models import User
from audit.models import AuditLog
from common.errors import ApiError
from common.tenant_rls import clear_tenant_context, tenant_context
from memberships.models import SchoolMembershipRole
from parents import email_recovery_services as service
from parents.email_recovery_models import (
    AccountRecoveryEmail,
    AccountRecoveryEmailDelivery,
)
from parents.email_recovery_models import (
    RecoveryEmailDeliveryStatus as Status,
)
from parents.email_recovery_models import (
    RecoveryEmailPurpose as Purpose,
)
from parents.models import GuardianStudentRelation
from parents.security import decrypt_value, token_hash
from platform_team.models import PlatformStaffMembership
from tests.attendance_helpers import setup_attendance_env

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "Original-Parent-Password-2026!"
NEW_PASSWORD = "New-Parent-Password-2026!"
BASE = "/api/v1/parent/recovery-email/"
RESET = "/api/v1/auth/parent-password-recovery/"


def post(client, path, data):
    return client.post(path, data, content_type="application/json")


@pytest.fixture
def email_env(make_school, make_membership, settings):
    settings.PARENT_RECOVERY_EMAIL_ENABLED = True
    settings.PARENT_RECOVERY_VERIFY_TTL_SECONDS = 86400
    settings.PARENT_RECOVERY_RESET_TTL_SECONDS = 900
    user = User.objects.create_user(
        mobile="0551800201", password=PASSWORD, email="staff-address@example.invalid"
    )
    actor = User.objects.create_user(mobile="0551800202", password=PASSWORD)
    school = make_school("مدرسة البريد الصناعي")
    make_membership(actor, school, ["SCHOOL_MANAGER"])
    students = setup_attendance_env(school, students_count=2)["students"]
    relation = GuardianStudentRelation.objects.create(
        user=user,
        school=school,
        student=students[0],
        status="ACTIVE",
        contact_bound=False,
        approved_by=actor,
        approved_at=timezone.now(),
    )
    suspended = GuardianStudentRelation.objects.create(
        user=user,
        school=school,
        student=students[1],
        status="SUSPENDED_CONTACT_REVIEW",
        contact_bound=False,
        approved_by=actor,
        approved_at=timezone.now(),
    )
    client = Client()
    client.force_login(user)
    with patch("parents.email_recovery_services._dispatch"):
        yield {
            "user": user,
            "actor": actor,
            "school": school,
            "relation": relation,
            "suspended": suspended,
            "client": client,
            "make_membership": make_membership,
        }


def enroll(env, email="Owner+Recovery@Example.invalid"):
    response = post(env["client"], BASE, {"email": email, "current_password": PASSWORD})
    assert response.status_code == 200, response.content
    delivery = AccountRecoveryEmailDelivery.objects.filter(
        user=env["user"],
        purpose=Purpose.RECOVERY_EMAIL_VERIFICATION,
    ).latest("created_at")
    prepared = service.prepare_email_delivery(delivery.id)
    assert prepared is not None
    service.finalize_email_delivery(
        delivery.id, Status.SUBMITTED_TO_PROVIDER, provider_reference=str(uuid4())
    )
    return prepared["token"], delivery


def verify(env):
    token, _ = enroll(env)
    result = post(env["client"], BASE + "verify/", {"token": token})
    assert result.status_code == 200, result.content
    return token


def reset_token(env):
    verify(env)
    result = post(Client(), RESET, {"mobile": env["user"].mobile})
    assert result.status_code == 202, result.content
    delivery = AccountRecoveryEmailDelivery.objects.filter(
        user=env["user"],
        purpose=Purpose.PASSWORD_RESET,
    ).latest("created_at")
    prepared = service.prepare_email_delivery(delivery.id)
    assert prepared is not None
    service.finalize_email_delivery(delivery.id, Status.SUBMITTED_TO_PROVIDER)
    return prepared["token"], delivery


def test_email_enrollment_is_owner_proved_encrypted_and_never_user_email(email_env):
    env = email_env
    token, delivery = enroll(env)
    item = AccountRecoveryEmail.objects.get(user=env["user"])
    assert decrypt_value(item.pending_email_encrypted) == "owner+recovery@example.invalid"
    assert "owner+recovery" not in item.pending_email_encrypted
    assert item.current_email_hash is None and item.verified_at is None
    delivery.refresh_from_db()
    assert delivery.token_hash == token_hash(token) and token != delivery.token_hash
    assert env["user"].email == "staff-address@example.invalid"
    assert post(env["client"], BASE + "verify/", {"token": token}).json()["verified"] is True


@pytest.mark.parametrize("email", ["", "bad", "a\r\nb@example.invalid", "x" * 255 + "@x.invalid"])
def test_enrollment_rejects_invalid_email(email_env, email):
    result = post(email_env["client"], BASE, {"email": email, "current_password": PASSWORD})
    assert result.status_code == 400
    assert not AccountRecoveryEmail.objects.exists()


def test_enrollment_and_resend_require_owner_current_password_and_session(email_env):
    env = email_env
    assert (
        post(
            env["client"], BASE, {"email": "x@example.invalid", "current_password": "wrong"}
        ).status_code
        == 403
    )
    assert (
        post(
            Client(), BASE, {"email": "x@example.invalid", "current_password": PASSWORD}
        ).status_code
        == 403
    )
    assert AccountRecoveryEmail.objects.count() == 0


def test_email_gate_denies_child_data_before_verification_then_allows(email_env):
    env = email_env
    path = f"/api/v1/parent/children/{env['relation'].id}/"
    blocked = env["client"].get(path)
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "EMAIL_VERIFICATION_REQUIRED"
    assert str(env["relation"].student_id) not in blocked.json()["message"]
    verify(env)
    assert env["client"].get(path).status_code == 200


def test_verification_is_explicit_post_one_use_matching_owner(email_env):
    env = email_env
    token, delivery = enroll(env)
    assert env["client"].get(BASE + "verify/", {"token": token}).status_code == 405
    assert post(env["client"], BASE + "verify/check/", {"token": token}).status_code == 200
    delivery.refresh_from_db()
    assert delivery.consumed_at is None
    wrong = Client()
    wrong.force_login(env["actor"])
    assert post(wrong, BASE + "verify/", {"token": token}).status_code == 400
    assert post(env["client"], BASE + "verify/", {"token": token}).status_code == 200
    repeated = post(env["client"], BASE + "verify/", {"token": token})
    assert repeated.status_code == 400 and repeated.json()["code"] == "RECOVERY_TOKEN_USED"


def test_verification_expiry_and_changed_pending_address_invalidate(email_env):
    env = email_env
    token, delivery = enroll(env)
    AccountRecoveryEmailDelivery.objects.filter(id=delivery.id).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert post(env["client"], BASE + "verify/", {"token": token}).status_code == 400
    token2, _ = enroll(env, "another@example.invalid")
    assert post(env["client"], BASE + "verify/", {"token": token}).status_code == 400
    assert post(env["client"], BASE + "verify/", {"token": token2}).status_code == 200


def test_email_conflict_is_generic_and_preserves_primary_account(email_env):
    env = email_env
    token, _ = enroll(env)
    other = User.objects.create_user(mobile="0551800203", password=PASSWORD)
    AccountRecoveryEmail.objects.create(
        user=other,
        current_email_encrypted=service.encrypt_value("owner+recovery@example.invalid"),
        current_email_hash=service.recovery_email_hash("owner+recovery@example.invalid"),
        verified_at=timezone.now(),
    )
    result = post(env["client"], BASE + "verify/", {"token": token})
    assert result.status_code == 400 and result.json()["code"] == "RECOVERY_TOKEN_INVALID"
    assert AccountRecoveryEmail.objects.get(user=env["user"]).verified_at is None
    assert str(other.id).encode() not in result.content


def test_registration_email_never_swaps_existing_account_credentials(email_env):
    env = email_env
    service.enroll_registration_email(env["user"], "attacker@example.invalid", new_account=False)
    assert AccountRecoveryEmail.objects.count() == 0
    verify(env)
    original = AccountRecoveryEmail.objects.get(user=env["user"]).current_email_hash
    service.enroll_registration_email(env["user"], "attacker@example.invalid", new_account=True)
    assert AccountRecoveryEmail.objects.get(user=env["user"]).current_email_hash == original


def test_newly_activated_account_enrolls_pending_without_granting_children(email_env):
    env = email_env
    service.enroll_registration_email(env["user"], "new@example.invalid", new_account=True)
    item = AccountRecoveryEmail.objects.get(user=env["user"])
    assert item.pending_email_hash and item.verified_at is None
    assert env["client"].get("/api/v1/parent/children/").status_code == 403


def test_resend_cooldown_and_duplicate_worker_claim_are_bounded(email_env):
    env = email_env
    _, delivery = enroll(env)
    assert post(env["client"], BASE + "resend/", {}).status_code == 200
    assert AccountRecoveryEmailDelivery.objects.count() == 1
    assert service.prepare_email_delivery(delivery.id) is None


@pytest.mark.parametrize("status", [Status.FAILED, Status.UNKNOWN])
def test_provider_failures_never_auto_reissue_or_false_verify(email_env, status):
    env = email_env
    post(env["client"], BASE, {"email": "mail@example.invalid", "current_password": PASSWORD})
    delivery = AccountRecoveryEmailDelivery.objects.get()
    token = service.prepare_email_delivery(delivery.id)["token"]
    service.finalize_email_delivery(delivery.id, status, error_code="TEST_PROVIDER_FAILURE")
    assert service.prepare_email_delivery(delivery.id) is None
    item = AccountRecoveryEmail.objects.get()
    assert item.verified_at is None
    response = post(env["client"], BASE + "verify/", {"token": token})
    assert response.status_code == (400 if status == Status.FAILED else 200)


def test_stale_worker_claim_becomes_unknown_and_is_not_retried(email_env):
    _, delivery = enroll(email_env)
    AccountRecoveryEmailDelivery.objects.filter(id=delivery.id).update(
        status=Status.SENDING, attempt_started_at=timezone.now() - timedelta(minutes=11)
    )
    assert service.prepare_email_delivery(delivery.id) is None
    delivery.refresh_from_db()
    assert delivery.status == Status.UNKNOWN


def test_reset_response_identical_missing_unverified_and_verified_account(email_env):
    env = email_env
    missing = post(Client(), RESET, {"mobile": "0551800999"})
    unverified = post(Client(), RESET, {"mobile": env["user"].mobile})
    verify(env)
    verified = post(Client(), RESET, {"mobile": env["user"].mobile})
    assert missing.status_code == unverified.status_code == verified.status_code == 202
    assert missing.content == unverified.content == verified.content
    assert "email" not in verified.json()
    assert "no-store" in verified["Cache-Control"]
    assert "private" in verified["Cache-Control"]


def test_atomic_reset_revokes_all_real_sessions_preserves_relations_and_login_identifier(email_env):
    env = email_env
    second_session = Client()
    second_session.force_login(env["user"])
    token, _ = reset_token(env)
    before = list(GuardianStudentRelation.objects.filter(user=env["user"]).values("id", "status"))
    result = post(
        Client(),
        RESET + "complete/",
        {"token": token, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
    )
    assert result.status_code == 200, result.content
    env["user"].refresh_from_db()
    assert env["user"].check_password(NEW_PASSWORD)
    assert env["user"].mobile == "+966551800201"
    assert env["user"].email == "staff-address@example.invalid"
    assert (
        list(GuardianStudentRelation.objects.filter(user=env["user"]).values("id", "status"))
        == before
    )
    for old in (env["client"], second_session):
        assert old.get("/api/v1/auth/me/").status_code == 403
    assert (
        post(
            Client(), "/api/v1/auth/login/", {"mobile": env["user"].mobile, "password": PASSWORD}
        ).status_code
        == 401
    )
    new_client = Client()
    assert (
        post(
            new_client,
            "/api/v1/auth/login/",
            {"mobile": env["user"].mobile, "password": NEW_PASSWORD},
        ).status_code
        == 200
    )
    assert new_client.get(f"/api/v1/parent/children/{env['relation'].id}/").status_code == 200
    assert new_client.get(f"/api/v1/parent/children/{env['suspended'].id}/").status_code == 404
    assert (
        post(
            Client(),
            RESET + "complete/",
            {"token": token, "new_password": PASSWORD, "confirm_password": PASSWORD},
        ).status_code
        == 400
    )


@pytest.mark.parametrize("change", ["password", "email", "expired", "inactive"])
def test_reset_rechecks_current_account_binding(email_env, change):
    env = email_env
    token, delivery = reset_token(env)
    if change == "password":
        env["user"].set_password("Changed-Out-Of-Band-2026!")
        env["user"].save(update_fields=["password"])
    elif change == "email":
        item = AccountRecoveryEmail.objects.get()
        AccountRecoveryEmail.objects.filter(id=item.id).update(revision=item.revision + 1)
    elif change == "expired":
        AccountRecoveryEmailDelivery.objects.filter(id=delivery.id).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
    else:
        User.objects.filter(id=env["user"].id).update(is_active=False)
    result = post(
        Client(),
        RESET + "complete/",
        {"token": token, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
    )
    assert result.status_code == 400
    env["user"].refresh_from_db()
    assert not env["user"].check_password(NEW_PASSWORD)


@pytest.mark.parametrize("role", ["SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR", "GATE_GUARD"])
def test_sensitive_school_roles_fail_closed_but_ordinary_teachers_can_recover(email_env, role):
    env = email_env
    verify(env)
    env["make_membership"](env["user"], env["school"], [role])
    assert post(Client(), RESET, {"mobile": env["user"].mobile}).status_code == 202
    assert not AccountRecoveryEmailDelivery.objects.filter(purpose=Purpose.PASSWORD_RESET).exists()


def test_teacher_parent_recovery_preserves_job_membership(email_env):
    env = email_env
    membership = env["make_membership"](env["user"], env["school"], ["TEACHER"])
    token, _ = reset_token(env)
    assert (
        post(
            Client(),
            RESET + "complete/",
            {"token": token, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
        ).status_code
        == 200
    )
    membership.refresh_from_db()
    assert membership.status == "ACTIVE"
    assert list(membership.roles.values_list("role", flat=True)) == ["TEACHER"]


@pytest.mark.parametrize("kind", ["superuser", "staff", "platform", "initial_password"])
def test_privileged_account_reset_blocked_even_with_verified_email(email_env, kind):
    env = email_env
    verify(env)
    if kind == "platform":
        PlatformStaffMembership.objects.create(user=env["user"], role="AUDITOR")
    else:
        field = {
            "superuser": "is_superuser",
            "staff": "is_staff",
            "initial_password": "must_change_password",
        }[kind]
        User.objects.filter(id=env["user"].id).update(**{field: True})
    response = post(Client(), RESET, {"mobile": env["user"].mobile})
    assert response.status_code == 202
    assert not AccountRecoveryEmailDelivery.objects.filter(purpose=Purpose.PASSWORD_RESET).exists()


def test_new_sensitive_role_after_issuance_invalidates_reset(email_env):
    env = email_env
    token, _ = reset_token(env)
    env["make_membership"](env["user"], env["school"], ["VICE_PRINCIPAL"])
    assert post(Client(), RESET + "check/", {"token": token}).status_code == 400


def test_email_change_keeps_verified_primary_until_proof_and_invalidates_old_tokens(email_env):
    env = email_env
    token, _ = reset_token(env)
    item = AccountRecoveryEmail.objects.get()
    original = item.current_email_hash
    new_token, _ = enroll(env, "second@example.invalid")
    item.refresh_from_db()
    assert item.current_email_hash == original and item.verified_at is not None
    assert post(Client(), RESET + "check/", {"token": token}).status_code == 400
    assert post(env["client"], BASE + "verify/", {"token": new_token}).status_code == 200
    item.refresh_from_db()
    assert item.current_email_hash != original


def test_transaction_failure_rolls_back_password_and_token_consumption(email_env):
    env = email_env
    token, delivery = reset_token(env)
    with patch(
        "parents.email_recovery_services.record_event", side_effect=RuntimeError("audit down")
    ):
        with pytest.raises(RuntimeError, match="audit down"):
            service.complete_password_recovery(token, NEW_PASSWORD, NEW_PASSWORD)
    env["user"].refresh_from_db()
    delivery.refresh_from_db()
    assert env["user"].check_password(PASSWORD) and delivery.consumed_at is None
    assert post(Client(), RESET + "check/", {"token": token}).status_code == 200


def test_password_policy_and_confirmation_do_not_consume_token(email_env):
    token, delivery = reset_token(email_env)
    for password, confirm in (("123", "123"), (NEW_PASSWORD, "different")):
        response = post(
            Client(),
            RESET + "complete/",
            {"token": token, "new_password": password, "confirm_password": confirm},
        )
        assert response.status_code == 400
    delivery.refresh_from_db()
    assert delivery.consumed_at is None


def test_csrf_is_required_even_for_anonymous_password_reset(email_env):
    csrf = Client(enforce_csrf_checks=True)
    assert post(csrf, RESET, {"mobile": email_env["user"].mobile}).status_code == 403
    csrf.get("/api/v1/auth/csrf/")
    token = csrf.cookies["csrftoken"].value
    result = csrf.post(
        RESET,
        {"mobile": email_env["user"].mobile},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert result.status_code == 202


def test_password_request_rate_limit_applies_to_missing_numbers(email_env):
    anonymous = Client()
    responses = [post(anonymous, RESET, {"mobile": "0551800999"}) for _ in range(6)]
    assert [r.status_code for r in responses] == [202] * 5 + [429]


def test_audit_and_public_payloads_never_contain_token_email_or_password(email_env):
    env = email_env
    token, _ = reset_token(env)
    status = env["client"].get(BASE)
    assert b"owner+recovery@example.invalid" not in status.content
    assert token.encode() not in status.content
    metadata = str(list(AuditLog.objects.filter(action__startswith="PARENT_RECOVERY").values()))
    assert token not in metadata and "owner+recovery@example.invalid" not in metadata
    assert PASSWORD not in metadata


def test_concurrent_reset_consumes_once_under_independent_connections(email_env):
    token, _ = reset_token(email_env)

    def reset():
        connections.close_all()
        try:
            service.complete_password_recovery(token, NEW_PASSWORD, NEW_PASSWORD)
            return "OK"
        except ApiError as exc:
            return exc.code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: reset(), range(2)))
    assert sorted(results) == ["OK", "RECOVERY_TOKEN_USED"]


def test_concurrent_verification_consumes_once_under_independent_connections(email_env):
    env = email_env
    token, _ = enroll(env)

    def verify_once():
        connections.close_all()
        try:
            service.verify_recovery_email(env["user"], token)
            return "OK"
        except ApiError as exc:
            return exc.code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: verify_once(), range(2)))
    assert sorted(results) == ["OK", "RECOVERY_TOKEN_USED"]
    item = AccountRecoveryEmail.objects.get(user=env["user"])
    assert item.verified_at is not None and item.revision == 2


@pytest.mark.parametrize("operation", ["INSERT", "UPDATE"])
def test_privileged_role_assignment_serializes_after_reset_under_independent_connections(
    email_env,
    operation,
):
    env = email_env
    membership = env["make_membership"](env["user"], env["school"], ["TEACHER"])
    token, _ = reset_token(env)
    entered_password_validation = Event()
    permit_reset = Event()
    grant_started = Event()
    grant_connection = {}

    def hold_validation(*_args):
        entered_password_validation.set()
        assert permit_reset.wait(timeout=10)

    def reset():
        connections.close_all()
        try:
            service.complete_password_recovery(token, NEW_PASSWORD, NEW_PASSWORD)
            return "RESET"
        finally:
            connections.close_all()

    def grant():
        connections.close_all()
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    grant_connection["pid"] = cursor.fetchone()[0]
                grant_started.set()
                if operation == "INSERT":
                    SchoolMembershipRole.objects.create(
                        membership_id=membership.id, role="VICE_PRINCIPAL"
                    )
                else:
                    SchoolMembershipRole.objects.filter(membership_id=membership.id).update(
                        role="VICE_PRINCIPAL"
                    )
            return "GRANTED"
        finally:
            connections.close_all()

    with patch("parents.email_recovery_services.validate_password", side_effect=hold_validation):
        with ThreadPoolExecutor(max_workers=2) as executor:
            reset_future = executor.submit(reset)
            assert entered_password_validation.wait(timeout=10)
            grant_future = executor.submit(grant)
            assert grant_started.wait(timeout=10)
            # Observe the actual PostgreSQL wait, not a scheduler delay assumption.
            saw_lock_wait = False
            for _ in range(100):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE datname=current_database() AND wait_event_type='Lock' "
                        "AND pid=%s)",
                        [grant_connection["pid"]],
                    )
                    saw_lock_wait = cursor.fetchone()[0]
                if saw_lock_wait:
                    break
            try:
                assert saw_lock_wait
                assert not grant_future.done()
            finally:
                permit_reset.set()
            assert reset_future.result(timeout=10) == "RESET"
            assert grant_future.result(timeout=10) == "GRANTED"
    env["user"].refresh_from_db()
    assert env["user"].check_password(NEW_PASSWORD)
    # The old credential is consumed before privileges are assigned.
    assert post(Client(), RESET + "check/", {"token": token}).status_code == 400


@pytest.mark.parametrize("operation", ["INSERT", "UPDATE"])
def test_privileged_role_assignment_committed_first_denies_pending_reset(email_env, operation):
    env = email_env
    membership = env["make_membership"](env["user"], env["school"], ["TEACHER"])
    token, _ = reset_token(env)
    if operation == "INSERT":
        SchoolMembershipRole.objects.create(membership=membership, role="VICE_PRINCIPAL")
    else:
        SchoolMembershipRole.objects.filter(membership=membership).update(role="VICE_PRINCIPAL")
    result = post(
        Client(),
        RESET + "complete/",
        {"token": token, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
    )
    assert result.status_code == 400
    env["user"].refresh_from_db()
    assert env["user"].check_password(PASSWORD)


def test_password_recovery_preserves_three_school_relationships_without_account_recreation(
    email_env,
    make_school,
):
    env = email_env
    for index in range(2):
        school = make_school(f"مدرسة مستقلة {index}")
        students = setup_attendance_env(school, students_count=1)["students"]
        GuardianStudentRelation.objects.create(
            user=env["user"],
            school=school,
            student=students[0],
            status="ACTIVE",
            contact_bound=False,
            approved_by=env["actor"],
            approved_at=timezone.now(),
        )
    before = list(GuardianStudentRelation.objects.filter(user=env["user"]).order_by("id").values())
    account_id = env["user"].id
    user_count = User.objects.count()
    token, _ = reset_token(env)
    assert (
        post(
            Client(),
            RESET + "complete/",
            {"token": token, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
        ).status_code
        == 200
    )
    assert User.objects.count() == user_count
    assert User.objects.get(mobile=env["user"].mobile).id == account_id
    after = list(GuardianStudentRelation.objects.filter(user=env["user"]).order_by("id").values())
    assert after == before


def test_real_nobypass_role_school_and_platform_context_cannot_access_or_verify_foreign_email(
    email_env,
):
    env = email_env
    token, _ = enroll(env)
    item = AccountRecoveryEmail.objects.get()
    role = connection.ops.quote_name(f"parent_email_rls_{uuid4().hex}")
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
            with tenant_context(school_id=env["school"].id, user_id=env["actor"].id):
                assert AccountRecoveryEmail.objects.count() == 0
                assert AccountRecoveryEmailDelivery.objects.count() == 0
            with tenant_context(user_id=env["actor"].id, bypass=True):
                assert AccountRecoveryEmail.objects.count() == 0
                assert (
                    AccountRecoveryEmail.objects.filter(id=item.id).update(
                        verified_at=timezone.now()
                    )
                    == 0
                )
            with service.email_scope(user_id=env["user"].id, action="ENROLL"):
                with pytest.raises(DatabaseError), transaction.atomic():
                    AccountRecoveryEmail.objects.filter(id=item.id).update(
                        current_email_hash=item.pending_email_hash,
                        current_email_encrypted=item.pending_email_encrypted,
                        verified_at=timezone.now(),
                    )
            verified = post(env["client"], BASE + "verify/", {"token": token})
            assert verified.status_code == 200, verified.content
            assert (
                env["client"].get(f"/api/v1/parent/children/{env['relation'].id}/").status_code
                == 200
            )
            response = post(Client(), RESET, {"mobile": env["user"].mobile})
            assert response.status_code == 202
            with service.email_scope(user_id=env["user"].id):
                delivery = AccountRecoveryEmailDelivery.objects.filter(
                    purpose=Purpose.PASSWORD_RESET
                ).latest("created_at")
            prepared = service.prepare_email_delivery(delivery.id)
            assert prepared is not None
            service.finalize_email_delivery(delivery.id, Status.SUBMITTED_TO_PROVIDER)
            reset_result = post(
                Client(),
                RESET + "complete/",
                {
                    "token": prepared["token"],
                    "new_password": NEW_PASSWORD,
                    "confirm_password": NEW_PASSWORD,
                },
            )
            assert reset_result.status_code == 200, reset_result.content
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP OWNED BY {role}")
            cursor.execute(f"DROP ROLE IF EXISTS {role}")
        clear_tenant_context()
