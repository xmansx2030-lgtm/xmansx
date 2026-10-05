from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from threading import Barrier
from zoneinfo import ZoneInfo

import pytest
from django.db import close_old_connections, connection, connections
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from academics.models import BellPeriod
from attendance.models import AttendanceMark, AttendanceSession
from attendance.selectors.preparation import get_today_preparation
from audit.models import AuditLog
from students.models import Section
from tests.attendance_helpers import make_students, setup_attendance_env

NOW = datetime(2026, 10, 5, 9, 5, tzinfo=ZoneInfo("Asia/Riyadh"))
BASE = "/api/v1/attendance/admin"


@pytest.fixture
def prepared_env(role_client, monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: NOW)
    teacher, school, user = role_client(["TEACHER"])
    env = setup_attendance_env(school)
    period = env["period"]
    period.sequence = 2
    period.start_time = time(8, 40)
    period.end_time = time(9, 20)
    period.save()
    for sequence, start, end in [(1, time(8), time(8, 40)), (3, time(9, 20), time(10))]:
        BellPeriod.objects.create(
            school=school,
            bell_schedule=env["schedule"],
            sequence=sequence,
            name=f"الحصة {sequence}",
            start_time=start,
            end_time=end,
        )
    env.update(school=school, teacher=teacher, teacher_user=user)
    return env


def target(env, sequence=1):
    return {
        "section_id": env["section"].id,
        "date": NOW.date().isoformat(),
        "period_sequence": sequence,
    }


def post(client, url, data):
    return client.post(url, data, content_type="application/json")


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["SCHOOL_MANAGER", "VICE_PRINCIPAL"])
def test_leader_previews_starts_and_submits_an_ended_period(prepared_env, role_client, role):
    env = prepared_env
    admin, _, user = role_client([role], school=env["school"])
    preview = admin.get(f"{BASE}/sections/{env['section'].id}/preview/", target(env))
    assert preview.status_code == 200
    assert preview.json()["period"]["sequence"] == 1
    assert not AttendanceSession.objects.exists()
    assert (
        admin.get("/api/v1/attendance/preparation/today/").json()["periods"][0]["summary"][
            "not_started"
        ]
        == 1
    )
    session = post(admin, f"{BASE}/sessions/start/", target(env)).json()
    assert session["status"] == "IN_PROGRESS"
    assert (
        admin.get("/api/v1/attendance/preparation/today/").json()["periods"][0]["summary"][
            "in_progress"
        ]
        == 1
    )
    response = post(
        admin,
        f"{BASE}/sessions/{session['id']}/submit/",
        {
            "marks": [{"student_id": env["students"][0].id, "status": "ABSENT"}],
            "reason": "استكمال تحضير الفصل",
        },
    )
    assert response.status_code == 200
    record = AttendanceSession.objects.get(id=session["id"])
    assert record.submitted_by_membership.user_id == user.id
    assert record.period_sequence == 1
    assert record.marks.count() == 1
    assert AuditLog.objects.filter(
        action="ATTENDANCE_SUBMITTED",
        actor=user,
        metadata__administrative_reason="استكمال تحضير الفصل",
        metadata__administrative_role=role,
    ).exists()
    period = get_today_preparation(school=env["school"])["periods"][0]
    assert period["summary"]["incomplete"] == 0
    assert period["summary"]["overdue"] == 0
    assert (
        admin.get("/api/v1/attendance/preparation/today/").json()["periods"][0]["summary"][
            "incomplete"
        ]
        == 0
    )


@pytest.mark.django_db
def test_leader_resumes_teacher_session_and_preserves_frozen_schedule(prepared_env, role_client):
    env = prepared_env
    teacher_session = post(
        env["teacher"],
        "/api/v1/attendance/sessions/start/",
        {
            "section_id": env["section"].id,
        },
    ).json()
    admin, _, user = role_client(["VICE_PRINCIPAL"], school=env["school"])
    resumed = post(admin, f"{BASE}/sessions/start/", target(env, 2))
    assert resumed.status_code == 200
    assert resumed.json()["id"] == teacher_session["id"]
    assert AttendanceSession.objects.get().started_by_membership.user_id == env["teacher_user"].id
    BellPeriod.objects.filter(bell_schedule=env["schedule"], sequence=1).delete()
    previous = post(admin, f"{BASE}/sessions/start/", target(env)).json()
    assert previous["period"]["start_time"] == "08:00"
    assert AttendanceSession.objects.get(id=previous["id"]).bell_period_id is None
    assert (
        post(
            admin,
            f"{BASE}/sessions/{teacher_session['id']}/submit/",
            {
                "marks": [],
                "reason": "استكمال جلسة المعلم",
            },
        ).status_code
        == 200
    )
    assert (
        AttendanceSession.objects.get(id=teacher_session["id"]).submitted_by_membership.user_id
        == user.id
    )


@pytest.mark.django_db
def test_scope_counts_unsubmitted_only_and_has_no_read_side_effects(prepared_env):
    env = prepared_env
    inactive = Section.objects.create(
        school=env["school"], grade=env["grade"], code="old", name="قديم", is_active=False
    )
    make_students(env["school"], inactive, env["year"], 1, prefix="18661")
    Section.objects.create(school=env["school"], grade=env["grade"], code="empty", name="فارغ")
    payload = get_today_preparation(school=env["school"])
    assert [p["state"] for p in payload["periods"]] == ["ENDED", "CURRENT", "UPCOMING"]
    assert payload["periods"][0]["summary"]["incomplete"] == 1
    assert payload["periods"][1]["summary"]["not_started"] == 1
    assert payload["periods"][2]["summary"] is None
    assert not payload["periods"][2]["sections"]
    assert not AttendanceSession.objects.exists()


@pytest.mark.django_db
def test_admin_rejects_previous_date_future_period_blank_reason_and_empty_section(
    prepared_env, role_client
):
    env = prepared_env
    admin, _, _ = role_client(["SCHOOL_MANAGER"], school=env["school"])
    for data, code in [
        (
            {**target(env), "date": (NOW.date() - timedelta(days=1)).isoformat()},
            "ADMIN_ATTENDANCE_TODAY_ONLY",
        ),
        (target(env, 3), "ATTENDANCE_PERIOD_NOT_STARTED"),
    ]:
        response = post(admin, f"{BASE}/sessions/start/", data)
        assert response.status_code == 409
        assert response.json()["code"] == code
    empty = Section.objects.create(
        school=env["school"], grade=env["grade"], code="empty", name="فارغ"
    )
    assert (
        post(admin, f"{BASE}/sessions/start/", {**target(env), "section_id": empty.id}).status_code
        == 400
    )
    session = post(admin, f"{BASE}/sessions/start/", target(env)).json()
    assert (
        post(
            admin, f"{BASE}/sessions/{session['id']}/submit/", {"marks": [], "reason": "   "}
        ).status_code
        == 400
    )
    assert AttendanceSession.objects.get().status == "IN_PROGRESS"


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["TEACHER", "COUNSELOR", "GATE_GUARD"])
def test_other_roles_cannot_use_administrative_endpoints(prepared_env, role_client, role):
    env = prepared_env
    client, _, _ = role_client([role], school=env["school"])
    assert client.get("/api/v1/attendance/preparation/today/").status_code == 403
    assert (
        client.get(f"{BASE}/sections/{env['section'].id}/preview/", target(env)).status_code == 403
    )
    assert post(client, f"{BASE}/sessions/start/", target(env)).status_code == 403
    assert (
        post(client, f"{BASE}/sessions/1/submit/", {"marks": [], "reason": "اختبار"}).status_code
        == 403
    )


@pytest.mark.django_db
def test_tenant_isolation_for_start_preview_submit_and_day_counts(prepared_env, role_client):
    env = prepared_env
    admin, _, _ = role_client(["SCHOOL_MANAGER"], school=env["school"])
    session = post(admin, f"{BASE}/sessions/start/", target(env)).json()
    foreign, school, _ = role_client(["VICE_PRINCIPAL"])
    setup_attendance_env(school)
    assert (
        foreign.get(f"{BASE}/sections/{env['section'].id}/preview/", target(env)).status_code == 404
    )
    assert post(foreign, f"{BASE}/sessions/start/", target(env)).status_code == 404
    assert (
        post(
            foreign, f"{BASE}/sessions/{session['id']}/submit/", {"marks": [], "reason": "اختبار"}
        ).status_code
        == 404
    )
    rows = foreign.get("/api/v1/attendance/preparation/today/").json()["periods"][0]["sections"]
    assert all(row["section_id"] != env["section"].id for row in rows)


@pytest.mark.django_db
def test_monitoring_query_count_does_not_grow_per_section(prepared_env):
    from attendance.services.periods import build_period_snapshot

    env = prepared_env
    post(env["teacher"], "/api/v1/attendance/sessions/start/", {"section_id": env["section"].id})
    membership = env["teacher_user"].memberships.get(school=env["school"])
    get_today_preparation(school=env["school"])
    with CaptureQueriesContext(connection) as initial:
        get_today_preparation(school=env["school"])
    for number in range(12):
        section = Section.objects.create(
            school=env["school"],
            grade=env["grade"],
            code=f"q{number}",
            name=str(number),
        )
        make_students(env["school"], section, env["year"], 1, prefix=f"19{number:03d}")
        AttendanceSession.objects.create(
            school=env["school"],
            academic_year=env["year"],
            section=section,
            attendance_date=NOW.date(),
            period_sequence=2,
            bell_period_snapshot=build_period_snapshot(env["period"], NOW.date(), "Asia/Riyadh"),
            roster_fingerprint="fp",
            unprepared_alert_minutes_snapshot=25,
            started_by_membership=membership,
        )
    with CaptureQueriesContext(connection) as expanded:
        payload = get_today_preparation(school=env["school"])
    assert payload["periods"][1]["summary"]["incomplete"] == 13
    assert len(initial) == len(expanded)
    assert len(expanded) <= 10


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("role", ["SCHOOL_MANAGER", "VICE_PRINCIPAL"])
def test_concurrent_teacher_and_leader_start_and_submit_have_one_winner(
    prepared_env, role_client, role
):
    env = prepared_env
    admin, _, user = role_client([role], school=env["school"])
    barrier = Barrier(2)

    def concurrent(client, url, body):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return post(client, url, body)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        teacher = pool.submit(
            concurrent,
            env["teacher"],
            "/api/v1/attendance/sessions/start/",
            {"section_id": env["section"].id},
        )
        leader = pool.submit(concurrent, admin, f"{BASE}/sessions/start/", target(env, 2))
        starts = [teacher.result(timeout=30), leader.result(timeout=30)]
    assert sorted(r.status_code for r in starts) == [200, 201]
    assert starts[0].json()["id"] == starts[1].json()["id"]
    assert AttendanceSession.objects.count() == 1
    session_id = starts[0].json()["id"]
    barrier = Barrier(2)
    teacher_marks = [{"student_id": env["students"][0].id, "status": "ABSENT"}]
    admin_marks = [{"student_id": env["students"][1].id, "status": "ABSENT"}]
    with ThreadPoolExecutor(max_workers=2) as pool:
        teacher = pool.submit(
            concurrent,
            env["teacher"],
            f"/api/v1/attendance/sessions/{session_id}/submit/",
            {"marks": teacher_marks},
        )
        leader = pool.submit(
            concurrent,
            admin,
            f"{BASE}/sessions/{session_id}/submit/",
            {"marks": admin_marks, "reason": "تغطية إدارية"},
        )
        submits = [teacher.result(timeout=30), leader.result(timeout=30)]
    assert sorted(r.status_code for r in submits) == [200, 409]
    loser = next(r for r in submits if r.status_code == 409)
    assert loser.json()["code"] == "ATTENDANCE_SESSION_ALREADY_SUBMITTED"
    record = AttendanceSession.objects.get(id=session_id)
    teacher_won = submits[0].status_code == 200
    assert record.submitted_by_membership.user_id == (
        env["teacher_user"].id if teacher_won else user.id
    )
    assert list(AttendanceMark.objects.values_list("student_id", flat=True)) == [
        env["students"][0 if teacher_won else 1].id,
    ]
    assert AuditLog.objects.filter(action="ATTENDANCE_SUBMITTED").count() == 1
    connections.close_all()
    connections["default"].close_pool()
