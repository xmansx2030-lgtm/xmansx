import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from attendance.models import AttendanceMark, AttendanceSession
from audit.models import AuditAction, AuditLog
from memberships.models import SchoolMembership
from schools.services.settings import get_or_create_settings
from subscriptions.services.school_purge import school_scoped_models_in_delete_order
from tests.attendance_helpers import setup_attendance_env


@pytest.mark.django_db
def test_platform_admin_permanently_deletes_school_data_and_only_orphan_accounts(
    client, make_membership, make_school, make_user, settings, tmp_path
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
    assert school.__class__.objects.filter(id=school.id).exists()

    response = client.delete(
        f"/api/v1/platform/schools/{school.id}/",
        {
            "confirmation_name": school.name,
            "acknowledge_permanent_deletion": True,
        },
        content_type="application/json",
    )

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
    assert SchoolMembership.objects.filter(user=shared_user, school=other_school).exists()
    deletion_log = AuditLog.objects.get(
        action=AuditAction.PLATFORM_SCHOOL_PERMANENTLY_DELETED,
        target_id=str(school.id),
    )
    assert deletion_log.school_id is None
    assert deletion_log.actor == admin


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
