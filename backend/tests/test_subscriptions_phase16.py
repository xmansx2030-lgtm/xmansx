from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from devices.models import AttendanceDevice
from excuses.models import AbsenceExcuse
from excuses.services import excuses as excuse_service
from memberships.models import SchoolRole
from students.models import Student, StudentStatus
from subscriptions.access import BLOCKED, FULL, READ_ONLY, get_school_access_mode
from subscriptions.entitlements import get_limit, require_capacity
from subscriptions.models import (
    EntitlementKey,
    SaaSPlan,
    SchoolSubscription,
    SubscriptionEvent,
    SubscriptionEventType,
    SubscriptionStatus,
)
from subscriptions.services import plans as plan_service
from subscriptions.services import subscriptions as subscription_service


@pytest.fixture
def platform_admin(make_user):
    return make_user("0550001600", is_staff=True, is_superuser=True)


def create_plan(
    actor,
    *,
    code="basic",
    students=100,
    staff=10,
    devices=2,
    storage=10,
    counseling=True,
):
    return plan_service.create_plan(
        actor=actor,
        code=code,
        name_ar=f"باقة {code}",
        entitlements={
            EntitlementKey.MAX_STUDENTS: students,
            EntitlementKey.MAX_STAFF: staff,
            EntitlementKey.MAX_DEVICES: devices,
            EntitlementKey.MAX_STORAGE_GB: storage,
            EntitlementKey.COUNSELING: counseling,
        },
    )


@pytest.mark.django_db
def test_subscription_snapshot_survives_plan_edit(make_school, platform_admin):
    school = make_school()
    plan = create_plan(platform_admin, students=100)

    subscription_service.activate(school=school, plan_id=plan.id, actor=platform_admin)
    assert get_limit(school, EntitlementKey.MAX_STUDENTS) == 100

    plan_service.update_plan(
        plan=plan,
        actor=platform_admin,
        entitlements={EntitlementKey.MAX_STUDENTS: 500},
    )

    assert get_limit(school, EntitlementKey.MAX_STUDENTS) == 100


@pytest.mark.django_db
def test_downgrade_blocks_new_students_without_deleting_existing(make_school, platform_admin):
    school = make_school()
    pro = create_plan(platform_admin, code="pro", students=500)
    basic = create_plan(platform_admin, code="starter", students=100)
    subscription_service.activate(school=school, plan_id=pro.id, actor=platform_admin)
    Student.objects.bulk_create(
        [
            Student(
                school=school,
                national_id_encrypted=f"enc-{idx}",
                national_id_lookup_hash=f"hash-{idx}",
                national_id_masked="**********",
                student_number=f"S{idx}",
                full_name=f"طالب {idx}",
                status=StudentStatus.ACTIVE,
            )
            for idx in range(120)
        ]
    )

    subscription_service.change_plan(
        school=school, plan_id=basic.id, actor=platform_admin, reason="downgrade"
    )

    assert Student.objects.filter(school=school).count() == 120
    with pytest.raises(Exception) as exc:
        require_capacity(
            school,
            EntitlementKey.MAX_STUDENTS,
            current=Student.objects.filter(school=school, status=StudentStatus.ACTIVE).count(),
        )
    assert getattr(exc.value, "code", "") == "STUDENT_LIMIT_EXCEEDED"


@pytest.mark.django_db
def test_expired_and_suspended_access_modes_preserve_data(make_school, platform_admin):
    school = make_school()
    plan = create_plan(platform_admin)
    subscription = subscription_service.activate(
        school=school, plan_id=plan.id, actor=platform_admin
    )
    Student.objects.create(
        school=school,
        national_id_encrypted="enc",
        national_id_lookup_hash="hash",
        national_id_masked="**********",
        student_number="S1",
        full_name="طالب",
    )

    now = timezone.now()
    subscription.starts_at = now - timedelta(days=30)
    subscription.ends_at = now - timedelta(days=1)
    subscription.save(update_fields=["starts_at", "ends_at", "updated_at"])

    assert get_school_access_mode(school) == READ_ONLY
    assert Student.objects.filter(school=school).count() == 1

    subscription.status = SubscriptionStatus.SUSPENDED
    subscription.suspended_at = timezone.now()
    subscription.suspension_reason = "إيقاف إداري"
    subscription.save(update_fields=["status", "suspended_at", "suspension_reason", "updated_at"])

    assert get_school_access_mode(school) == BLOCKED
    assert Student.objects.filter(school=school).count() == 1


@pytest.mark.django_db
def test_device_limit_after_downgrade_preserves_existing_devices(
    role_client, platform_admin
):
    client, school, _user = role_client([SchoolRole.SCHOOL_MANAGER])
    pro = create_plan(platform_admin, code="devices-pro", devices=5)
    starter = create_plan(platform_admin, code="devices-starter", devices=2)
    subscription_service.activate(school=school, plan_id=pro.id, actor=platform_admin)
    for idx in range(4):
        AttendanceDevice.objects.create(
            school=school,
            name=f"جهاز {idx}",
            vendor="ZKTeco",
            serial_number=f"SN-{idx}",
        )

    subscription_service.change_plan(
        school=school, plan_id=starter.id, actor=platform_admin, reason="downgrade"
    )

    response = client.post(
        "/api/v1/devices/",
        {
            "name": "جهاز جديد",
            "vendor": "ZKTeco",
            "serial_number": "SN-new",
            "connection_type": "LAN",
        },
        content_type="application/json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "DEVICE_LIMIT_EXCEEDED"
    assert AttendanceDevice.objects.filter(school=school).count() == 4


@pytest.mark.django_db
def test_no_subscription_legacy_school_remains_full_access(make_school):
    school = make_school()
    assert get_school_access_mode(school) == FULL
    assert SchoolSubscription.objects.filter(school=school).count() == 0
    assert SaaSPlan.objects.count() == 0


@pytest.mark.django_db
def test_activate_after_effective_expiry_closes_stale_active_subscription(
    make_school, platform_admin
):
    school = make_school()
    old_plan = create_plan(platform_admin, code="old-plan", students=100)
    new_plan = create_plan(platform_admin, code="new-plan", students=500)
    old_subscription = subscription_service.activate(
        school=school, plan_id=old_plan.id, actor=platform_admin
    )
    now = timezone.now()
    old_subscription.starts_at = now - timedelta(days=30)
    old_subscription.ends_at = now - timedelta(days=1)
    old_subscription.save(update_fields=["starts_at", "ends_at", "updated_at"])

    new_subscription = subscription_service.activate(
        school=school, plan_id=new_plan.id, actor=platform_admin
    )

    old_subscription.refresh_from_db()
    assert old_subscription.status == SubscriptionStatus.EXPIRED
    assert new_subscription.status == SubscriptionStatus.ACTIVE
    assert get_limit(school, EntitlementKey.MAX_STUDENTS) == 500


@pytest.mark.django_db
def test_transition_sync_is_idempotent_for_grace(make_school, platform_admin):
    school = make_school()
    plan = create_plan(platform_admin)
    subscription = subscription_service.activate(
        school=school, plan_id=plan.id, actor=platform_admin
    )
    now = timezone.now()
    subscription.starts_at = now - timedelta(days=30)
    subscription.ends_at = now - timedelta(days=1)
    subscription.grace_ends_at = now + timedelta(days=6)
    subscription.save(
        update_fields=["starts_at", "ends_at", "grace_ends_at", "updated_at"]
    )

    assert subscription_service.sync_expirations(now=now) == {"expired": 0, "grace": 1}
    assert subscription_service.sync_expirations(now=now) == {"expired": 0, "grace": 0}
    assert (
        SubscriptionEvent.objects.filter(
            subscription=subscription,
            event_type=SubscriptionEventType.GRACE_STARTED,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_storage_limit_blocks_new_excuse_attachment_without_deleting_existing(
    make_school, make_user, make_membership, platform_admin
):
    school = make_school()
    plan = create_plan(platform_admin, storage=0)
    subscription_service.activate(school=school, plan_id=plan.id, actor=platform_admin)
    manager = make_user("0550001601")
    membership = make_membership(manager, school, [SchoolRole.SCHOOL_MANAGER])
    student = Student.objects.create(
        school=school,
        national_id_encrypted="enc-storage",
        national_id_lookup_hash="hash-storage",
        national_id_masked="**********",
        student_number="ST-storage",
        full_name="طالب التخزين",
    )
    excuse = AbsenceExcuse.objects.create(
        school=school,
        student=student,
        reason_type="MEDICAL",
        notes="",
        recorded_by_membership=membership,
        recorded_at=timezone.now(),
    )
    uploaded = SimpleUploadedFile(
        "proof.pdf",
        b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF",
        content_type="application/pdf",
    )

    with pytest.raises(Exception) as exc:
        excuse_service.add_attachment(
            excuse=excuse,
            school=school,
            membership=membership,
            uploaded_file=uploaded,
        )

    assert getattr(exc.value, "code", "") == "STORAGE_LIMIT_EXCEEDED"
    assert excuse.attachments.count() == 0


@pytest.mark.django_db
def test_counseling_feature_gate_blocks_backend_endpoint(role_client, platform_admin):
    client, school, _user = role_client([SchoolRole.COUNSELOR])
    plan = create_plan(platform_admin, code="no-counseling", counseling=False)
    subscription_service.activate(school=school, plan_id=plan.id, actor=platform_admin)

    response = client.get("/api/v1/counselor/dashboard/")

    assert response.status_code == 403
    assert response.json()["code"] == "FEATURE_NOT_INCLUDED_IN_PLAN"


@pytest.mark.django_db
def test_platform_admin_permissions_isolate_platform_api(
    client, role_client, platform_admin
):
    client.force_login(platform_admin)
    assert client.get("/api/v1/platform/overview/").status_code == 200

    manager_client, _school, _user = role_client([SchoolRole.SCHOOL_MANAGER])
    response = manager_client.get("/api/v1/platform/overview/")

    assert response.status_code == 403
