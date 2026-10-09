"""School deletion preserves independent global recovery credentials under real RLS."""

from uuid import uuid4

import pytest
from django.db import connection
from django.test import Client, override_settings
from django.utils import timezone

from accounts.models import User
from common.tenant_rls import clear_tenant_context, tenant_context
from memberships.models import SchoolMembership
from parents.email_recovery_models import AccountRecoveryEmail, AccountRecoveryEmailDelivery
from parents.email_recovery_services import credential_fingerprint, recovery_email_hash
from parents.models import GuardianStudentRelation
from parents.security import encrypt_value
from schools.models import School
from tests.attendance_helpers import setup_attendance_env

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "School-Purge-Recovery-2026!"


@pytest.mark.parametrize("state", ["verified_parent", "pending_parent", "verified_orphan"])
def test_restricted_school_purge_preserves_global_recovery_owner_and_deletes_ordinary_orphan(
    make_school,
    make_membership,
    state,
):
    school = make_school("مدرسة حذف صناعية")
    owner = User.objects.create_user(
        mobile="0551800401", password=PASSWORD, is_superuser=True, is_staff=True
    )
    guardian = User.objects.create_user(mobile="0551800402", password=PASSWORD)
    ordinary = User.objects.create_user(mobile="0551800403", password=PASSWORD)
    make_membership(guardian, school, ["TEACHER"])
    make_membership(ordinary, school, ["TEACHER"])
    if state != "verified_orphan":
        student = setup_attendance_env(school, students_count=1)["students"][0]
        GuardianStudentRelation.objects.create(
            user=guardian,
            school=school,
            student=student,
            status="ACTIVE",
            contact_bound=False,
            approved_by=owner,
            approved_at=timezone.now(),
        )
    address = "owner@example.invalid"
    lookup = recovery_email_hash(address)
    item = AccountRecoveryEmail.objects.create(
        user=guardian,
        current_email_encrypted=encrypt_value(address) if state != "pending_parent" else "",
        current_email_hash=lookup if state != "pending_parent" else None,
        verified_at=timezone.now() if state != "pending_parent" else None,
        pending_email_encrypted=encrypt_value(address) if state == "pending_parent" else "",
        pending_email_hash=lookup if state == "pending_parent" else "",
    )
    delivery = AccountRecoveryEmailDelivery.objects.create(
        user=guardian,
        recovery_email=item,
        purpose="RECOVERY_EMAIL_VERIFICATION" if state == "pending_parent" else "PASSWORD_RESET",
        email_hash=lookup,
        email_revision=1,
        password_fingerprint=credential_fingerprint(guardian),
        mobile_fingerprint="f" * 64,
    )
    original_credential = AccountRecoveryEmail.objects.values().get(id=item.id)
    original_delivery = AccountRecoveryEmailDelivery.objects.values().get(id=delivery.id)
    original_user = User.objects.values("id", "mobile", "password").get(id=guardian.id)
    client = Client(raise_request_exception=False)
    client.force_login(owner)
    role = connection.ops.quote_name(f"parent_email_purge_{uuid4().hex}")
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
            with tenant_context(user_id=owner.id, bypass=True):
                # General platform authority must not expose global private credentials.
                assert AccountRecoveryEmail.objects.count() == 0
                assert AccountRecoveryEmailDelivery.objects.count() == 0
            response = client.delete(
                f"/api/v1/platform/schools/{school.id}/",
                {"confirmation_name": school.name, "acknowledge_permanent_deletion": True},
                content_type="application/json",
            )
            assert response.status_code == 200, response.content
            assert response.json()["user_accounts_deleted"] == 1
            assert address.encode() not in response.content
            with tenant_context(user_id=guardian.id):
                assert AccountRecoveryEmail.objects.values().get(id=item.id) == original_credential
                assert (
                    AccountRecoveryEmailDelivery.objects.values().get(id=delivery.id)
                    == original_delivery
                )
            with tenant_context(user_id=owner.id, bypass=True):
                assert not School.objects.filter(id=school.id).exists()
                assert not SchoolMembership.objects.filter(school_id=school.id).exists()
                assert not GuardianStudentRelation.objects.filter(school_id=school.id).exists()
            assert (
                User.objects.values("id", "mobile", "password").get(id=guardian.id) == original_user
            )
            assert not User.objects.filter(id=ordinary.id).exists()
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP OWNED BY {role}")
            cursor.execute(f"DROP ROLE IF EXISTS {role}")
        clear_tenant_context()
