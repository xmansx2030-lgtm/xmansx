"""School approval -> one email bearer -> atomic activation and verified recovery email."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import DatabaseError, connection, connections, transaction
from django.utils import timezone

from accounts.models import User
from common.tenant_rls import clear_tenant_context, tenant_context
from parents import services
from parents.activation_email import (
    locked_activation,
    prepare_activation_email,
    send_parent_activation_email,
)
from parents.email_recovery_models import AccountRecoveryEmail, AccountRecoveryEmailDelivery
from parents.email_recovery_provider import EmailDeliveryResult, _content, recovery_link
from parents.email_recovery_services import email_scope, recovery_email_hash
from parents.models import GuardianActivation, GuardianStudentRelation
from parents.security import decrypt_value, token_hash
from parents.serializers import RegistrationDecisionSerializer
from tests.parent_email_helpers import provision_verified_recovery_email
from tests.test_parent_email_credential_boundary import restricted_role
from tests.test_parent_portal import PASSWORD, approve, post, register
from tests.test_parent_portal import portal_env as _portal_env

pytestmark = pytest.mark.django_db(transaction=True)
ACTIVATE = "/api/v1/parent/activation/"
portal_env = _portal_env


@pytest.fixture
def activation_env(portal_env, settings):
    settings.PARENT_RECOVERY_EMAIL_ENABLED = True
    with patch("parents.activation_email.send_parent_activation_email.delay") as queued:
        item, _ = register(portal_env)
        decision = approve(portal_env, item, delivery="EMAIL")
        activation = GuardianActivation.objects.get(request=item)
        queued.assert_called_once_with(item.school_id, activation.id)
        assert decision["delivery_status"] == "PENDING"
        assert "activation_url" not in decision
        yield {**portal_env, "registration": item, "activation": activation}


def send(env, *, restricted=False, result="SUBMITTED_TO_PROVIDER"):
    captured = {}

    def provider(**kwargs):
        captured.update(kwargs)
        return EmailDeliveryResult(result, str(uuid4()), "" if result != "FAILED" else "REJECTED")

    with patch("parents.activation_email.send_activation_email", side_effect=provider) as mocked:
        if restricted:
            with restricted_role():
                send_parent_activation_email(env["school"].id, env["activation"].id)
        else:
            send_parent_activation_email(env["school"].id, env["activation"].id)
        mocked.assert_called_once()
    return captured["token"], captured


def complete(env, token, **extra):
    return post(
        env["parent"],
        ACTIVATE,
        {
            "token": token,
            "new_password": PASSWORD,
            "confirm_password": PASSWORD,
            **extra,
        },
    )


@pytest.mark.parametrize("restricted", [False, True])
def test_email_activation_verifies_once_and_grants_only_approved_child(activation_env, restricted):
    env = activation_env
    token, captured = send(env, restricted=restricted)
    assert captured["recipient"] == "registration@parent.invalid"
    assert captured["school_name"] == env["school"].name
    assert not GuardianStudentRelation.objects.filter(student=env["student"]).exists()
    assert post(env["parent"], ACTIVATE + "check/", {"token": token}).status_code == 200
    assert not User.objects.filter(mobile=env["student"].guardian_mobile).exists()
    if restricted:
        with restricted_role():
            response = complete(env, token)
    else:
        response = complete(env, token)
    assert response.status_code == 200, response.content
    owner = User.objects.get(pk=response.json()["id"])
    credential = AccountRecoveryEmail.objects.get(user=owner)
    assert credential.verified_at
    assert decrypt_value(credential.current_email_encrypted) == "registration@parent.invalid"
    assert credential.pending_email_hash == ""
    assert not AccountRecoveryEmailDelivery.objects.filter(user=owner).exists()
    assert env["parent"].get("/api/v1/parent/children/").status_code == 200
    assert complete(env, token).status_code == 409
    assert GuardianStudentRelation.objects.filter(user=owner).count() == 1
    with patch("parents.activation_email.send_activation_email") as provider:
        assert send_parent_activation_email(env["school"].id, env["activation"].id) == "skipped"
        provider.assert_not_called()


@pytest.mark.parametrize("change", ["expiry", "contact", "revoke"])
def test_stale_email_activation_does_not_create_account_or_credential(activation_env, change):
    env = activation_env
    token, _ = send(env)
    if change == "expiry":
        with patch(
            "parents.services.timezone.now",
            return_value=env["activation"].expires_at + timedelta(seconds=1),
        ):
            assert complete(env, token).status_code == 409
    elif change == "contact":
        env["student"].guardian_mobile = "+966551900099"
        env["student"].save(update_fields=["guardian_mobile"])
    else:
        GuardianActivation.objects.filter(pk=env["activation"].pk).update(revoked_at=timezone.now())
    if change != "expiry":
        assert complete(env, token).status_code == 409
    assert not User.objects.filter(
        mobile=decrypt_value(env["registration"].mobile_encrypted)
    ).exists()
    assert not GuardianStudentRelation.objects.filter(student=env["student"]).exists()
    assert AccountRecoveryEmail.objects.count() == 0


@pytest.mark.parametrize("status", ["FAILED", "UNKNOWN"])
def test_provider_failure_is_not_retried_and_failed_token_is_denied(activation_env, status):
    env = activation_env
    token, _ = send(env, result=status)
    env["activation"].refresh_from_db()
    assert env["activation"].delivery_status == status
    with patch("parents.activation_email.send_activation_email") as provider:
        assert send_parent_activation_email(env["school"].id, env["activation"].id) == "skipped"
        provider.assert_not_called()
    assert complete(env, token).status_code == (409 if status == "FAILED" else 200)


def test_crash_after_claim_never_reissues_or_resends(activation_env):
    env = activation_env
    claimed = prepare_activation_email(env["school"].id, env["activation"].id)
    assert claimed
    with patch("parents.activation_email.send_activation_email") as provider:
        assert send_parent_activation_email(env["school"].id, env["activation"].id) == "skipped"
        provider.assert_not_called()
    assert GuardianActivation.objects.get(pk=env["activation"].id).token_hash == token_hash(
        claimed["token"]
    )


def test_existing_teacher_must_login_and_reauthenticate_first_email(
    activation_env, make_membership
):
    env = activation_env
    owner = User.objects.create_user(mobile=env["student"].guardian_mobile, password=PASSWORD)
    membership = make_membership(owner, env["school"], ["TEACHER"])
    snapshot = owner.password
    token, _ = send(env, restricted=True)
    assert complete(env, token).status_code == 403
    env["parent"].force_login(owner)
    assert complete(env, token).status_code == 403
    assert not GuardianStudentRelation.objects.filter(user=owner).exists()
    with restricted_role():
        response = complete(env, token, current_password=PASSWORD)
    assert response.status_code == 200, response.content
    owner.refresh_from_db()
    assert owner.password == snapshot
    assert response.json()["id"] == owner.id
    assert AccountRecoveryEmail.objects.get(user=owner).verified_at
    assert membership.roles.get().role == "TEACHER"


def test_link_cannot_replace_existing_verified_email_or_other_school_relationships(
    activation_env, make_school
):
    env = activation_env
    owner = User.objects.create_user(mobile=env["student"].guardian_mobile, password=PASSWORD)
    email = provision_verified_recovery_email(owner, "original@parent.invalid")
    before = AccountRecoveryEmail.objects.values().get(pk=email.pk)
    other_school = make_school("مدرسة مستقلة")
    from tests.attendance_helpers import setup_attendance_env

    child = setup_attendance_env(other_school, students_count=1)["students"][0]
    suspended = GuardianStudentRelation.objects.create(
        user=owner,
        school=other_school,
        student=child,
        status="SUSPENDED_CONTACT_REVIEW",
        contact_bound=False,
    )
    token, _ = send(env)
    env["parent"].force_login(owner)
    with restricted_role():
        response = complete(env, token)
    assert response.status_code == 200, response.content
    assert AccountRecoveryEmail.objects.values().get(pk=email.pk) == before
    suspended.refresh_from_db()
    assert suspended.status == "SUSPENDED_CONTACT_REVIEW"


def test_email_conflict_rolls_back_account_relation_and_bearer(activation_env):
    env = activation_env
    foreign = User.objects.create_user(mobile="0551900090", password=PASSWORD)
    provision_verified_recovery_email(foreign, "registration@parent.invalid")
    token, _ = send(env)
    with restricted_role():
        result = complete(env, token)
    assert result.status_code == 400, result.content
    assert not User.objects.filter(mobile=env["student"].guardian_mobile).exists()
    assert not GuardianStudentRelation.objects.filter(student=env["student"]).exists()
    assert GuardianActivation.objects.get(pk=env["activation"].pk).used_at is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("delivery_channel", "MANUAL"),
        ("email_hash", "f" * 64),
        ("token_hash", "a" * 64),
    ],
)
def test_database_blocks_activation_binding_rewrite(activation_env, field, value):
    env = activation_env
    token, _ = send(env)
    with restricted_role(), tenant_context(school_id=env["school"].id):
        with pytest.raises(DatabaseError), transaction.atomic():
            GuardianActivation.objects.filter(pk=env["activation"].id).update(**{field: value})
    assert GuardianActivation.objects.get(pk=env["activation"].id).token_hash == token_hash(token)


def test_worker_rechecks_noor_contact_before_sending(activation_env):
    env = activation_env
    env["student"].guardian_mobile = "+966551900099"
    env["student"].save(update_fields=["guardian_mobile"])
    with patch("parents.activation_email.send_activation_email") as provider:
        assert send_parent_activation_email(env["school"].id, env["activation"].id) == "skipped"
        provider.assert_not_called()


def test_database_refuses_school_claim_of_email_ownership_without_exact_bearer(activation_env):
    owner = User.objects.create_user(mobile="0551900091", password=PASSWORD)
    email = AccountRecoveryEmail.objects.create(
        user=owner,
        pending_email_hash=recovery_email_hash("attacker@parent.invalid"),
        pending_email_encrypted="not-evidence",
    )
    with restricted_role(), email_scope(user_id=owner.id, action="ACTIVATE"):
        with (
            pytest.raises(DatabaseError, match="consumed exact account bearer"),
            transaction.atomic(),
        ):
            AccountRecoveryEmail.objects.filter(pk=email.pk).update(
                current_email_hash=email.pending_email_hash,
                current_email_encrypted=email.pending_email_encrypted,
                pending_email_hash="",
                pending_email_encrypted="",
                verified_at=timezone.now(),
                revision=2,
            )


def test_concurrent_activation_claims_only_once_and_preserves_single_user(activation_env):
    env = activation_env
    token, _ = send(env)
    barrier = Barrier(2)

    def worker(_):
        connections.close_all()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SET ROLE {quoted_role}")
            barrier.wait(timeout=10)
            try:
                user = services.complete_activation(
                    token=token,
                    new_password=PASSWORD,
                    confirm_password=PASSWORD,
                )
                return user.pk
            except Exception as error:
                from common.errors import ApiError

                assert isinstance(error, ApiError)
                assert error.code == "ACTIVATION_INVALID"
                return None
        finally:
            clear_tenant_context()
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
            connections.close_all()

    # Provision permissions once; concurrently GRANTing the same schema races
    # PostgreSQL's ACL catalog, independently of the application transaction.
    with restricted_role():
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            quoted_role = connection.ops.quote_name(cursor.fetchone()[0])
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(worker, range(2)))
    assert sum(value is not None for value in outcomes) == 1
    assert GuardianStudentRelation.objects.filter(student=env["student"]).count() == 1
    assert AccountRecoveryEmail.objects.filter(verified_at__isnull=False).count() == 1


def test_default_channel_email_and_purpose_branding_is_escaped():
    serializer = RegistrationDecisionSerializer(data={"decision": "REJECT"})
    assert serializer.is_valid()
    assert serializer.validated_data["delivery"] == "EMAIL"
    subject, text, html = _content(
        purpose="PARENT_ACCOUNT_ACTIVATION",
        link="https://localhost/parent/activate#token=safe",
        expires_at=timezone.now(),
        school_name="مدرسة <script>bad</script>",
    )
    assert "تفعيل" in subject and "مدرسة" in subject
    assert "توثيق" in text and "<script>" not in html
    assert "/parent/activate#token=" in recovery_link(
        purpose="PARENT_ACCOUNT_ACTIVATION",
        token="t" * 43,
    )


def test_resend_activation_sender_uses_school_name_without_changing_address(settings):
    import json
    from email.header import decode_header
    from email.utils import parseaddr

    from parents.email_recovery_provider import send_activation_email

    settings.PARENT_RECOVERY_EMAIL_ENABLED = True
    settings.PARENT_RECOVERY_EMAIL_ADAPTER = "resend"
    settings.RESEND_API_KEY = "test-key-not-a-real-secret"
    settings.RESEND_FROM_EMAIL = "منصة المواظبة <recovery@mail.mowadhabah.com>"
    with patch("parents.email_recovery_provider.build_opener") as factory:
        response = factory.return_value.open.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = json.dumps({"id": str(uuid4())}).encode()
        result = send_activation_email(
            delivery_id=str(uuid4()),
            recipient="synthetic@parent.invalid",
            token="a" * 43,
            expires_at=timezone.now(),
            school_name="مدرسة الاختبار",
        )
        assert result.status == "SUBMITTED_TO_PROVIDER"
        payload = json.loads(factory.return_value.open.call_args.args[0].data)
    display, address = parseaddr(payload["from"])
    display = decode_header(display)[0][0].decode("utf-8")
    assert display == "مدرسة الاختبار — منصة المواظبة"
    assert address == "recovery@mail.mowadhabah.com"
    assert "مدرسة الاختبار" in payload["subject"]


def test_rollback_refuses_email_activation_data_without_removing_guards(activation_env):
    import importlib

    migration = importlib.import_module("parents.migrations.0009_email_activation")
    with pytest.raises(DatabaseError, match="unsafe guard rollback blocked"):
        with transaction.atomic(), connection.schema_editor() as editor:
            migration.backward(None, editor)
    assert GuardianActivation.objects.filter(pk=activation_env["activation"].pk).exists()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname='parent_activation_email_guard'"
        )
        assert cursor.fetchone()[0] == 1


def test_reissue_defaults_to_email_and_invalidates_the_previous_bearer(activation_env):
    env = activation_env
    token, _ = send(env)
    result = post(
        env["staff"],
        f"/api/v1/staff/parents/registrations/{env['registration'].id}/activation/",
        {"verification_note": "تحقق حضوري مستقل حديث من صاحب الصفة"},
    )
    assert result.status_code == 200
    assert result.json() == {"delivery_status": "PENDING"}
    newest = GuardianActivation.objects.filter(request=env["registration"]).latest("id")
    assert newest.delivery_channel == "EMAIL"
    assert newest.email_hash == env["registration"].email_hash
    assert newest.delivery_key != env["activation"].delivery_key
    assert complete(env, token).status_code == 409
    new_token, _ = send({**env, "activation": newest})
    assert complete(env, new_token).status_code == 200


def test_two_children_delivery_locks_do_not_upgrade_the_shared_school_lock(activation_env):
    env = activation_env
    other = env["students"][1]
    other.guardian_mobile = "+966551900004"
    other.save(update_fields=["guardian_mobile"])
    second_env = {**env, "student": other}
    item, _ = register(second_env)
    approve(second_env, item, delivery="EMAIL")
    second = GuardianActivation.objects.get(request=item)
    barrier = Barrier(2)

    def worker(activation_id):
        connections.close_all()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SET ROLE {quoted_role}")
            with locked_activation(env["school"].id, activation_id) as locked:
                assert locked is not None
                # Both distinct child deliveries must hold their locks together.
                # A joined FOR UPDATE on School would serialize them here and
                # deadlock when both first acquire the school's KEY SHARE lock.
                barrier.wait(timeout=10)
                return locked[0].id
        finally:
            clear_tenant_context()
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
            connections.close_all()

    with restricted_role():
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            quoted_role = connection.ops.quote_name(cursor.fetchone()[0])
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(worker, [env["activation"].id, second.id]))
    assert set(outcomes) == {env["activation"].id, second.id}
