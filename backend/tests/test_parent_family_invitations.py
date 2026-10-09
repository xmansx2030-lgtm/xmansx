"""One reviewed school family SMS, exact grants, live PostgreSQL/RLS and replay."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from django.db import DatabaseError, connection, connections, transaction
from django.test import Client
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from audit.models import AuditLog
from common.tenant_rls import clear_tenant_context, tenant_context
from memberships.models import SchoolMembership
from parents import family_invitation_services as service
from parents.contact_security import recipient_hash
from parents.email_recovery_models import AccountRecoveryEmail
from parents.models import (
    GuardianActivation,
    GuardianFamilyInvitation,
    GuardianStudentRelation,
    RecipientContactBlock,
)
from parents.security import decrypt_value, token_hash
from school_sms.models import SchoolSmsIntegration
from school_sms.providers import SmsProviderError, SmsProviderResult
from school_sms.security import encrypt_secret
from students.models import Student
from tests.attendance_helpers import make_students, setup_attendance_env
from tests.parent_email_helpers import provision_verified_recovery_email
from tests.test_parent_email_credential_boundary import restricted_role
from tests.test_parent_portal import PASSWORD, post
from tests.test_parent_portal import portal_env as _portal_env

pytestmark = pytest.mark.django_db(transaction=True)
portal_env = _portal_env
STAFF = "/api/v1/staff/parents/families/"
CHECK = "/api/v1/parent/family-invitation/check/"
ACTIVATE = "/api/v1/parent/family-invitation/activate/"


@pytest.fixture
def family_env(portal_env, settings):
    env = portal_env
    settings.PARENT_FAMILY_INVITATION_SMS_ENABLED = True
    settings.PARENT_RECOVERY_EMAIL_ENABLED = True
    extra = make_students(env["school"], env["section"], env["year"], 1, prefix="INVITE")
    students = env["students"] + extra
    for student, phone in zip(students, ["0551900003", "+966551900003", "٠٥٥١٩٠٠٠٠٣"], strict=True):
        student.guardian_mobile = phone
        student.guardian_name = "ولي أمر أسرة صناعية"
        student.save(update_fields=["guardian_mobile", "guardian_name"])
        student.refresh_from_db()
    SchoolSmsIntegration.objects.create(
        school=env["school"],
        provider="DREAMS",
        username="synthetic",
        secret_encrypted=encrypt_secret("fake-not-a-real-provider-key"),
        sender_name="Synthetic",
        is_active=True,
    )
    env["family"] = students
    env["membership"] = SchoolMembership.objects.get(user=env["actor"], school=env["school"])
    yield env


def data(env, **extra):
    return {
        "mobile": "+966551900003",
        "name": "ولي أمر أسرة صناعية",
        "relationship_type": "أب",
        "verification_note": "تم التحقق حضورياً من صفة ولي الأمر والأبناء والرقم",
        "children": [{"id": s.id, "revision": s.guardian_contact_revision} for s in env["family"]],
        **extra,
    }


def invite(env, *, status="SENT", restricted=False, **extra):
    captured = {}

    def send(invitation, token):
        captured.update(token=token, invitation=invitation)
        return status, "TEST_FAILURE" if status != "SENT" else "", "fake-reference"

    with patch("parents.family_invitation_sms.send_family_sms", side_effect=send) as provider:
        if restricted:
            with restricted_role():
                response = post(env["staff"], STAFF, {"invitations": [data(env, **extra)]})
        else:
            response = post(env["staff"], STAFF, {"invitations": [data(env, **extra)]})
        assert response.status_code == 201, response.content
        provider.assert_called_once()
    return captured["token"], GuardianFamilyInvitation.objects.get(
        pk=response.json()["invitations"][0]["id"]
    )


def activate(env, token, **extra):
    with patch("parents.email_recovery_tasks.send_parent_recovery_email.delay"):
        return post(
            env["parent"],
            ACTIVATE,
            {
                "token": token,
                "email": "family@parent.invalid",
                "new_password": PASSWORD,
                "confirm_password": PASSWORD,
                **extra,
            },
        )


@pytest.mark.parametrize(
    "search",
    [
        "أسرة صناعية",
        "اسرة صناعية",
        "0551900003",
        "٠٥٥١٩٠٠٠٠٣",
        "+966 55 190 0003",
        "00966551900003",
        "900003",
        "INVITE-00",
    ],
)
def test_search_keeps_all_siblings_and_school_scope(family_env, make_school, search):
    env = family_env
    other_school = make_school("مدرسة أخرى")
    foreign = setup_attendance_env(other_school, students_count=1)["students"][0]
    Student.objects.filter(pk=foreign.pk).update(
        guardian_mobile="0551900003",
        guardian_name="ولي أمر أسرة صناعية",
        full_name="طالب INVITE-00",
    )
    # Enough contacts to place the target family beyond the first page.
    extra = make_students(env["school"], env["section"], env["year"], 26, prefix="SEARCH")
    for i, child in enumerate(extra):
        Student.objects.filter(pk=child.pk).update(
            guardian_mobile=f"050100{i:04d}", guardian_name=f"أسرة أخرى {i}"
        )
    with restricted_role():
        first_page = env["staff"].get(STAFF).json()
        assert first_page["count"] == 27
        assert not any(row["mobile"] == "+966551900003" for row in first_page["results"])
        response = env["staff"].get(STAFF, {"search": search})
    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["count"] == 1
    assert payload["next"] is None
    assert payload["results"][0]["child_count"] == 3
    assert {child["id"] for child in payload["results"][0]["children"]} == {
        child.id for child in env["family"]
    }


def test_search_reviewed_invitation_name_and_no_results(family_env):
    env = family_env
    invite(env, name="أحمد صاحب الدعوة")
    with restricted_role():
        found = env["staff"].get(STAFF, {"search": "احمد الدعوة"})
        missing = env["staff"].get(STAFF, {"search": "اسم غير موجود"})
        invalid = env["staff"].get(STAFF, {"search": "x" * 151})
    assert found.status_code == 200, found.content
    assert found.json()["count"] == 1
    assert len(found.json()["results"][0]["children"]) == 3
    assert missing.status_code == 200
    assert missing.json()["count"] == 0
    assert invalid.status_code == 400


@pytest.mark.parametrize("restricted", [False, True])
def test_one_invite_three_exact_children_email_gate_and_staff_distinction(family_env, restricted):
    env = family_env
    with restricted_role():
        groups = env["staff"].get(STAFF)
    assert groups.status_code == 200, groups.content
    assert groups.json()["count"] == 1
    assert groups.json()["results"][0]["child_count"] == 3
    assert not groups.json()["results"][0]["needs_review"]
    token, invitation = invite(env, restricted=restricted)
    assert token not in str(env["staff"].get(STAFF).json())
    assert token not in str(list(AuditLog.objects.values("metadata")))
    with restricted_role():
        metadata = post(env["parent"], CHECK, {"token": token})
        assert metadata.status_code == 200, metadata.content
        assert set(metadata.json()) == {
            "school_name",
            "children_count",
            "account_exists",
            "requires_login",
            "email_verified",
        }
        response = activate(env, token)
        assert response.status_code == 200, response.content
        assert env["parent"].get("/api/v1/parent/children/").status_code == 403
    owner = User.objects.get(pk=response.json()["id"])
    assert owner.mobile == "+966551900003"
    assert GuardianStudentRelation.objects.filter(user=owner, status="ACTIVE").count() == 3
    assert AccountRecoveryEmail.objects.get(user=owner).verified_at is None
    provision_verified_recovery_email(owner)
    with restricted_role():
        assert len(env["parent"].get("/api/v1/parent/children/").json()["results"]) == 3
    assert activate(env, token).status_code == 409
    rows = env["staff"].get(STAFF).json()["results"]
    assert rows[0]["invitation"]["lifecycle"] == "ACTIVATED"
    invitation.refresh_from_db()
    assert invitation.activated_user_id == owner.id


@pytest.mark.parametrize(
    "role,status", [("VICE_PRINCIPAL", 200), ("TEACHER", 403), ("STUDENT_COUNSELOR", 403)]
)
def test_exact_staff_roles(family_env, role_client, role, status):
    client, _, _ = role_client([role], family_env["school"])
    with restricted_role():
        assert client.get(STAFF).status_code == status
        if status != 200:
            assert post(client, STAFF, {"invitations": [data(family_env)]}).status_code == 403


@pytest.mark.parametrize("change", ["phone", "name", "inactive", "blocked", "expiry"])
def test_stale_family_never_partially_grants(family_env, change):
    env = family_env
    token, invitation = invite(env)
    student = env["family"][1]
    if change in {"phone", "name"}:
        field = "guardian_mobile" if change == "phone" else "guardian_name"
        Student.objects.filter(pk=student.pk).update(
            **{field: "0551999999" if change == "phone" else "اسم مختلف"}
        )
    elif change == "inactive":
        Student.objects.filter(pk=student.pk).update(status="WITHDRAWN")
    elif change == "blocked":
        RecipientContactBlock.objects.create(
            school=env["school"],
            student=student,
            mobile_hash=recipient_hash(student.guardian_mobile),
            reason="رقم غير موثوق",
            created_by=env["actor"],
        )
    else:
        with patch(
            "parents.family_invitation_services.timezone.now",
            return_value=invitation.expires_at + timedelta(seconds=1),
        ):
            assert activate(env, token).status_code == 409
        return
    assert activate(env, token).status_code == 409
    assert not User.objects.filter(mobile="+966551900003").exists()
    assert not GuardianStudentRelation.objects.exists()


def test_existing_teacher_authenticates_keeps_password_and_recovery_credential(
    family_env, make_membership
):
    env = family_env
    owner = User.objects.create_user(
        mobile="0551900003", password=PASSWORD, email="staff@parent.invalid"
    )
    make_membership(owner, env["school"], ["TEACHER"])
    email = provision_verified_recovery_email(owner, "original@parent.invalid")
    original_password = owner.password
    token, _ = invite(env)
    assert activate(env, token).status_code == 403
    env["parent"].force_login(owner)
    with restricted_role():
        response = activate(env, token, email="attacker@parent.invalid")
    assert response.status_code == 200, response.content
    owner.refresh_from_db()
    email.refresh_from_db()
    assert owner.password == original_password and owner.email == "staff@parent.invalid"
    assert decrypt_value(email.current_email_encrypted) == "original@parent.invalid"
    assert response.json()["id"] == owner.id
    assert "TEACHER" in response.json()["memberships"][0]["roles"]
    assert (
        SchoolMembership.objects.get(user=owner, school=env["school"]).roles.get().role == "TEACHER"
    )


@pytest.mark.parametrize("status", ["FAILED", "UNKNOWN"])
def test_delivery_state_is_real_not_a_success_claim(family_env, status):
    token, invitation = invite(family_env, status=status)
    assert invitation.delivery_status == status
    with patch("parents.family_invitation_sms.send_family_sms") as provider:
        service.deliver_invitation(invitation.school_id, invitation.id, token)
        provider.assert_not_called()
    assert activate(family_env, token).status_code == (409 if status == "FAILED" else 200)


@pytest.mark.parametrize("provider_name", ["DREAMS", "MSEGAT"])
def test_reuses_provider_once_without_absence_paths(family_env, provider_name):
    env = family_env
    SchoolSmsIntegration.objects.filter(school=env["school"]).update(provider=provider_name)
    with patch(
        "parents.family_invitation_sms.send_sms",
        return_value=SmsProviderResult("provider-accepted"),
    ) as provider:
        response = post(env["staff"], STAFF, {"invitations": [data(env)]})
    assert response.status_code == 201, response.content
    provider.assert_called_once()
    message = provider.call_args.kwargs
    assert message["provider"] == provider_name and message["mobile"] == "+966551900003"
    assert env["school"].name in message["message"]
    assert all(s.full_name not in message["message"] for s in env["family"])
    assert "#token=" in message["message"]


@pytest.mark.parametrize("ambiguous", [False, True])
def test_provider_errors_sanitized_without_retry(family_env, ambiguous):
    with patch(
        "parents.family_invitation_sms.send_sms",
        side_effect=SmsProviderError("REJECTED", ambiguous=ambiguous),
    ) as provider:
        response = post(family_env["staff"], STAFF, {"invitations": [data(family_env)]})
    assert response.status_code == 201
    assert response.json()["invitations"][0]["delivery_status"] == (
        "UNKNOWN" if ambiguous else "FAILED"
    )
    provider.assert_called_once()


def test_duplicate_and_batch_stale_proofs_never_send(family_env):
    env = family_env
    stale = data(env)
    stale["children"][0]["revision"] += 1
    with patch("parents.family_invitation_sms.send_sms") as provider:
        assert post(env["staff"], STAFF, {"invitations": [data(env), stale]}).status_code == 409
        provider.assert_not_called()
    assert not GuardianFamilyInvitation.objects.exists()
    invite(env)
    with patch("parents.family_invitation_sms.send_sms") as provider:
        assert post(env["staff"], STAFF, {"invitations": [data(env)]}).status_code == 429
        provider.assert_not_called()


def test_foreign_child_and_actual_rls_are_denied(family_env, make_school):
    env = family_env
    other = make_school()
    foreign = setup_attendance_env(other, students_count=1)["students"][0]
    malicious = data(
        env, children=[{"id": foreign.id, "revision": foreign.guardian_contact_revision}]
    )
    with restricted_role():
        assert post(env["staff"], STAFF, {"invitations": [malicious]}).status_code == 409
    token, invitation = invite(env)
    with restricted_role(), tenant_context(school_id=other.id):
        assert not GuardianFamilyInvitation.objects.filter(pk=invitation.id).exists()
        assert service.invitation_index(token)["id"] == invitation.id
        assert not GuardianFamilyInvitation.objects.filter(pk=invitation.id).exists()


def test_bound_child_cannot_use_legacy_activation_or_replaced_proof(family_env):
    token, invitation = invite(family_env)
    activation = GuardianActivation.objects.get(
        family_child__invitation=invitation, student=family_env["student"]
    )
    individual = service._child_token(token, activation.id)
    assert (
        post(
            family_env["parent"],
            "/api/v1/parent/activation/",
            {
                "token": individual,
                "new_password": PASSWORD,
                "confirm_password": PASSWORD,
            },
        ).status_code
        == 409
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        GuardianActivation.objects.filter(pk=activation.pk).update(token_hash=token_hash("changed"))
    with pytest.raises(DatabaseError), transaction.atomic():
        GuardianFamilyInvitation.objects.filter(pk=invitation.pk).update(mobile_hash="a" * 64)


def test_transaction_failure_does_not_leave_partial_identity(family_env):
    token, _ = invite(family_env)
    original = service.apply_activation_relation
    counter = 0

    def fail(**kwargs):
        nonlocal counter
        counter += 1
        if counter == 2:
            raise DatabaseError("synthetic transaction interruption")
        return original(**kwargs)

    with patch("parents.family_invitation_services.apply_activation_relation", side_effect=fail):
        with pytest.raises(DatabaseError):
            activate(family_env, token)
    assert not User.objects.filter(mobile="+966551900003").exists()
    assert not GuardianStudentRelation.objects.exists()
    assert not GuardianActivation.objects.filter(used_at__isnull=False).exists()


def test_concurrent_activation_consumes_family_once(family_env):
    env = family_env
    token, _ = invite(env)
    barrier = Barrier(2)

    def attempt():
        connections.close_all()
        clear_tenant_context()
        try:
            barrier.wait(timeout=10)
            with patch("parents.email_recovery_tasks.send_parent_recovery_email.delay"):
                return post(
                    Client(),
                    ACTIVATE,
                    {
                        "token": token,
                        "email": "concurrent@parent.invalid",
                        "new_password": PASSWORD,
                        "confirm_password": PASSWORD,
                    },
                ).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: attempt(), range(2)))
    assert sorted(results) == [200, 409]
    assert User.objects.filter(mobile="+966551900003").count() == 1
    assert GuardianStudentRelation.objects.count() == 3


def test_duplicate_live_invitation_rejected_before_second_sms(family_env):
    env = family_env
    invite(env)
    with patch("parents.family_invitation_sms.send_family_sms") as provider:
        assert post(env["staff"], STAFF, {"invitations": [data(env)]}).status_code == 409
        provider.assert_not_called()


def test_missing_email_cannot_create_account_or_grants(family_env):
    token, _ = invite(family_env)
    assert activate(family_env, token, email=None).status_code == 400
    assert not User.objects.filter(mobile="+966551900003").exists()
    assert not GuardianStudentRelation.objects.exists()


def test_explicit_reissue_after_name_change_revokes_whole_previous_family(family_env):
    env = family_env
    token, invitation = invite(env)
    Student.objects.filter(pk=env["family"][0].pk).update(guardian_name="اسم راجعه المدير")
    env["family"][0].refresh_from_db()
    new_token, new_invitation = invite(env, reissue=True)
    assert invitation.id != new_invitation.id
    assert activate(env, token).status_code == 409
    assert activate(env, new_token).status_code == 200


def test_purge_one_student_revokes_all_unused_sibling_bearers(family_env):
    from students.services.purge import purge_student

    env = family_env
    token, invitation = invite(env)
    sibling = GuardianActivation.objects.get(
        family_child__invitation=invitation, student=env["family"][1]
    )
    Student.objects.filter(pk=env["student"].pk).update(status="WITHDRAWN")
    env["student"].refresh_from_db()
    with restricted_role(), tenant_context(school_id=env["school"].id, user_id=env["actor"].id):
        purge_student(env["student"], actor=env["actor"])
    assert not GuardianFamilyInvitation.objects.filter(pk=invitation.id).exists()
    sibling.refresh_from_db()
    assert sibling.revoked_at
    assert activate(env, token).status_code == 409
    assert Student.objects.filter(pk=env["family"][1].pk).exists()


def test_family_history_does_not_grow_list_query_count(family_env):
    env = family_env
    invite(env)
    with CaptureQueriesContext(connection) as first:
        assert env["staff"].get(STAFF).status_code == 200
    with patch("parents.family_invitation_sms.send_family_sms", return_value=("SENT", "", "fake")):
        for _ in range(8):
            service.create_invitation(
                school=env["school"], membership=env["membership"], data=data(env, reissue=True)
            )
    with CaptureQueriesContext(connection) as after:
        response = env["staff"].get(STAFF)
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert len(first) == len(after)
    assert any("DISTINCT ON" in query["sql"] for query in after)


def test_concurrent_issue_keeps_one_open_invitation_and_one_send(family_env):
    env = family_env
    barrier = Barrier(2)

    def issue():
        from common.errors import ApiError

        connections.close_all()
        clear_tenant_context()
        try:
            barrier.wait(timeout=10)
            with tenant_context(school_id=env["school"].id):
                try:
                    service.create_invitation(
                        school=env["school"], membership=env["membership"], data=data(env)
                    )
                    return "CREATED"
                except ApiError as exc:
                    return exc.code
        finally:
            connections.close_all()

    with patch(
        "parents.family_invitation_sms.send_family_sms", return_value=("SENT", "", "fake")
    ) as provider:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: issue(), range(2)))
        assert sorted(results) == ["CREATED", "INVITATION_EXISTS"]
        provider.assert_called_once()
    assert GuardianFamilyInvitation.objects.count() == 1


def test_database_catalog_and_data_rollback_guard(family_env):
    import importlib

    invite(family_env)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname IN "
            "('parents_guardianfamilyinvitation','parents_guardianfamilyinvitationchild')"
        )
        assert len(rows := cursor.fetchall()) == 2 and all(row[1] and row[2] for row in rows)
        cursor.execute(
            "SELECT count(*) FROM pg_policies WHERE tablename IN "
            "('parents_guardianfamilyinvitation','parents_guardianfamilyinvitationchild')"
        )
        assert cursor.fetchone()[0] == 8
        cursor.execute(
            "SELECT count(*) FROM pg_proc WHERE proname LIKE 'xmansx_parent_family_%' AND prosecdef"
        )
        assert cursor.fetchone()[0] == 0
    migration = importlib.import_module("parents.migrations.0010_guardianfamilyinvitation_and_more")
    with pytest.raises(DatabaseError), transaction.atomic(), connection.schema_editor() as editor:
        migration.backward(None, editor)
    assert GuardianFamilyInvitation.objects.count() == 1
