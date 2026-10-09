"""First guardian binding must use a fresh owner proof under the User row lock."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.admin import UserAdmin
from accounts.models import User
from common.errors import ApiError
from common.tenant_rls import clear_tenant_context, tenant_context
from parents.models import GuardianActivation, GuardianRegistrationRequest, GuardianStudentRelation
from parents.security import encrypt_value, mobile_hash, token_hash
from parents.services import complete_activation
from platform_team.models import PlatformStaffMembership
from platform_team.services import run_member_action
from students.models import Student
from tests.test_parent_recovery_independent_security import _restricted_role

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def activation_fixture(make_school, make_user):
    school = make_school()
    owner = make_user("0559802101")
    operator = make_user("0559802102")
    approver = make_user("0559802103")
    PlatformStaffMembership.objects.create(user=owner, role="SUPPORT", status="ACTIVE")
    PlatformStaffMembership.objects.create(
        user=operator, role="OPERATIONS_MANAGER", status="ACTIVE"
    )
    student = Student.objects.create(
        school=school,
        full_name="طالب التفعيل المتزامن",
        guardian_name="ولي الحساب الأصلي",
        guardian_mobile=owner.mobile,
        national_id_encrypted="synthetic-encrypted-identifier",
        national_id_lookup_hash="d" * 64,
        national_id_masked="******4321",
    )
    item = GuardianRegistrationRequest.objects.create(
        school=school,
        student=student,
        name="ولي الحساب الأصلي",
        mobile_encrypted=encrypt_value(owner.mobile),
        mobile_hash=mobile_hash(owner.mobile),
        mobile_masked="+9665****2101",
        identifier_encrypted="synthetic-encrypted-identifier",
        identifier_hash=student.national_id_lookup_hash,
        receipt_hash=token_hash(uuid4().hex),
        status="APPROVED",
        approved_by=approver,
        approved_at=timezone.now(),
        contact_revision=student.guardian_contact_revision,
    )
    token = uuid4().hex
    activation = GuardianActivation.objects.create(
        school=school,
        student=student,
        request=item,
        token_hash=token_hash(token),
        contact_revision=student.guardian_contact_revision,
        expires_at=timezone.now() + timedelta(hours=1),
        delivery_status="MANUAL",
    )
    client = Client()
    response = client.post(
        "/api/v1/auth/login/",
        {"mobile": owner.mobile, "password": "Str0ng-Pass-2026"},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    request = RequestFactory().post("/api/v1/parent/activation/complete/")
    request.user = owner
    request.session = client.session
    return school, owner, operator, item, activation, token, request


def test_reset_first_cannot_bind_guardian_from_pre_reset_authenticated_snapshot(
    activation_fixture, monkeypatch
):
    school, owner, operator, item, activation, token, request = activation_fixture
    reset_at_guard = Event()
    allow_reset = Event()
    reset_committed = Event()
    activation_select_started = Event()
    activation_select_completed = Event()
    state = {}
    real_generate = __import__(
        "platform_team.services", fromlist=["generate_temporary_password"]
    ).generate_temporary_password

    def pause_reset():
        reset_at_guard.set()
        assert allow_reset.wait(20), "coordinator did not release reset"
        return real_generate()

    monkeypatch.setattr("platform_team.services.generate_temporary_password", pause_reset)
    with _restricted_role() as role:

        def worker(kind):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"SET ROLE {role}")
                    cursor.execute("SELECT pg_backend_pid()")
                    state[kind] = cursor.fetchone()[0]
                clear_tenant_context()
                if kind == "reset":
                    try:
                        with tenant_context(user_id=operator.pk, bypass=True):
                            return run_member_action(
                                user_id=owner.pk, action="reset-password", actor=operator
                            )
                    finally:
                        reset_committed.set()

                def pause_owner_select(execute, sql, params, many, context):
                    target = 'FROM "accounts_user"' in sql and '"mobile" =' in sql
                    if target:
                        activation_select_started.set()
                    result = execute(sql, params, many, context)
                    if target:
                        activation_select_completed.set()
                        assert reset_committed.wait(20)
                    return result

                try:
                    with connection.execute_wrapper(pause_owner_select):
                        complete_activation(token=token, user=owner, request=request)
                    return "ACTIVATED"
                except ApiError as error:
                    return error.code
            finally:
                with connection.cursor() as cursor:
                    cursor.execute("RESET ROLE")
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            reset = pool.submit(worker, "reset")
            assert reset_at_guard.wait(20)
            binding = pool.submit(worker, "activation")
            try:
                assert activation_select_started.wait(20)
                deadline = time.monotonic() + 15
                locked = False
                while not activation_select_completed.is_set() and time.monotonic() < deadline:
                    # The coordinator reads only wait metadata as the DB owner;
                    # both business transactions continue under the non-bypass role.
                    with connection.cursor() as cursor:
                        cursor.execute("RESET ROLE")
                        cursor.execute(
                            "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s",
                            [state["activation"]],
                        )
                        row = cursor.fetchone()
                        cursor.execute(f"SET ROLE {role}")
                    locked = bool(row and row[0] == "Lock")
                    if locked:
                        break
                    time.sleep(0.02)
                assert activation_select_completed.is_set() or locked
            finally:
                allow_reset.set()
            result = reset.result(timeout=30)
            outcome = binding.result(timeout=30)
        assert result["temporary_password"]
        assert outcome in {"EXISTING_ACCOUNT_LOGIN_REQUIRED", "PASSWORD_CHANGE_REQUIRED"}, outcome
        with tenant_context(school_id=school.pk, user_id=owner.pk):
            assert not GuardianStudentRelation.objects.filter(
                user=owner, student=activation.student_id
            ).exists()
            activation.refresh_from_db()
            item.refresh_from_db()
            assert activation.used_at is None and item.status == "APPROVED"


def test_stale_authenticated_snapshot_denied_even_when_required_password_change_completed(
    activation_fixture,
):
    school, owner, operator, item, activation, token, request = activation_fixture
    with _restricted_role():
        with tenant_context(user_id=operator.pk, bypass=True):
            result = run_member_action(user_id=owner.pk, action="reset-password", actor=operator)
        # Simulate a current authorized password completion while the already
        # authenticated activation request still holds its original session proof.
        fresh = User.objects.get(pk=owner.pk)
        assert fresh.check_password(result["temporary_password"])
        fresh.set_password("Reset-Completed-New-Password-2026!")
        fresh.must_change_password = False
        fresh.save(update_fields=["password", "must_change_password"])
        with pytest.raises(ApiError) as error:
            complete_activation(token=token, user=owner, request=request)
        assert error.value.code == "EXISTING_ACCOUNT_LOGIN_REQUIRED"
        with tenant_context(school_id=school.pk):
            assert not GuardianStudentRelation.objects.filter(
                user=owner, student=activation.student_id
            ).exists()
            activation.refresh_from_db()
            item.refresh_from_db()
            assert activation.used_at is None and item.status == "APPROVED"


@pytest.mark.parametrize("credential", ["password", "mobile"])
@override_settings(ROOT_URLCONF="tests.test_parent_independent_account_security")
def test_admin_credential_change_serializes_with_first_guardian_binding(
    activation_fixture, monkeypatch, credential
):
    school, owner, operator, item, activation, token, request = activation_fixture
    operator.is_staff = True
    operator.save(update_fields=["is_staff"])
    operator.user_permissions.add(
        Permission.objects.get(content_type__app_label="accounts", codename="change_user")
    )
    client = Client()
    client.force_login(operator)
    original_password, original_mobile = owner.password, owner.mobile
    guarded = Event()
    resume_admin = Event()
    binding_finished = Event()
    owner_select_started = Event()
    state = {}
    real_guard = UserAdmin._has_guardian_relations

    def pause_first_guard(self, account):
        result = real_guard(self, account)
        if account and account.pk == owner.pk and not guarded.is_set():
            assert not result
            guarded.set()
            assert resume_admin.wait(20)
        return result

    monkeypatch.setattr(UserAdmin, "_has_guardian_relations", pause_first_guard)
    if credential == "password":
        url = reverse("independent_parent_admin:auth_user_password_change", args=[owner.pk])
        data = {
            "password1": "Admin-New-Synthetic-Password-2026!",
            "password2": "Admin-New-Synthetic-Password-2026!",
            "usable_password": "true",
        }
    else:
        url = reverse("independent_parent_admin:accounts_user_change", args=[owner.pk])
        data = {
            "mobile": "+966559802104",
            "first_name": owner.first_name,
            "last_name": owner.last_name,
            "email": owner.email,
            "is_active": "on",
            "groups": [],
            "_save": "Save",
        }

    with _restricted_role() as role:

        def worker(kind):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"SET ROLE {role}")
                    cursor.execute("SELECT pg_backend_pid()")
                    state[kind] = cursor.fetchone()[0]
                clear_tenant_context()
                if kind == "admin":
                    return client.post(url, data).status_code

                def observe_owner_select(execute, sql, params, many, context):
                    if 'FROM "accounts_user"' in sql and '"mobile" =' in sql:
                        owner_select_started.set()
                    return execute(sql, params, many, context)

                try:
                    with connection.execute_wrapper(observe_owner_select):
                        complete_activation(token=token, user=owner, request=request)
                    return "ACTIVATED"
                except ApiError as error:
                    return error.code
                finally:
                    binding_finished.set()
            finally:
                with connection.cursor() as cursor:
                    cursor.execute("RESET ROLE")
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            admin_change = pool.submit(worker, "admin")
            assert guarded.wait(20)
            binding = pool.submit(worker, "binding")
            try:
                assert owner_select_started.wait(20)
                deadline = time.monotonic() + 15
                locked = False
                while not binding_finished.is_set() and time.monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute("RESET ROLE")
                        cursor.execute(
                            "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s",
                            [state["binding"]],
                        )
                        row = cursor.fetchone()
                        cursor.execute(f"SET ROLE {role}")
                    locked = bool(row and row[0] == "Lock")
                    if locked:
                        break
                    time.sleep(0.02)
                assert binding_finished.is_set() or locked
            finally:
                resume_admin.set()
            admin_status = admin_change.result(timeout=30)
            binding_result = binding.result(timeout=30)

        assert admin_status in {302, 403}
        owner.refresh_from_db()
        with tenant_context(school_id=school.pk, user_id=owner.pk):
            relation = GuardianStudentRelation.objects.filter(
                user=owner, student=activation.student_id
            )
            if binding_result == "ACTIVATED":
                assert admin_status == 403
                assert owner.password == original_password and owner.mobile == original_mobile
                assert relation.count() == 1 and relation.get().status == "ACTIVE"
            else:
                assert (
                    credential == "password" and binding_result == "EXISTING_ACCOUNT_LOGIN_REQUIRED"
                )
                assert not relation.exists()
                activation.refresh_from_db()
                item.refresh_from_db()
                assert activation.used_at is None and item.status == "APPROVED"
