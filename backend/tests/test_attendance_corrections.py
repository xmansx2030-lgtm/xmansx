"""Correction contracts, including independent PostgreSQL connections and stale forms."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections, connections

from attendance.models import (
    AttendanceChange,
    AttendanceMark,
    AttendanceSession,
    DailyAttendanceSummary,
)
from audit.models import AuditAction, AuditLog
from tests.attendance_helpers import setup_attendance_env


@pytest.fixture
def correction_env(role_client):
    teacher, school, user = role_client(["TEACHER"])
    env = setup_attendance_env(school)
    env.update(school=school, teacher=teacher, teacher_user=user)
    started = teacher.post(
        "/api/v1/attendance/sessions/start/",
        {"section_id": env["section"].id},
        content_type="application/json",
    )
    assert started.status_code == 201
    session_id = started.json()["id"]
    submitted = teacher.post(
        f"/api/v1/attendance/sessions/{session_id}/submit/",
        {"marks": [absent(student.id) for student in env["students"][:2]]},
        content_type="application/json",
    )
    assert submitted.status_code == 200
    env.update(session=submitted.json(), url=f"/api/v1/attendance/sessions/{session_id}/")
    return env


def absent(student_id):
    return {"student_id": student_id, "status": "ABSENT"}


def patch(client, url, body):
    return client.patch(url, body, content_type="application/json")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "roles", [["SCHOOL_MANAGER"], ["VICE_PRINCIPAL"], ["SCHOOL_MANAGER", "TEACHER"]]
)
@pytest.mark.parametrize("reason", ["", "   "])
def test_administrative_class_correction_requires_reason(
    correction_env, role_client, roles, reason
):
    env = correction_env
    client, _, _ = role_client(roles, school=env["school"])
    result = patch(
        client,
        env["url"],
        {
            "marks": [],
            "reason": reason,
            "expected_updated_at": env["session"]["updated_at"],
        },
    )
    assert result.status_code == 400
    assert result.json()["code"] == "VALIDATION_ERROR"
    assert AttendanceMark.objects.filter(session_id=env["session"]["id"]).count() == 2
    assert not AttendanceChange.objects.exists()
    assert not AuditLog.objects.filter(action=AuditAction.ATTENDANCE_EDITED).exists()


@pytest.mark.django_db
def test_teacher_reason_remains_optional_and_noop_keeps_version(correction_env):
    env = correction_env
    unchanged = patch(
        env["teacher"],
        env["url"],
        {
            "marks": env["session"]["marks"],
            "expected_updated_at": env["session"]["updated_at"],
        },
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["updated_at"] == env["session"]["updated_at"]
    assert not AttendanceChange.objects.exists()
    changed = patch(
        env["teacher"],
        env["url"],
        {
            "marks": [],
            "expected_updated_at": env["session"]["updated_at"],
        },
    )
    assert changed.status_code == 200
    assert changed.json()["updated_at"] != env["session"]["updated_at"]
    assert AttendanceChange.objects.count() == 2


@pytest.mark.django_db
def test_corrections_without_version_are_rejected(correction_env, role_client):
    env = correction_env
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=env["school"])
    student_id = env["students"][0].id
    for url, body in (
        (env["url"], {"marks": [], "reason": "تصحيح إداري"}),
        (f"{env['url']}students/{student_id}/", {"status": "PRESENT", "reason": "تصحيح إداري"}),
    ):
        result = patch(manager, url, body)
        assert result.status_code == 400
        assert "expected_updated_at" in result.json()["details"]
    assert not AttendanceChange.objects.exists()


@pytest.mark.django_db
def test_class_and_student_corrections_share_version_and_reject_stale_forms(
    correction_env,
    role_client,
):
    env = correction_env
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=env["school"])
    student_id = env["students"][0].id
    url = f"{env['url']}students/{student_id}/"
    detail = manager.get(
        f"/api/v1/students/{student_id}/attendance-days/{env['session']['attendance_date']}/"
    ).json()
    assert detail["periods"][0]["session_updated_at"] == env["session"]["updated_at"]
    # The class correction changes a different student's mark while the form is open.
    class_edit = patch(
        manager,
        env["url"],
        {
            "marks": [absent(student_id)],
            "reason": "تصحيح الطالب الثاني",
            "expected_updated_at": env["session"]["updated_at"],
        },
    )
    assert class_edit.status_code == 200
    stale = patch(
        manager,
        url,
        {
            "status": "PRESENT",
            "reason": "تصحيح فردي",
            "expected_updated_at": detail["periods"][0]["session_updated_at"],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "ATTENDANCE_SESSION_CHANGED"
    assert AttendanceChange.objects.count() == 1
    fresh = patch(
        manager,
        url,
        {
            "status": "PRESENT",
            "reason": "تصحيح فردي بعد المراجعة",
            "expected_updated_at": class_edit.json()["updated_at"],
        },
    )
    assert fresh.status_code == 200
    stale_class = patch(
        manager,
        env["url"],
        {
            "marks": [absent(student_id)],
            "reason": "نسخة قديمة",
            "expected_updated_at": class_edit.json()["updated_at"],
        },
    )
    assert stale_class.status_code == 409
    assert stale_class.json()["code"] == "ATTENDANCE_SESSION_CHANGED"
    assert AttendanceChange.objects.count() == 2
    assert not AttendanceMark.objects.filter(session_id=env["session"]["id"]).exists()
    assert DailyAttendanceSummary.objects.get(student_id=student_id).absence_status == "NONE"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("other_role", ["VICE_PRINCIPAL", "TEACHER"])
def test_concurrent_class_corrections_keep_winner_and_require_review_before_retry(
    correction_env,
    role_client,
    other_role,
):
    env = correction_env
    manager, _, _ = role_client(["SCHOOL_MANAGER"], school=env["school"])
    other = (
        env["teacher"]
        if other_role == "TEACHER"
        else role_client(
            [other_role],
            school=env["school"],
        )[0]
    )
    clients = [manager, other]
    original = env["session"]
    student_ids = [student.id for student in env["students"][:2]]
    barrier = Barrier(2)

    def concurrent(index):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            return patch(
                clients[index],
                env["url"],
                {
                    "marks": [absent(student_ids[1 - index])],
                    "reason": "تصحيح متزامن",
                    "expected_updated_at": original["updated_at"],
                },
            )
        finally:
            connections.close_all()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            requests = [pool.submit(concurrent, index) for index in range(2)]
            results = [request.result(timeout=30) for request in requests]
        assert sorted(result.status_code for result in results) == [200, 409]
        loser = next(index for index, result in enumerate(results) if result.status_code == 409)
        assert results[loser].json()["code"] == "ATTENDANCE_SESSION_CHANGED"
        winner = 1 - loser
        assert list(AttendanceMark.objects.values_list("student_id", flat=True)) == [
            student_ids[loser],
        ]
        assert AttendanceChange.objects.count() == 1
        assert AttendanceChange.objects.get().student_id == student_ids[winner]
        assert AuditLog.objects.filter(action=AuditAction.ATTENDANCE_EDITED).count() == 1
        fresh = clients[loser].get(env["url"]).json()
        retry = patch(
            clients[loser],
            env["url"],
            {
                "marks": [],
                "reason": "مراجعة أحدث تحضير ثم استكمال التصحيح",
                "expected_updated_at": fresh["updated_at"],
            },
        )
        assert retry.status_code == 200
        assert not AttendanceMark.objects.exists()
        assert AttendanceChange.objects.count() == 2
        assert AuditLog.objects.filter(action=AuditAction.ATTENDANCE_EDITED).count() == 2
        persisted = AttendanceSession.objects.get(id=original["id"])
        assert persisted.submitted_by_membership.user_id == env["teacher_user"].id
        assert persisted.submitted_at.isoformat() == original["submitted_at"]
        assert set(DailyAttendanceSummary.objects.values_list("absence_status", flat=True)) == {
            "NONE",
        }
    finally:
        connections.close_all()
        connections["default"].close_pool()


@pytest.mark.django_db(transaction=True)
def test_duplicate_single_correction_creates_one_mark_and_change(correction_env, role_client):
    env = correction_env
    clients = [
        role_client([role], school=env["school"])[0]
        for role in ("SCHOOL_MANAGER", "VICE_PRINCIPAL")
    ]
    student_id = env["students"][2].id
    url = f"{env['url']}students/{student_id}/"
    barrier = Barrier(2)

    def concurrent(client):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            return patch(
                client,
                url,
                {
                    "status": "ABSENT",
                    "reason": "تحقق إداري",
                    "expected_updated_at": env["session"]["updated_at"],
                },
            )
        finally:
            connections.close_all()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(concurrent, client) for client in clients]
            results = [future.result(timeout=30) for future in futures]
        assert sorted(result.status_code for result in results) == [200, 409]
        assert next(result for result in results if result.status_code == 409).json()["code"] == (
            "ATTENDANCE_STATUS_UNCHANGED"
        )
        assert AttendanceMark.objects.filter(student_id=student_id).count() == 1
        assert AttendanceChange.objects.count() == 1
        assert AuditLog.objects.filter(action=AuditAction.ATTENDANCE_EDITED).count() == 1
    finally:
        connections.close_all()
        connections["default"].close_pool()
