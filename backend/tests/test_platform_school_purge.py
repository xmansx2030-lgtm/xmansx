from uuid import uuid4

import pytest
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import override_settings
from django.utils import timezone

from attendance.models import AttendanceMark, AttendanceSession
from audit.models import AuditAction, AuditLog
from common.errors import ApiError
from common.tenant_rls import clear_tenant_context, tenant_context
from memberships.models import SchoolMembership
from platform_team.models import PlatformStaffMembership, PlatformStaffRole
from schools.models import School
from schools.services.settings import get_or_create_settings
from subscriptions.models import SaaSPlan
from subscriptions.services import subscriptions as subscription_service
from subscriptions.services.school_purge import (
    permanently_delete_school,
    school_scoped_models_in_delete_order,
)
from tests.attendance_helpers import setup_attendance_env


@pytest.fixture
def application_db_role():
    """Enforce the same RLS restrictions as Render's non-superuser DB account."""
    role = connection.ops.quote_name(f"school_purge_test_{uuid4().hex}")
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE ROLE {role} NOSUPERUSER NOBYPASSRLS")
        cursor.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
        cursor.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"
        )
        cursor.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
    try:
        yield role
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP OWNED BY {role}")
            cursor.execute(f"DROP ROLE IF EXISTS {role}")
        clear_tenant_context()


def _audit_purge_scope():
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.school_purge_id', true)")
        return cursor.fetchone()[0] or ""


@pytest.mark.django_db(transaction=True)
def test_platform_admin_permanently_deletes_school_data_and_only_orphan_accounts(
    client, make_membership, make_school, make_user, settings, tmp_path, application_db_role
):
    settings.MEDIA_ROOT = tmp_path
    admin = make_user("0550008010", is_staff=True, is_superuser=True)
    exclusive_user = make_user("0550008011")
    shared_user = make_user("0550008012")
    school = make_school("مدرسة الحذف الشامل")
    other_school = make_school("مدرسة باقية")
    exclusive_membership = make_membership(exclusive_user, school, ["TEACHER"])
    make_membership(shared_user, school, ["SCHOOL_MANAGER"])
    make_membership(shared_user, other_school, ["TEACHER"])
    platform_user = make_user("0550008013")
    PlatformStaffMembership.objects.create(user=platform_user, role=PlatformStaffRole.SUPPORT)
    make_membership(platform_user, school, ["TEACHER"])
    other_event = AuditLog.objects.create(school=other_school, action=AuditAction.LOGIN_SUCCESS)
    global_event = AuditLog.objects.create(action=AuditAction.LOGIN_SUCCESS)
    plan = SaaSPlan.objects.create(code="purge-test", name_ar="باقة اختبار الحذف")
    subscription_service.start_trial(school=school, plan_id=plan.id, actor=admin, trial_days=10)

    attendance = setup_attendance_env(school, students_count=1)
    session = AttendanceSession.objects.create(
        school=school,
        academic_year=attendance["year"],
        section=attendance["section"],
        attendance_date=timezone.localdate(),
        bell_period=attendance["period"],
        period_sequence=attendance["period"].sequence,
        bell_period_snapshot={"sequence": attendance["period"].sequence},
        roster_fingerprint="test",
        unprepared_alert_minutes_snapshot=25,
        started_by_membership=exclusive_membership,
    )
    AttendanceMark.objects.create(
        school=school,
        session=session,
        student=attendance["students"][0],
        status="ABSENT",
    )
    AuditLog.objects.create(
        school=school,
        actor=exclusive_user,
        action=AuditAction.ATTENDANCE_STARTED,
    )
    school_settings = get_or_create_settings(school=school)
    school_settings.logo.save("logo.png", ContentFile(b"school-logo"))
    logo_path = tmp_path / school_settings.logo.name
    assert logo_path.exists()

    client.force_login(admin)
    with connection.cursor() as cursor:
        cursor.execute(f"SET ROLE {application_db_role}")
    with override_settings(DATABASE_RLS_ENFORCED=True):
        mismatch = client.delete(
            f"/api/v1/platform/schools/{school.id}/",
            {
                "confirmation_name": "اسم غير مطابق",
                "acknowledge_permanent_deletion": True,
            },
            content_type="application/json",
        )
        assert mismatch.status_code == 409
        assert mismatch.json()["code"] == "SCHOOL_DELETE_CONFIRMATION_MISMATCH"
        assert _audit_purge_scope() == ""
        with tenant_context(bypass=True):
            assert School.objects.filter(id=school.id).exists()

        response = client.delete(
            f"/api/v1/platform/schools/{school.id}/",
            {
                "confirmation_name": school.name,
                "acknowledge_permanent_deletion": True,
            },
            content_type="application/json",
        )
    assert _audit_purge_scope() == ""
    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert response.json()["storage_objects_deleted"] == 1
    assert response.json()["storage_objects_failed"] == 0
    assert not logo_path.exists()
    assert not school.__class__.objects.filter(id=school.id).exists()
    for scoped in school_scoped_models_in_delete_order():
        assert not scoped.model._default_manager.filter(
            **{scoped.school_field.attname: school.id}
        ).exists()

    assert not exclusive_user.__class__.objects.filter(id=exclusive_user.id).exists()
    assert shared_user.__class__.objects.filter(id=shared_user.id).exists()
    assert platform_user.__class__.objects.filter(id=platform_user.id).exists()
    assert PlatformStaffMembership.objects.filter(user=platform_user).exists()
    assert SchoolMembership.objects.filter(user=shared_user, school=other_school).exists()
    assert AuditLog.objects.filter(id__in=[other_event.id, global_event.id]).count() == 2
    assert SaaSPlan.objects.filter(id=plan.id).exists()
    deletion_log = AuditLog.objects.get(
        action=AuditAction.PLATFORM_SCHOOL_PERMANENTLY_DELETED,
        target_id=str(school.id),
    )
    assert deletion_log.school_id is None
    assert deletion_log.actor == admin


@pytest.mark.django_db(transaction=True)
def test_audit_purge_policy_requires_platform_context_and_exact_school(
    make_school, application_db_role
):
    school = make_school("المدرسة المستهدفة")
    other_school = make_school("مدرسة أخرى")
    target_event = AuditLog.objects.create(school=school, action=AuditAction.LOGIN_SUCCESS)
    other_event = AuditLog.objects.create(school=other_school, action=AuditAction.LOGIN_SUCCESS)
    global_event = AuditLog.objects.create(action=AuditAction.LOGIN_SUCCESS)
    with connection.cursor() as cursor:
        cursor.execute(f"SET ROLE {application_db_role}")

    with tenant_context(school_id=school.id), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.school_purge_id', %s, true)", [str(school.id)])
        assert AuditLog.objects.all().delete()[0] == 0
        assert AuditLog.objects.filter(id=target_event.id).update(action="CHANGED") == 0

    assert _audit_purge_scope() == ""
    with tenant_context(bypass=True):
        # A regular platform request must not gain general audit DELETE or UPDATE access.
        assert AuditLog.objects.all().delete()[0] == 0
        assert AuditLog.objects.all().update(action="CHANGED") == 0
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.school_purge_id', %s, true)", [str(school.id)]
                )
            assert AuditLog.objects.all().delete()[0] == 1
            assert set(AuditLog.objects.values_list("id", flat=True)) == {
                other_event.id, global_event.id,
            }
        assert _audit_purge_scope() == ""
        assert AuditLog.objects.all().delete()[0] == 0


@pytest.mark.django_db(transaction=True)
def test_school_purge_failure_restores_audit_records_and_preserves_files(
    client, make_school, make_user, make_membership, application_db_role, monkeypatch, tmp_path,
    settings,
):
    admin = make_user("0550008020", is_superuser=True)
    user = make_user("0550008021")
    school = make_school("مدرسة التراجع عن الحذف")
    membership = make_membership(user, school, ["SCHOOL_MANAGER"])
    event = AuditLog.objects.create(school=school, action=AuditAction.LOGIN_SUCCESS)
    settings.MEDIA_ROOT = tmp_path
    school_settings = get_or_create_settings(school=school)
    school_settings.logo.save("logo.png", ContentFile(b"school-logo"))
    logo_path = tmp_path / school_settings.logo.name

    def block_school_delete(*args, **kwargs):
        assert _audit_purge_scope() == ""
        raise ProtectedError("Injected final-school deletion failure", [event])

    monkeypatch.setattr(School, "delete", block_school_delete)
    client.force_login(admin)
    with connection.cursor() as cursor:
        cursor.execute(f"SET ROLE {application_db_role}")
    with override_settings(DATABASE_RLS_ENFORCED=True):
        response = client.delete(
            f"/api/v1/platform/schools/{school.id}/",
            {"confirmation_name": school.name, "acknowledge_permanent_deletion": True},
            content_type="application/json",
        )
    assert response.status_code == 409
    assert response.json()["code"] == "SCHOOL_DELETE_BLOCKED"
    assert _audit_purge_scope() == ""
    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")
    assert School.objects.filter(id=school.id).exists()
    assert SchoolMembership.objects.filter(id=membership.id).exists()
    assert AuditLog.objects.filter(id=event.id).exists()
    assert user.__class__.objects.filter(id=user.id).exists()
    assert logo_path.exists()
    assert not AuditLog.objects.filter(
        action=AuditAction.PLATFORM_SCHOOL_PERMANENTLY_DELETED
    ).exists()


@pytest.mark.django_db
def test_school_purge_service_rechecks_platform_manage_permission(make_school, make_user):
    school = make_school("مدرسة محمية من الحذف المباشر")
    actor = make_user("0550008030")
    with pytest.raises(ApiError) as error:
        permanently_delete_school(school_id=school.id, confirmation_name=school.name, actor=actor)
    assert error.value.code == "PERMISSION_DENIED"
    assert School.objects.filter(id=school.id).exists()


@pytest.mark.django_db(transaction=True)
def test_school_purge_refuses_silently_filtered_audit_deletion(
    client, make_school, make_user, make_membership, application_db_role
):
    admin = make_user("0550008040", is_superuser=True)
    user = make_user("0550008041")
    school = make_school("مدرسة سياسة الحذف الناقصة")
    membership = make_membership(user, school, ["SCHOOL_MANAGER"])
    event = AuditLog.objects.create(school=school, action=AuditAction.LOGIN_SUCCESS)
    client.force_login(admin)

    # Reproduce a deployment missing the policy without changing the test DB permanently.
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("DROP POLICY audit_school_purge_delete ON audit_auditlog")
            cursor.execute(f"SET ROLE {application_db_role}")
        try:
            with override_settings(DATABASE_RLS_ENFORCED=True):
                response = client.delete(
                    f"/api/v1/platform/schools/{school.id}/",
                    {"confirmation_name": school.name, "acknowledge_permanent_deletion": True},
                    content_type="application/json",
                )
            assert response.status_code == 409
            assert response.json()["code"] == "SCHOOL_DELETE_BLOCKED"
            assert _audit_purge_scope() == ""
            with tenant_context(bypass=True):
                assert School.objects.filter(id=school.id).exists()
                assert SchoolMembership.objects.filter(id=membership.id).exists()
                assert AuditLog.objects.filter(id=event.id).exists()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
            transaction.set_rollback(True)


@pytest.mark.django_db
def test_school_delete_requires_platform_admin(
    role_client, make_school
):
    manager, _, _ = role_client(["SCHOOL_MANAGER"])
    target = make_school("مدرسة محمية")

    response = manager.delete(
        f"/api/v1/platform/schools/{target.id}/",
        {
            "confirmation_name": target.name,
            "acknowledge_permanent_deletion": True,
        },
        content_type="application/json",
    )

    assert response.status_code == 403
    assert target.__class__.objects.filter(id=target.id).exists()
