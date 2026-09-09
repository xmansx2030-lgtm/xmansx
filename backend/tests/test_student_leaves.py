"""اختبارات استئذانات الطلاب: الصلاحيات والعزل والسجل والإلغاء والحذف النهائي."""

from datetime import timedelta

import pytest
from django.utils import timezone

from audit.models import AuditAction, AuditLog
from student_leaves.models import (
    StudentGateRelease,
    StudentLeavePermission,
    StudentLeaveStatus,
)
from students.models import StudentStatus
from students.services.purge import purge_student
from tests.excuse_env import build_env

pytestmark = pytest.mark.django_db

BASE = "/api/v1/student-leaves/"
GATE_BASE = "/api/v1/gate/student-leaves/"


@pytest.fixture
def env(role_client, make_user, make_membership):
    client, school, user = role_client(["VICE_PRINCIPAL"])
    membership = user.memberships.get(school=school)
    data = build_env(
        school=school,
        teacher_membership=make_membership(make_user("0550018100"), school, ["TEACHER"]),
        vice_membership=membership,
        prefix="51810",
    )
    data.update({"client": client, "membership": membership})
    return data


def create_leave(
    client,
    student,
    *,
    leave_date=None,
    reason="موعد طبي لدى المستشفى",
    recipient=None,
):
    payload = {
        "student_id": student.id,
        "leave_date": (leave_date or timezone.localdate()).isoformat(),
        "leave_time": "10:35",
        "reason": reason,
    }
    payload.update(recipient or {})
    return client.post(
        BASE,
        payload,
        content_type="application/json",
    )


def test_vice_records_structured_leave_in_student_history(env):
    student = env["students"][0]

    response = create_leave(env["client"], student)

    assert response.status_code == 201
    body = response.json()
    assert body["student"]["id"] == student.id
    assert body["leave_time"] == "10:35"
    assert body["weekday_label"]
    assert body["reason"] == "موعد طبي لدى المستشفى"
    assert body["grade_name"] == "الأول الثانوي"
    assert body["section_name"] == "1"
    assert body["status"] == "ACTIVE"
    assert body["recorded_by_name"]

    history = env["client"].get(f"{BASE}?student={student.id}").json()
    assert history["count"] == 1
    assert history["results"][0]["reason"] == "موعد طبي لدى المستشفى"
    assert history["summary"] == {"total": 1, "active": 1, "cancelled": 0}

    log = AuditLog.objects.get(action=AuditAction.STUDENT_LEAVE_RECORDED)
    assert log.school_id == env["school"].id
    assert "موعد طبي" not in str(log.metadata)


def test_duplicate_active_leave_same_day_rejected_but_cancelled_can_be_replaced(env):
    student = env["students"][0]
    first = create_leave(env["client"], student)
    duplicate = create_leave(env["client"], student, reason="سبب آخر")
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "ACTIVE_STUDENT_LEAVE_ALREADY_EXISTS"

    cancelled = env["client"].post(
        f"{BASE}{first.json()['id']}/cancel/",
        {"reason": "سُجل على الطالب بالخطأ"},
        content_type="application/json",
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["cancellation_reason"] == "سُجل على الطالب بالخطأ"
    assert StudentLeavePermission.objects.filter(id=first.json()["id"]).exists()

    replacement = create_leave(env["client"], student, reason="موعد جديد")
    assert replacement.status_code == 201
    assert StudentLeavePermission.objects.filter(student=student).count() == 2


def test_leave_rejects_future_date_and_inactive_student(env):
    future = create_leave(
        env["client"],
        env["students"][0],
        leave_date=timezone.localdate() + timedelta(days=1),
    )
    assert future.status_code == 400

    student = env["students"][1]
    student.status = StudentStatus.TRANSFERRED
    student.save(update_fields=["status"])
    inactive = create_leave(env["client"], student)
    assert inactive.status_code == 409
    assert inactive.json()["code"] == "ACTIVE_STUDENT_REQUIRED"


def test_manager_and_vice_allowed_other_roles_denied(env, role_client, make_school):
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=env["school"])
    assert create_leave(manager, env["students"][0]).status_code == 201

    other_student = env["students"][1]
    for role in ("COUNSELOR", "TEACHER"):
        client, _, _ = role_client([role], school=env["school"])
        assert create_leave(client, other_student).status_code == 403
        assert client.get(BASE).status_code == 403


def test_tenant_isolation_hides_foreign_students_and_leaves(
    env, role_client, make_user, make_membership
):
    create_leave(env["client"], env["students"][0])
    other_client, other_school, other_user = role_client(["VICE_PRINCIPAL"])
    other_env = build_env(
        school=other_school,
        teacher_membership=make_membership(make_user("0550018200"), other_school, ["TEACHER"]),
        vice_membership=other_user.memberships.get(school=other_school),
        prefix="51820",
    )
    assert create_leave(other_client, env["students"][1]).status_code == 404
    assert other_client.get(BASE).json()["count"] == 0
    assert create_leave(other_client, other_env["students"][0]).status_code == 201
    assert env["client"].get(BASE).json()["count"] == 1


def test_student_purge_deletes_leave_records(env):
    student = env["students"][0]
    create_leave(env["client"], student)
    student.status = StudentStatus.GRADUATED
    student.save(update_fields=["status"])

    purge_student(student)

    assert not StudentLeavePermission.objects.filter(student_id=student.id).exists()


def test_cancelled_status_is_persisted_with_actor_and_time(env):
    response = create_leave(env["client"], env["students"][0])
    leave_id = response.json()["id"]
    env["client"].post(
        f"{BASE}{leave_id}/cancel/",
        {"reason": "لم يغادر الطالب المدرسة"},
        content_type="application/json",
    )
    leave = StudentLeavePermission.objects.get(id=leave_id)
    assert leave.status == StudentLeaveStatus.CANCELLED
    assert leave.cancelled_by_membership_id == env["membership"].id
    assert leave.cancelled_at is not None
    assert AuditLog.objects.filter(action=AuditAction.STUDENT_LEAVE_CANCELLED).exists()


def test_leave_create_and_cancel_invalidate_dashboard_cache(
    env, django_capture_on_commit_callbacks
):
    from school_dashboard.cache import build_key

    def dashboard_key():
        return build_key(school_id=env["school"].id, section="today", parts={"roles": ["VP"]})

    before = dashboard_key()
    with django_capture_on_commit_callbacks(execute=True):
        created = create_leave(env["client"], env["students"][0])
    after_create = dashboard_key()
    assert after_create != before

    with django_capture_on_commit_callbacks(execute=True):
        cancelled = env["client"].post(
            f"{BASE}{created.json()['id']}/cancel/",
            {"reason": "لم يغادر الطالب المدرسة"},
            content_type="application/json",
        )
    assert cancelled.status_code == 200
    assert dashboard_key() != after_create


def test_all_gate_guards_share_today_queue_and_first_confirmation_wins(env, role_client):
    created = create_leave(
        env["client"],
        env["students"][0],
        recipient={
            "recipient_name": "أحمد عبدالله",
            "recipient_relationship": "والد",
            "recipient_id_last4": "4321",
        },
    )
    leave_id = created.json()["id"]
    first_guard, _, _ = role_client(["GATE_GUARD"], school=env["school"])
    second_guard, _, _ = role_client(["GATE_GUARD"], school=env["school"])

    queue = first_guard.get(GATE_BASE)
    assert queue.status_code == 200
    body = queue.json()
    assert body["summary"] == {"total": 1, "pending": 1, "released": 0}
    row = body["results"][0]
    assert row["student"]["student_number"] == env["students"][0].student_number
    assert row["grade_name"] == "الأول الثانوي"
    assert row["section_name"] == "1"
    assert row["recipient_name"] == "أحمد عبدالله"
    assert row["recipient_relationship"] == "والد"
    assert row["recipient_id_last4"] == "4321"
    assert "reason" not in row
    assert "national_id_masked" not in row["student"]

    confirmed = first_guard.post(f"{GATE_BASE}{leave_id}/release/")
    assert confirmed.status_code == 201
    assert confirmed.json()["gate_release"]["released_at"]
    assert StudentGateRelease.objects.filter(leave_permission_id=leave_id).count() == 1

    shared = second_guard.get(GATE_BASE).json()
    assert shared["summary"] == {"total": 1, "pending": 0, "released": 1}
    assert shared["results"][0]["gate_release"]["released_by_name"]

    duplicate = second_guard.post(f"{GATE_BASE}{leave_id}/release/")
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "STUDENT_ALREADY_RELEASED"
    assert StudentGateRelease.objects.filter(leave_permission_id=leave_id).count() == 1
    assert AuditLog.objects.filter(
        action=AuditAction.STUDENT_GATE_RELEASE_CONFIRMED,
        target_id=str(StudentGateRelease.objects.get(leave_permission_id=leave_id).id),
    ).exists()


def test_gate_scope_permissions_search_and_tenant_isolation(env, role_client):
    env["students"][0].student_number = "GATE-1001"
    env["students"][0].save(update_fields=["student_number", "updated_at"])
    create_leave(env["client"], env["students"][0])
    guard, _, _ = role_client(["GATE_GUARD"], school=env["school"])
    teacher, _, _ = role_client(["TEACHER"], school=env["school"])
    foreign_guard, _, _ = role_client(["GATE_GUARD"])

    assert (
        guard.get(f"{GATE_BASE}?search={env['students'][0].student_number}").json()["summary"][
            "total"
        ]
        == 1
    )
    assert guard.get(f"{GATE_BASE}?search=غير-موجود").json()["results"] == []
    assert teacher.get(GATE_BASE).status_code == 403
    assert teacher.post(f"{GATE_BASE}1/release/").status_code == 403
    assert foreign_guard.get(GATE_BASE).json()["results"] == []


def test_recipient_last_four_validation_and_release_prevents_cancellation(env, role_client):
    invalid = create_leave(
        env["client"],
        env["students"][0],
        recipient={"recipient_id_last4": "12A"},
    )
    assert invalid.status_code == 400

    created = create_leave(
        env["client"],
        env["students"][0],
        recipient={"recipient_id_last4": "٠١٢٣"},
    )
    assert created.json()["recipient_id_last4"] == "0123"
    guard, _, _ = role_client(["GATE_GUARD"], school=env["school"])
    assert guard.post(f"{GATE_BASE}{created.json()['id']}/release/").status_code == 201

    cancelled = env["client"].post(
        f"{BASE}{created.json()['id']}/cancel/",
        {"reason": "محاولة إلغاء بعد الخروج"},
        content_type="application/json",
    )
    assert cancelled.status_code == 409
    assert cancelled.json()["code"] == "STUDENT_LEAVE_ALREADY_RELEASED"
