"""Independent regressions for global credentials and additive-schema compatibility."""

from contextlib import contextmanager
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from django.contrib.admin import AdminSite
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import Client, override_settings
from django.urls import include, path, reverse
from django.utils import timezone

from accounts.admin import UserAdmin
from accounts.models import User
from common.security.identifiers import (
    decrypt_national_id,
    encrypt_national_id,
    mask_national_id,
    national_id_lookup_hash,
)
from common.tenant_rls import clear_tenant_context, tenant_context
from memberships.models import SchoolMembership
from parents.models import (
    GuardianActivation,
    GuardianContactReview,
    GuardianRegistrationRequest,
    GuardianStudentRelation,
    ParentRegistrationConfig,
)
from platform_team.models import PlatformStaffMembership
from students.models import Student
from tests.attendance_helpers import setup_attendance_env

pytestmark = pytest.mark.django_db
NEW_PASSWORD = "Independent-Account-Password-2026!"

# Exercise the actual registered ModelAdmin through HTTP, even when the production
# URL configuration deliberately disables its normal administration surface.
admin_site = AdminSite(name="independent_parent_admin")
admin_site.register(User, UserAdmin)
urlpatterns = [
    path("independent-admin/", admin_site.urls),
    path("", include("config.urls")),
]


def _student(school, *, historical=False):
    identifier = "1066900123"
    model = Student
    if historical:
        # This is the actual model state known to the baseline application. Its
        # INSERT omits guardian_contact_revision rather than supplying a test value.
        state = MigrationLoader(connection).project_state(
            [("students", "0006_student_merged_into")]
        )
        model = state.apps.get_model("students", "Student")
        assert "guardian_contact_revision" not in {
            field.name for field in model._meta.concrete_fields
        }
    return model.objects.create(
        school_id=school.pk,
        full_name="طالب توافق المخطط",
        national_id_encrypted=encrypt_national_id(identifier),
        national_id_lookup_hash=national_id_lookup_hash(identifier),
        national_id_masked=mask_national_id(identifier),
        guardian_name="ولي صاحب الحساب",
        guardian_mobile="+966550089001",
    )


def _relation(student, owner, approver, *, status="ACTIVE"):
    return GuardianStudentRelation.objects.create(
        school_id=student.school_id,
        student_id=student.pk,
        user=owner,
        status=status,
        approved_by=approver,
        approved_at=timezone.now(),
        contact_revision=1,
    )


@pytest.mark.parametrize("status", ["ACTIVE", "SUSPENDED_CONTACT_REVIEW", "REVOKED"])
@pytest.mark.parametrize("superuser", [False, True])
@override_settings(ROOT_URLCONF=__name__)
def test_admin_password_endpoint_cannot_reset_any_global_guardian_account(
    make_school, make_user, status, superuser
):
    school = make_school("مدرسة العلاقة العالمية")
    owner = make_user("0550089001")
    operator = make_user("0550089002", is_staff=True, is_superuser=superuser)
    if not superuser:
        operator.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="accounts", codename="change_user"
            )
        )
    relation = _relation(_student(school), owner, operator, status=status)
    original_hash = owner.password
    owner_client = Client()
    owner_client.force_login(owner)
    original_session = owner_client.session.session_key
    original_auth_hash = owner_client.session["_auth_user_hash"]
    client = Client()
    client.force_login(operator)
    password_url = reverse(
        "independent_parent_admin:auth_user_password_change", args=[owner.pk]
    )

    response = client.post(
        password_url,
        {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD, "usable_password": "true"},
    )

    assert response.status_code == 403, response.content
    assert client.get(password_url).status_code == 403
    owner.refresh_from_db()
    relation.refresh_from_db()
    assert owner.password == original_hash
    assert owner.mobile == "+966550089001"
    assert relation.user_id == owner.pk and relation.status == status
    assert owner_client.get("/api/v1/auth/me/").status_code == 200
    assert owner_client.session.session_key == original_session
    assert owner_client.session["_auth_user_hash"] == original_auth_hash


@override_settings(ROOT_URLCONF=__name__)
def test_ordinary_admin_password_reset_remains_available(make_user):
    owner = make_user("0550089011")
    operator = make_user("0550089012", is_staff=True)
    operator.user_permissions.add(
        Permission.objects.get(content_type__app_label="accounts", codename="change_user")
    )
    client = Client()
    client.force_login(operator)
    response = client.post(
        reverse("independent_parent_admin:auth_user_password_change", args=[owner.pk]),
        {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD, "usable_password": "true"},
    )
    assert response.status_code == 302, response.content
    owner.refresh_from_db()
    assert owner.check_password(NEW_PASSWORD)


@override_settings(ROOT_URLCONF=__name__)
def test_admin_change_form_cannot_assign_a_posted_guardian_password(make_school, make_user):
    school = make_school("مدرسة حماية نموذج الحساب")
    owner = make_user("0550089001")
    operator = make_user("0550089002", is_staff=True)
    operator.user_permissions.add(
        Permission.objects.get(content_type__app_label="accounts", codename="change_user")
    )
    _relation(_student(school), owner, operator)
    original_hash = owner.password
    client = Client()
    client.force_login(operator)
    response = client.post(
        reverse("independent_parent_admin:accounts_user_change", args=[owner.pk]),
        {
            "first_name": owner.first_name,
            "last_name": owner.last_name,
            "email": owner.email,
            "is_active": "on",
            "groups": [],
            "password": "pbkdf2_sha256$forged-password-hash",
            "password1": NEW_PASSWORD,
            "password2": NEW_PASSWORD,
            "_save": "Save",
        },
    )
    assert response.status_code == 302, response.content
    owner.refresh_from_db()
    assert owner.password == original_hash
    assert not owner.check_password(NEW_PASSWORD)


def test_admin_save_rejects_guardian_password_replacement_even_without_change_form(
    make_school, make_user
):
    school = make_school("مدرسة حماية حفظ الحساب")
    owner = make_user("0550089001")
    operator = make_user("0550089002", is_staff=True, is_superuser=True)
    _relation(_student(school), owner, operator)
    original_hash = owner.password
    owner.set_password(NEW_PASSWORD)
    with pytest.raises(PermissionDenied):
        admin_site._registry[User].save_model(SimpleNamespace(user=operator), owner, None, True)
    owner.refresh_from_db()
    assert owner.password == original_hash


@pytest.mark.parametrize("status", ["ACTIVE", "SUSPENDED_CONTACT_REVIEW", "REVOKED"])
@pytest.mark.parametrize("platform_role", ["SUPPORT", "OWNER"])
def test_platform_password_reset_confirmation_cannot_replace_guardian_ownership_proof(
    make_school, make_user, make_membership, status, platform_role
):
    employment_school = make_school("مدرسة عمل المدير")
    family_school = make_school("مدرسة الأبناء المستقلة")
    owner = make_user("0550089001")
    operator = make_user("0550089002", is_superuser=platform_role == "OWNER")
    if platform_role != "OWNER":
        PlatformStaffMembership.objects.create(user=operator, role=platform_role, status="ACTIVE")
    membership = make_membership(owner, employment_school, ["SCHOOL_MANAGER"])
    relation = _relation(_student(family_school), owner, operator, status=status)
    owner_client = Client()
    owner_client.force_login(owner)
    original_hash = owner.password
    original_auth_hash = owner_client.session["_auth_user_hash"]
    original_session_key = owner_client.session.session_key
    client = Client()
    client.force_login(operator)

    response = client.post(
        f"/api/v1/platform/schools/{employment_school.pk}/managers/{membership.pk}/reset-password/",
        {"confirm_shared_account_impact": True},
        content_type="application/json",
    )

    assert response.status_code == 409, response.content
    assert response.json()["code"] == "GUARDIAN_ACCOUNT_PASSWORD_RESET_NOT_ALLOWED"
    assert "temporary_password" not in response.json()
    owner.refresh_from_db()
    relation.refresh_from_db()
    assert owner.password == original_hash and not owner.must_change_password
    assert owner.mobile == "+966550089001"
    assert relation.user_id == owner.pk and relation.status == status
    assert SchoolMembership.objects.get(pk=membership.pk).user_id == owner.pk
    assert owner_client.get("/api/v1/auth/me/").status_code == 200
    assert owner_client.session["_auth_user_hash"] == original_auth_hash
    assert owner_client.session.session_key == original_session_key


def test_platform_ordinary_manager_password_reset_remains_available(
    make_school, make_user, make_membership
):
    school = make_school("مدرسة مدير بلا حساب أسرة")
    owner = make_user("0550089041")
    operator = make_user("0550089042")
    PlatformStaffMembership.objects.create(user=operator, role="SUPPORT", status="ACTIVE")
    membership = make_membership(owner, school, ["SCHOOL_MANAGER"])
    client = Client()
    client.force_login(operator)
    response = client.post(
        f"/api/v1/platform/schools/{school.pk}/managers/{membership.pk}/reset-password/",
        {"confirm_shared_account_impact": True},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    owner.refresh_from_db()
    assert owner.check_password(response.json()["temporary_password"])
    assert owner.must_change_password


def test_baseline_student_insert_omits_revision_and_contact_guard_still_runs(
    make_school, make_user
):
    school = make_school("مدرسة توافق التطبيق السابق")
    owner = make_user("0550089001")
    approver = make_user("0550089002")
    historical_student = _student(school, historical=True)
    student = Student.objects.get(pk=historical_student.pk)
    assert student.guardian_contact_revision == 1
    relation = _relation(student, owner, approver)

    # The old application doesn't know the revision column, yet an old-style UPDATE
    # must still execute the current database suspension guard after a code rollback.
    type(historical_student).objects.filter(pk=student.pk).update(
        guardian_mobile="+966550089099"
    )

    student.refresh_from_db()
    relation.refresh_from_db()
    owner.refresh_from_db()
    assert student.guardian_contact_revision == 2
    assert relation.status == "SUSPENDED_CONTACT_REVIEW"
    assert GuardianContactReview.objects.filter(student=student, current_revision=2).exists()
    assert owner.mobile == "+966550089001"


@contextmanager
def _application_role():
    role = connection.ops.quote_name(f"independent_parent_rls_{uuid4().hex}")
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {role} NOSUPERUSER NOBYPASSRLS")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            cursor.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"
            )
            cursor.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
            cursor.execute(f"SET ROLE {role}")
            cursor.execute(
                "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
            assert cursor.fetchone() == (False, False)
        clear_tenant_context()
        with override_settings(DATABASE_RLS_ENFORCED=True):
            yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP OWNED BY {role}")
            cursor.execute(f"DROP ROLE IF EXISTS {role}")
        clear_tenant_context()


@pytest.mark.django_db(transaction=True)
def test_existing_employee_activates_three_schools_under_real_rls_without_identity_takeover(
    make_school, make_user, make_membership
):
    owner = make_user("0550089021", recovery_email_verified=True)
    wrong_owner = make_user("0550089022")
    original_hash = owner.password
    fixtures = []
    for index in range(3):
        school = make_school(f"مدرسة الحساب المختلط {index + 1}")
        manager = make_user(f"055008903{index}")
        make_membership(manager, school, ["SCHOOL_MANAGER"])
        attendance = setup_attendance_env(school, students_count=1)
        student = attendance["students"][0]
        student.guardian_mobile = owner.mobile
        student.save(update_fields=["guardian_mobile"])
        config = ParentRegistrationConfig.objects.create(school=school, enabled=True)
        staff_client = Client()
        staff_client.force_login(manager)
        # Client.session returns a new SessionStore each access; save the one changed.
        staff_session = staff_client.session
        staff_session["active_school_id"] = school.pk
        staff_session.save()
        fixtures.append((school, student, config, staff_client))
    employment = make_membership(owner, fixtures[0][0], ["TEACHER"])
    owner_client, wrong_client, anonymous = Client(), Client(), Client()

    with _application_role():
        login = owner_client.post(
            "/api/v1/auth/login/",
            {"mobile": owner.mobile, "password": "Str0ng-Pass-2026"},
            content_type="application/json",
        )
        assert login.status_code == 200, login.content
        wrong_client.force_login(wrong_owner)
        wrong_session_key = wrong_client.session.session_key
        wrong_auth_hash = wrong_client.session["_auth_user_hash"]
        owner_auth_hash = owner_client.session["_auth_user_hash"]
        relations, registrations = [], []
        for school, student, config, staff_client in fixtures:
            registration = anonymous.post(
                f"/api/v1/parent/registration/{config.token}/",
                {
                    "name": "ولي صاحب الحساب الحالي",
                    "mobile": owner.mobile,
                    "email": "existing-owner-registration@parent.invalid",
                    "student_identifier": decrypt_national_id(student.national_id_encrypted),
                    "relationship_type": "أب",
                },
                content_type="application/json",
            )
            assert registration.status_code == 202, registration.content
            with tenant_context(school_id=school.pk):
                item = GuardianRegistrationRequest.objects.get(school=school)
            registrations.append(item.pk)
            approval = staff_client.post(
                f"/api/v1/staff/parents/registrations/{item.pk}/decision/",
                {
                    "decision": "APPROVE",
                    "student_id": student.pk,
                    "verification_note": "تحقق مستقل حضورياً من هوية وصلة ولي الأمر",
                    "contact_bound": True,
                    "delivery": "MANUAL",
                },
                content_type="application/json",
            )
            assert approval.status_code == 200, approval.content
            token = parse_qs(urlsplit(approval.json()["activation_url"]).fragment)["token"][0]
            malicious_payload = {
                "token": token,
                "new_password": NEW_PASSWORD,
                "confirm_password": NEW_PASSWORD,
            }
            for unauthorized in (anonymous, wrong_client):
                denied = unauthorized.post(
                    "/api/v1/parent/activation/", malicious_payload, content_type="application/json"
                )
                assert denied.status_code == 403, denied.content
            owner.refresh_from_db()
            assert owner.password == original_hash
            assert wrong_client.session.session_key == wrong_session_key
            assert wrong_client.session["_auth_user_hash"] == wrong_auth_hash
            assert wrong_client.session["_auth_user_id"] == str(wrong_owner.pk)
            with tenant_context(school_id=school.pk):
                assert GuardianActivation.objects.get(request=item).used_at is None
                assert not GuardianStudentRelation.objects.filter(student=student).exists()
            activated = owner_client.post(
                "/api/v1/parent/activation/", malicious_payload, content_type="application/json"
            )
            assert activated.status_code == 200, activated.content
            assert activated.json()["id"] == owner.pk
            assert activated.json()["active_school"]["id"] == employment.school_id
            assert activated.json()["roles"] == ["TEACHER"]
            with tenant_context(school_id=school.pk):
                relations.append(GuardianStudentRelation.objects.get(student=student).pk)
            owner.refresh_from_db()
            assert owner.password == original_hash
            assert owner_client.session["_auth_user_hash"] == owner_auth_hash

        children = owner_client.get("/api/v1/parent/children/")
        assert children.status_code == 200, children.content
        assert {row["relation_id"] for row in children.json()["results"]} == set(relations)
        assert {row["school"]["id"] for row in children.json()["results"]} == {
            school.pk for school, *_ in fixtures
        }
        assert fixtures[0][3].get(
            f"/api/v1/staff/parents/registrations/{registrations[1]}/"
        ).status_code == 404
        assert owner_client.get("/api/v1/staff/parents/settings/").status_code == 403
        with tenant_context(user_id=owner.pk):
            assert SchoolMembership.objects.filter(user=owner).count() == 1
            assert SchoolMembership.objects.get(pk=employment.pk).role_codes() == ["TEACHER"]
        revoked = fixtures[1][3].post(
            f"/api/v1/staff/parents/relations/{relations[1]}/decision/",
            {"status": "REVOKED", "reason": "انتهت الصفة في المدرسة الثانية فقط"},
            content_type="application/json",
        )
        assert revoked.status_code == 200, revoked.content
        assert owner_client.get(f"/api/v1/parent/children/{relations[1]}/").status_code == 404
        for relation_id in (relations[0], relations[2]):
            response = owner_client.get(f"/api/v1/parent/children/{relation_id}/")
            assert response.status_code == 200, response.content
        assert User.objects.filter(mobile=owner.mobile).count() == 1
        owner.refresh_from_db()
        assert owner.password == original_hash
