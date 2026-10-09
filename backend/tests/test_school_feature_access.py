"""Per-school paid-feature controls: real HTTP, tenant RLS and pre-send gates."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest
from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.test import Client
from django.utils import timezone

from audit.models import AuditLog
from common.errors import ApiError
from devices.models import DeviceEvent
from devices.services.bridge import authenticate_bridge
from parents.models import GuardianStudentRelation
from platform_team.models import PlatformStaffMembership
from school_sms.models import AbsenceSmsNotice, AbsenceSmsStatus
from school_sms.tasks import send_absence_notice
from schools.models import School
from subscriptions.entitlements import MANAGED_FEATURES, has_entitlement, school_feature_access
from subscriptions.models import SubscriptionEntitlement
from subscriptions.services import subscriptions as contracts
from tests.attendance_helpers import setup_attendance_env
from tests.test_devices_morning import env as _device_env
from tests.test_parent_email_credential_boundary import restricted_role
from tests.test_parent_family_invitations import family_env as _family_env
from tests.test_parent_family_invitations import invite
from tests.test_parent_portal import activate
from tests.test_parent_portal import portal_env as _portal_env
from tests.test_school_sms import _absence
from tests.test_subscriptions_phase16 import create_plan

pytestmark = pytest.mark.django_db(transaction=True)
device_env = _device_env
family_env = _family_env
portal_env = _portal_env


@pytest.fixture
def platform(make_user):
    owner = make_user("0551721001", is_superuser=True, is_staff=True)
    client = Client()
    client.force_login(owner)
    return client, owner


def toggle(client, school, feature, enabled):
    return client.patch(
        f"/api/v1/platform/schools/{school.pk}/features/",
        {"feature": feature, "enabled": enabled},
        content_type="application/json",
    )


def assert_locked(response, key):
    assert response.status_code == 403, response.content
    error = response.json()
    assert error["code"] == "FEATURE_NOT_INCLUDED_IN_PLAN"
    assert error["details"] == {"feature": key, "subscription_required": True}


def test_new_school_defaults_are_independent_and_existing_school_is_preserved(make_school):
    school = School.objects.create(name="مدرسة جديدة", slug="new-features")
    peer = School.objects.create(name="مدرسة جديدة أخرى", slug="new-peer")
    assert school.feature_access == dict.fromkeys(MANAGED_FEATURES, False)
    school.feature_access["PARENT_PORTAL"] = True
    assert peer.feature_access["PARENT_PORTAL"] is False
    legacy = make_school()
    assert school_feature_access(legacy) == dict.fromkeys(MANAGED_FEATURES, True)


@pytest.mark.parametrize("key", MANAGED_FEATURES)
def test_platform_toggle_is_audited_scoped_and_visible_on_next_school_request(
    platform, role_client, make_school, key
):
    school, peer = make_school(), make_school()
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school)
    owner_client, owner = platform
    with restricted_role():
        response = toggle(owner_client, school, key, False)
        assert response.status_code == 200, response.content
        assert response.json()["features"][key] is False
        assert (
            manager.get("/api/v1/school/features/", {"school_id": peer.pk}).json()
            == response.json()
        )
        assert manager.get("/api/v1/auth/me/").json()["school_features"][key] is False
        assert toggle(owner_client, school, key, False).status_code == 200
    school.refresh_from_db()
    peer.refresh_from_db()
    assert school.feature_access == {key: False}
    assert peer.feature_access == {}
    logs = AuditLog.objects.filter(action="SCHOOL_FEATURE_ACCESS_CHANGED", school=school)
    assert logs.count() == 1
    assert logs.get().actor_id == owner.id
    assert logs.get().metadata == {"feature": key, "before": True, "enabled": False}
    assert toggle(owner_client, school, key, True).status_code == 200
    assert manager.get("/api/v1/auth/me/").json()["school_features"][key] is True


@pytest.mark.parametrize(
    "role,allowed",
    [("SUPPORT", False), ("AUDITOR", False), ("BILLING", True), ("OPERATIONS_MANAGER", True)],
)
def test_only_subscription_managers_can_change_features(make_school, make_user, role, allowed):
    school = make_school()
    user = make_user("0551721002")
    PlatformStaffMembership.objects.create(user=user, role=role)
    client = Client()
    client.force_login(user)
    with restricted_role():
        assert client.get(f"/api/v1/platform/schools/{school.pk}/features/").status_code == 200
        assert toggle(client, school, "PARENT_PORTAL", False).status_code == (
            200 if allowed else 403
        )


def test_school_manager_cannot_grant_features(role_client):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    with restricted_role():
        assert toggle(client, school, "PARENT_PORTAL", True).status_code == 403
        assert (
            client.patch(
                "/api/v1/school/features/",
                {"feature": "PARENT_PORTAL", "enabled": True},
                content_type="application/json",
            ).status_code
            == 403
        )
    school.refresh_from_db()
    assert school.feature_access == {}


@pytest.mark.parametrize(
    "data",
    [
        {"feature": "COUNSELING", "enabled": False},
        {"feature": "PARENT_PORTAL", "enabled": "true"},
        {"feature": "PARENT_PORTAL", "enabled": 1},
        {"feature": "PARENT_PORTAL", "enabled": True, "school_id": 99},
        {"feature": "PARENT_PORTAL"},
    ],
)
def test_invalid_control_payload_never_changes_school(platform, make_school, data):
    school = make_school()
    response = platform[0].patch(
        f"/api/v1/platform/schools/{school.pk}/features/", data, content_type="application/json"
    )
    assert response.status_code == 400
    school.refresh_from_db()
    assert school.feature_access == {}
    assert not AuditLog.objects.filter(action="SCHOOL_FEATURE_ACCESS_CHANGED").exists()


@pytest.mark.parametrize(
    "key,url",
    [
        ("ABSENCE_SMS", "/api/v1/school/sms/integration/"),
        ("ABSENCE_SMS", "/api/v1/school/sms/absences/preview/"),
        ("ABSENCE_SMS", "/api/v1/school/sms/absences/send/"),
        ("PARENT_PORTAL", "/api/v1/staff/parents/settings/"),
        ("PARENT_PORTAL", "/api/v1/staff/parents/registrations/"),
        ("PARENT_PORTAL", "/api/v1/staff/parents/families/"),
        ("BIOMETRIC_DEVICES", "/api/v1/devices/"),
        ("BIOMETRIC_DEVICES", "/api/v1/device-bridges/"),
        ("BIOMETRIC_DEVICES", "/api/v1/device-identities/"),
    ],
)
def test_disabled_feature_blocks_reads_and_writes_before_payload_processing(
    platform, role_client, key, url
):
    client, school, _ = role_client(["SCHOOL_MANAGER"])
    assert toggle(platform[0], school, key, False).status_code == 200
    with restricted_role():
        assert_locked(client.get(url), key)
        assert_locked(client.post(url, {}, content_type="application/json"), key)


def test_disable_bridge_stops_token_ingest_and_keeps_existing_devices(platform, device_env):
    env = device_env
    school = env["school"]
    before_seen = env["bridge"].last_seen_at
    assert toggle(platform[0], school, "BIOMETRIC_DEVICES", False).status_code == 200
    with pytest.raises(ApiError) as error:
        authenticate_bridge(env["token"])
    assert error.value.code == "FEATURE_NOT_INCLUDED_IN_PLAN"
    response = Client().post(
        "/api/v1/bridge/events/batch/",
        {"events": []},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {env['token']}",
    )
    assert_locked(response, "BIOMETRIC_DEVICES")
    assert not DeviceEvent.objects.filter(school=school).exists()
    env["bridge"].refresh_from_db()
    assert env["bridge"].last_seen_at == before_seen
    assert toggle(platform[0], school, "BIOMETRIC_DEVICES", True).status_code == 200
    assert authenticate_bridge(env["token"]).pk == env["bridge"].pk


def test_disabled_parent_portal_preserves_account_and_relations(platform, portal_env, make_school):
    env = portal_env
    relation, _, receipt = activate(env)
    peer = make_school("مدرسة أخرى للأسرة")
    peer_student = setup_attendance_env(peer, students_count=1)["students"][0]
    peer_student.full_name = "طالب المدرسة الأخرى"
    peer_student.save(update_fields=["full_name"])
    peer_relation = GuardianStudentRelation.objects.create(
        user=relation.user,
        school=peer,
        student=peer_student,
        status="ACTIVE",
        contact_bound=False,
        approved_by=platform[1],
        approved_at=timezone.now(),
    )
    assert toggle(platform[0], env["school"], "PARENT_PORTAL", False).status_code == 200
    with restricted_role():
        assert_locked(Client().get(env["url"]), "PARENT_PORTAL")
        assert_locked(
            env["parent"].post(
                "/api/v1/parent/registration/status/",
                receipt,
                content_type="application/json",
            ),
            "PARENT_PORTAL",
        )
        children = env["parent"].get("/api/v1/parent/children/")
        assert children.status_code == 200, children.content
        assert env["student"].full_name not in children.content.decode()
        assert peer_student.full_name in children.content.decode()
        assert env["parent"].get(f"/api/v1/parent/children/{peer_relation.pk}/").status_code == 200
        assert_locked(env["parent"].get(f"/api/v1/parent/children/{relation.pk}/"), "PARENT_PORTAL")
        assert env["parent"].get("/api/v1/auth/me/").status_code == 200
    assert GuardianStudentRelation.objects.get(pk=relation.pk).status == "ACTIVE"
    assert toggle(platform[0], env["school"], "PARENT_PORTAL", True).status_code == 200
    assert (
        env["student"].full_name in env["parent"].get("/api/v1/parent/children/").content.decode()
    )


def test_disabled_family_invitation_cannot_activate_account(platform, family_env):
    env = family_env
    token, invitation = invite(env)
    assert toggle(platform[0], env["school"], "PARENT_PORTAL", False).status_code == 200
    response = env["parent"].post(
        "/api/v1/parent/family-invitation/check/", {"token": token}, content_type="application/json"
    )
    assert response.status_code in {400, 409}, response.content
    invitation.refresh_from_db()
    assert invitation.consumed_at is None
    assert not GuardianStudentRelation.objects.filter(school=env["school"]).exists()


def test_queued_absence_sms_never_contacts_provider_after_disable(platform, make_school):
    school = make_school()
    student, _, day = _absence(school)
    notice = AbsenceSmsNotice.objects.create(
        school=school,
        student=student,
        attendance_date=day,
        absence_status="FULL",
        provider="DREAMS",
        recipient_hash="a" * 64,
        status=AbsenceSmsStatus.QUEUED,
    )
    assert toggle(platform[0], school, "ABSENCE_SMS", False).status_code == 200
    with restricted_role(), patch("school_sms.tasks.send_sms") as provider:
        assert send_absence_notice(notice.pk) == "failed"
        provider.assert_not_called()
    notice.refresh_from_db()
    assert notice.failure_code == "FEATURE_NOT_INCLUDED_IN_PLAN"
    assert toggle(platform[0], school, "ABSENCE_SMS", True).status_code == 200
    with patch("school_sms.tasks.send_sms") as provider:
        assert send_absence_notice(notice.pk) == "skipped"
        provider.assert_not_called()


def test_school_override_survives_plan_change_and_extension(platform, make_school):
    school = make_school()
    client, owner = platform
    first = create_plan(owner, code="features-first")
    second = create_plan(owner, code="features-second")
    contracts.activate(school=school, plan_id=first.pk, actor=owner)
    assert toggle(client, school, "PARENT_PORTAL", False).status_code == 200
    assert toggle(client, school, "BIOMETRIC_DEVICES", True).status_code == 200
    contracts.change_plan(school=school, plan_id=second.pk, actor=owner, reason="Upgrade")
    contracts.extend(school=school, extra_days=30, actor=owner, reason="Renew")
    school.refresh_from_db()
    assert not has_entitlement(school, "PARENT_PORTAL")
    assert has_entitlement(school, "BIOMETRIC_DEVICES")


def test_concurrent_toggles_preserve_both_feature_decisions(platform, make_school):
    school = make_school()
    cookies = platform[0].cookies
    barrier = Barrier(2)

    def worker(key):
        try:
            client = Client()
            client.cookies = cookies.copy()
            barrier.wait(timeout=10)
            response = toggle(client, school, key, False)
            assert response.status_code == 200, response.content
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(worker, ["PARENT_PORTAL", "ABSENCE_SMS"]))
    school.refresh_from_db()
    assert school.feature_access == {"PARENT_PORTAL": False, "ABSENCE_SMS": False}


def test_migration_preserves_existing_schools_and_disables_new_ones():
    executor = MigrationExecutor(connection)
    full_targets = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("schools", "0006_schoolsettings_absence_sms_message_template")])
        old_apps = executor.loader.project_state(
            [("schools", "0006_schoolsettings_absence_sms_message_template")]
        ).apps
        old = old_apps.get_model("schools", "School").objects.create(
            name="مدرسة قائمة قبل الترقية", slug="pre-feature-migration"
        )
        MigrationExecutor(connection).migrate(full_targets)
        retained = School.objects.get(pk=old.pk)
        assert retained.feature_access == {}
        assert school_feature_access(retained) == dict.fromkeys(MANAGED_FEATURES, True)
        created = School.objects.create(name="مدرسة بعد الترقية", slug="post-feature-migration")
        assert school_feature_access(created) == dict.fromkeys(MANAGED_FEATURES, False)
    finally:
        MigrationExecutor(connection).migrate(full_targets)


def test_explicit_enable_overrides_plan_feature_but_preserves_subscription_lock(
    platform, role_client
):
    manager, school, _ = role_client(["SCHOOL_MANAGER"])
    client, owner = platform
    plan = create_plan(owner, code="limited-features")
    subscription = contracts.activate(school=school, plan_id=plan.pk, actor=owner)
    SubscriptionEntitlement.objects.create(
        subscription=subscription, key="BIOMETRIC_DEVICES", is_enabled=False
    )
    assert not has_entitlement(school, "BIOMETRIC_DEVICES")
    assert toggle(client, school, "BIOMETRIC_DEVICES", True).status_code == 200
    school.refresh_from_db()
    assert has_entitlement(school, "BIOMETRIC_DEVICES")
    assert manager.get("/api/v1/devices/").status_code == 200
    contracts.suspend(school=school, actor=owner, reason="Subscription lock")
    response = manager.post("/api/v1/devices/", {}, content_type="application/json")
    assert response.status_code == 403
    assert response.json()["code"] == "SCHOOL_SUSPENDED"


def test_anonymous_cannot_read_or_change_feature_controls(make_school):
    school = make_school()
    response = toggle(Client(), school, "PARENT_PORTAL", True)
    assert response.status_code == 403
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert Client().get("/api/v1/school/features/").status_code == 403
