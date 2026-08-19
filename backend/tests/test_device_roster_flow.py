"""تدقيق مستقل م8.6 — اختبارات التدفق الناقصة: الاعتماد/‏Stale بنوعيه/idempotency/
الإعادة/تعدد الأجهزة/الأدوار/عدم إرسال PII للجهاز."""

import pytest

from devices.models import (
    AttendanceDevice,
    DeviceRosterSyncItemStatus,
    DeviceRosterSyncJob,
    DeviceRosterSyncStatus,
    IdentityStatus,
    StudentDeviceIdentity,
)
from devices.services.bridge import create_bridge
from devices.services.roster import (
    _stable_external_user_id,
    command_payload,
    compare_device_roster,
    save_analysis,
)
from memberships.models import SchoolMembership
from students.models import StudentStatus
from tests.test_students_api import _enroll, _make_student


def _membership(user, school):
    return SchoolMembership.objects.get(user=user, school=school)


def _make_job(school, device, membership, device_users):
    job = DeviceRosterSyncJob.objects.create(
        school=school, device=device, created_by_membership=membership,
        status=DeviceRosterSyncStatus.ANALYZING,
    )
    return save_analysis(job=job, device_users=device_users)


@pytest.fixture
def env(role_client):
    client, school, user = role_client(["SCHOOL_MANAGER"])
    student = _make_student(school, "1012345678", "طالب نشط")
    _enroll(school, student)
    device = AttendanceDevice.objects.create(school=school, name="بوابة")
    bridge, token = create_bridge(school=school, name="جسر", actor=None)
    return {
        "client": client, "school": school,
        "membership": _membership(user, school),
        "student": student, "device": device, "bridge": bridge, "token": token,
    }


@pytest.mark.django_db
def test_approve_blocks_stale_saas_roster(env):
    """تغير بيانات الطلاب بعد المعاينة → الاعتماد يرفض 409 والمهمة STALE."""
    job = _make_job(env["school"], env["device"], env["membership"], [])
    assert job.status == DeviceRosterSyncStatus.READY_FOR_REVIEW
    env["student"].status = StudentStatus.GRADUATED
    env["student"].save(update_fields=["status"])

    response = env["client"].post(f"/api/v1/device-roster-syncs/{job.id}/approve/")
    assert response.status_code == 409
    assert response.json()["code"] == "DEVICE_ROSTER_PREVIEW_STALE"
    job.refresh_from_db()
    assert job.status == DeviceRosterSyncStatus.STALE


@pytest.mark.django_db
def test_stale_device_roster_blocks_execution(env, client):
    """تغير قائمة الجهاز خارجيًا بعد الاعتماد → لا تنفيذ أعمى (409 + STALE)."""
    job = _make_job(env["school"], env["device"], env["membership"], [])
    assert env["client"].post(
        f"/api/v1/device-roster-syncs/{job.id}/approve/"
    ).status_code == 200
    response = client.post(
        "/api/v1/bridge/roster/read/",
        {
            "job_id": job.id,
            "device_id": env["device"].id,
            "users": [{"external_user_id": "external-x", "display_name": "دخيل"}],
            "device_roster_version": "changed-externally",
        },
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {env['token']}",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "DEVICE_ROSTER_PREVIEW_STALE"
    job.refresh_from_db()
    assert job.status == DeviceRosterSyncStatus.STALE


@pytest.mark.django_db
def test_command_result_idempotent_on_lost_ack(env, client):
    """فقد الـACK وإعادة إرسال النتيجة نفسها لا يكرر الأثر (idempotent)."""
    job = _make_job(env["school"], env["device"], env["membership"], [])
    env["client"].post(f"/api/v1/device-roster-syncs/{job.id}/approve/")
    item = job.items.get()
    job.status = DeviceRosterSyncStatus.RUNNING
    job.save(update_fields=["status"])
    item.status = DeviceRosterSyncItemStatus.RUNNING
    item.save(update_fields=["status"])

    payload = {
        "job_id": job.id, "item_id": item.id, "command_id": item.command_id,
        "result": "SUCCEEDED", "error_code": "",
    }
    for _ in range(2):  # الإرسال الثاني = ACK مفقود ثم retry
        response = client.post(
            "/api/v1/bridge/roster/command-result/",
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {env['token']}",
        )
        assert response.status_code == 200
    item.refresh_from_db()
    assert item.status == DeviceRosterSyncItemStatus.SUCCEEDED
    assert item.attempts == 1  # الإعادة لم تعد الحساب
    identities = StudentDeviceIdentity.objects.filter(
        device=env["device"], external_user_id=item.external_user_id
    )
    assert identities.count() == 1
    assert identities.get().status == IdentityStatus.MATCHED


@pytest.mark.django_db
def test_partial_failure_then_retry_requeues_failed_only(env, client):
    second = _make_student(env["school"], "1012345679", "طالب ثانٍ")
    _enroll(env["school"], second, code="2")
    job = _make_job(env["school"], env["device"], env["membership"], [])
    assert job.create_count == 2
    env["client"].post(f"/api/v1/device-roster-syncs/{job.id}/approve/")
    job.status = DeviceRosterSyncStatus.RUNNING
    job.save(update_fields=["status"])
    items = list(job.items.order_by("id"))
    for item, result in zip(items, ["SUCCEEDED", "FAILED_RETRYABLE"], strict=True):
        item.status = DeviceRosterSyncItemStatus.RUNNING
        item.save(update_fields=["status"])
        client.post(
            "/api/v1/bridge/roster/command-result/",
            {
                "job_id": job.id, "item_id": item.id, "command_id": item.command_id,
                "result": result, "error_code": "TIMEOUT" if result != "SUCCEEDED" else "",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {env['token']}",
        )
    job.refresh_from_db()
    assert job.status == DeviceRosterSyncStatus.PARTIALLY_FAILED

    response = env["client"].post(f"/api/v1/device-roster-syncs/{job.id}/retry/")
    assert response.status_code == 200
    job.refresh_from_db()
    assert job.status == DeviceRosterSyncStatus.APPROVED
    statuses = sorted(job.items.values_list("status", flat=True))
    assert statuses == ["PENDING", "SUCCEEDED"]  # الناجح لا يعاد — الفاشل فقط

    # مهمة غير جزئية الفشل لا تقبل الإعادة
    assert env["client"].post(
        f"/api/v1/device-roster-syncs/{job.id}/retry/"
    ).status_code == 409


@pytest.mark.django_db
def test_multi_device_independence(env):
    """طالب MATCHED على جهاز A يبقى TO_CREATE على جهاز B — كل جهاز مستقل."""
    device_b = AttendanceDevice.objects.create(school=env["school"], name="بوابة ب")
    external_id = _stable_external_user_id(env["student"])
    StudentDeviceIdentity.objects.create(
        school=env["school"], device=env["device"], student=env["student"],
        external_user_id=external_id, display_name=env["student"].full_name,
        status=IdentityStatus.MATCHED,
    )
    result_a = compare_device_roster(
        school=env["school"], device=env["device"],
        device_users=[{"external_user_id": external_id,
                       "display_name": env["student"].full_name}],
    )
    result_b = compare_device_roster(
        school=env["school"], device=device_b, device_users=[]
    )
    assert result_a["summary"]["matched_count"] == 1
    assert result_a["summary"]["create_count"] == 0
    assert result_b["summary"]["create_count"] == 1
    assert not StudentDeviceIdentity.objects.filter(device=device_b).exists()


@pytest.mark.django_db
def test_active_student_on_device_is_never_delete(env):
    """‏ACTIVE بقيد فعال = لا TO_DELETE أبدًا — الغياب عن آخر ملف نور لا يغير ذلك،
    وTRANSFERRED هو ما يجعله مرشح إزالة (وليس حذفًا من SaaS)."""
    external_id = _stable_external_user_id(env["student"])
    StudentDeviceIdentity.objects.create(
        school=env["school"], device=env["device"], student=env["student"],
        external_user_id=external_id, display_name=env["student"].full_name,
        status=IdentityStatus.MATCHED,
    )
    device_users = [
        {"external_user_id": external_id, "display_name": env["student"].full_name}
    ]
    result = compare_device_roster(
        school=env["school"], device=env["device"], device_users=device_users
    )
    assert result["summary"]["delete_count"] == 0
    assert result["summary"]["matched_count"] == 1

    env["student"].status = StudentStatus.TRANSFERRED
    env["student"].save(update_fields=["status"])
    result = compare_device_roster(
        school=env["school"], device=env["device"], device_users=device_users
    )
    assert result["summary"]["delete_count"] == 1
    # الإزالة من الجهاز لا تعني حذف بيانات SaaS — الطالب باقٍ
    env["student"].refresh_from_db()
    assert env["student"].full_name == "طالب نشط"


@pytest.mark.django_db
def test_roster_roles_and_tenant_isolation(env, role_client):
    job = _make_job(env["school"], env["device"], env["membership"], [])
    vice, _, _ = role_client(["VICE_PRINCIPAL"], school=env["school"])
    teacher, _, _ = role_client(["TEACHER"], school=env["school"])
    foreign, _, _ = role_client(["SCHOOL_MANAGER"])  # مدرسة أخرى

    assert vice.get(f"/api/v1/device-roster-syncs/{job.id}/").status_code == 200
    assert vice.post(f"/api/v1/device-roster-syncs/{job.id}/approve/").status_code == 403
    assert teacher.get(f"/api/v1/device-roster-syncs/{job.id}/").status_code == 403
    assert foreign.get(f"/api/v1/device-roster-syncs/{job.id}/").status_code == 404
    assert foreign.post(
        f"/api/v1/devices/{env['device'].id}/roster-sync/analyze/"
    ).status_code == 404


@pytest.mark.django_db
def test_device_commands_carry_no_student_pii(env):
    """لا رقم هوية للجهاز إطلاقًا: المعرف مشتق داخلي والاسم فقط للعرض."""
    job = _make_job(env["school"], env["device"], env["membership"], [])
    item = job.items.get()
    item.command_id = "cmd-1"
    payload = command_payload(item)
    assert set(payload) == {
        "command_id", "job_id", "item_id", "device_id",
        "action", "external_user_id", "display_name",
    }
    assert "1012345678" not in str(payload)
    assert payload["external_user_id"].startswith("stu-")
    assert "1012345678" not in str(item.safe_after_snapshot)
    assert "1012345678" not in str(item.safe_before_snapshot)
