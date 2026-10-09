"""Repeatable synthetic release workloads under actual PostgreSQL restricted roles."""

import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from statistics import median
from threading import Barrier, Event, Thread
from time import perf_counter

import pytest
from django.db import close_old_connections, connection, connections
from django.test import Client
from django.utils import timezone

from accounts.models import User
from attendance.models import DailyAttendanceSummary
from common.tenant_rls import _settings, tenant_context
from parents.models import GuardianStudentRelation
from parents.request_models import ParentNotification
from tests.attendance_helpers import setup_attendance_env
from tests.test_parent_independent_account_security import _application_role

pytestmark = pytest.mark.django_db(transaction=True)


def _measure(client, url, *, repeats=7):
    samples = []
    responses = []
    for _ in range(repeats):
        queries = 0

        def count(execute, sql, params, many, context):
            nonlocal queries
            queries += 1
            return execute(sql, params, many, context)

        start = perf_counter()
        with connection.execute_wrapper(count):
            response = client.get(url)
            assert response.status_code == 200, response.content
        samples.append({
            "queries": queries,
            "milliseconds": round((perf_counter() - start) * 1000, 3),
        })
        responses.append(response.json())
    durations = sorted(sample["milliseconds"] for sample in samples)
    return {
        "samples": samples,
        "p50_ms": round(median(durations), 3),
        "p95_ms": durations[math.ceil(0.95 * len(durations)) - 1],
        "query_counts": sorted({sample["queries"] for sample in samples}),
    }, responses


def _fixtures(make_school, make_user):
    approver = make_user("0550078100")
    envs = [
        setup_attendance_env(make_school(f"مدرسة قياس الإصدار {i}"), students_count=5)
        for i in range(3)
    ]
    students = [envs[i % 3]["students"][i // 3] for i in range(10)]
    owners, relations, clients = {}, {}, {}
    for size in (1, 5, 10):
        owners[size] = make_user(f"05500781{size:02d}", recovery_email_verified=True)
        relations[size] = [
            GuardianStudentRelation.objects.create(
                school_id=student.school_id, student=student, user=owners[size],
                status="ACTIVE", contact_bound=False, approved_by=approver,
                approved_at=timezone.now(),
            ) for student in students[:size]
        ]
        ParentNotification.objects.bulk_create([
            ParentNotification(
                school_id=relations[size][i % size].school_id,
                relation=relations[size][i % size], user=owners[size],
                kind="RELATION_STATUS", dedup_key=f"release-measure:{i}",
                title="إشعار قياس صناعي",
            ) for i in range(500)
        ])
        clients[size] = Client()
        clients[size].force_login(owners[size])
    return approver, envs, owners, relations, clients


def test_one_five_ten_children_three_schools_and_unrelated_rows(make_school, make_user):
    approver, envs, owners, relations, clients = _fixtures(make_school, make_user)
    urls = {
        "children": "/api/v1/parent/children/?page_size=20",
        "notifications": "/api/v1/parent/notifications/?page_size=20",
    }
    before = {}
    with _application_role():
        for size, client in clients.items():
            before[size] = {}
            for name, url in urls.items():
                _measure(client, url, repeats=1)  # Auth/config and idempotent inbox warm-up.
                before[size][name], responses = _measure(client, url)
                if name == "children":
                    assert responses[-1]["count"] == size
                    assert len(responses[-1]["results"]) == size
                else:
                    assert responses[-1]["count"] == 500
                    assert len(responses[-1]["items"]) == 20
                    assert {row["relation_id"] for row in responses[-1]["items"]} <= {
                        relation.pk for relation in relations[size]
                    }
    foreign_users = User.objects.bulk_create([
        User(mobile=f"+9665790{i:05d}") for i in range(2000)
    ])
    GuardianStudentRelation.objects.bulk_create([
        GuardianStudentRelation(
            user=user, school_id=relations[10][0].school_id,
            student=envs[0]["students"][-1], status="ACTIVE", contact_bound=False,
            approved_by=approver, approved_at=timezone.now(),
        ) for user in foreign_users
    ])
    first = relations[10][0]
    end = envs[0]["local_now"].date()
    start = end - timedelta(days=365)
    DailyAttendanceSummary.objects.bulk_create([
        DailyAttendanceSummary(
            school_id=first.school_id, student=first.student, academic_year=envs[0]["year"],
            section=envs[0]["section"], attendance_date=start + timedelta(days=i),
            expected_periods=7, submitted_periods=7, absent_periods=1,
            present_periods=6, unexcused_absent_periods=1,
            completeness_status="COMPLETE", absence_status="PARTIAL",
            calculated_at=timezone.now(),
        ) for i in range(366)
    ])
    with connection.cursor() as cursor:
        cursor.execute("ANALYZE parents_guardianstudentrelation")
        cursor.execute("ANALYZE parents_parentnotification")
    after = {}
    with _application_role():
        for size, client in clients.items():
            after[size] = {}
            for name, url in urls.items():
                after[size][name], responses = _measure(client, url)
                assert before[size][name]["query_counts"] == after[size][name]["query_counts"]
                assert responses[-1]["count"] == (size if name == "children" else 500)
        history_url = f"/api/v1/parent/children/{first.pk}/history/"
        history, response = _measure(
            clients[10], f"{history_url}?from_date={start}&to_date={end}",
        )
        assert len(response[-1]["results"]) == 366
        short, _ = _measure(clients[10], f"{history_url}?from_date={end}&to_date={end}")
        assert history["query_counts"] == short["query_counts"]
        poll, _ = _measure(clients[10], f"/api/v1/parent/children/{first.pk}/", repeats=10)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.current_user_id', %s, false)", [str(owners[10].pk)],
            )
        relation_plan = GuardianStudentRelation.objects.filter(user=owners[10]).explain(
            analyze=True, buffers=True,
        )
        notice_plan = ParentNotification.objects.filter(user=owners[10]).order_by(
            "-created_at", "-id",
        )[:20].explain(analyze=True, buffers=True)
        assert "Index" in relation_plan and "Seq Scan" not in relation_plan
    print("release workload=" + json.dumps({
        "before_foreign": before, "after_2000_foreign": after,
        "history_366": history, "history_1": short, "ten_repeated_child_polls": poll,
        "percentile_method": "nearest-rank p95; seven local samples except ten child polls",
    }))
    print("release relation plan:\n" + relation_plan)
    print("release notification plan:\n" + notice_plan)


def test_twenty_distinct_users_concurrently_poll_twice(make_school, make_user):
    school = make_school("مدرسة عشرين مستخدماً صناعياً")
    env = setup_attendance_env(school, students_count=1)
    approver = make_user("0550078300")
    owners = [
        make_user(f"05500783{i + 1:02d}", recovery_email_verified=True) for i in range(20)
    ]
    relations = [GuardianStudentRelation.objects.create(
        school=school, student=env["students"][0], user=owner, status="ACTIVE",
        contact_bound=False, approved_by=approver, approved_at=timezone.now(),
    ) for owner in owners]
    barrier = Barrier(20)
    stop_monitor = Event()
    lock_samples, monitor_errors = [], []

    def monitor_locks():
        # Metadata only, from the isolated test database; no SQL text or student facts.
        close_old_connections()
        try:
            while not stop_monitor.is_set():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT clock_timestamp(), "
                        "count(*) FILTER (WHERE wait_event_type = 'Lock'), "
                        "count(*) FILTER (WHERE state = 'active' AND pid <> pg_backend_pid()), "
                        "max(extract(epoch FROM clock_timestamp() - query_start)) "
                        "FILTER (WHERE wait_event_type = 'Lock') "
                        "FROM pg_stat_activity WHERE datname = current_database()",
                    )
                    at, waiting, active, oldest = cursor.fetchone()
                lock_samples.append({
                    "at": at.isoformat(), "waiting_on_lock": waiting,
                    "active_queries": active,
                    "oldest_waiting_query_ms": round(float(oldest) * 1000, 3) if oldest else 0,
                })
                stop_monitor.wait(0.05)
        except Exception as exc:
            monitor_errors.append(exc)
        finally:
            connections.close_all()

    with _application_role():
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            role = cursor.fetchone()[0]

        def read(index):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"SET ROLE {connection.ops.quote_name(role)}")
                    cursor.execute(
                        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user",
                    )
                    assert cursor.fetchone() == (False, False)
                client = Client()
                client.force_login(owners[index])
                barrier.wait(timeout=30)
                samples, responses = _measure(
                    client, f"/api/v1/parent/children/{relations[index].pk}/", repeats=2,
                )
                assert all(row["child"]["relation_id"] == relations[index].pk for row in responses)
                return samples
            finally:
                connections.close_all()

        monitor = Thread(target=monitor_locks)
        monitor.start()
        started = perf_counter()
        try:
            with ThreadPoolExecutor(max_workers=20) as pool:
                samples = list(pool.map(read, range(20)))
            wall = round((perf_counter() - started) * 1000, 3)
        finally:
            stop_monitor.set()
            monitor.join(timeout=10)
        assert not monitor.is_alive()
        assert not monitor_errors, monitor_errors
    durations = sorted(row["milliseconds"] for sample in samples for row in sample["samples"])
    assert len(durations) == 40
    print("release twenty-user concurrency=" + json.dumps({
        "users": 20, "workers": 20, "requests": 40, "wall_ms": wall,
        "p50_ms": round(median(durations), 3),
        "p95_ms": durations[math.ceil(0.95 * len(durations)) - 1],
        "samples": samples,
        "lock_observations": lock_samples,
        "lock_sampling_limits": "50ms requested intervals; brief waits can fall between samples",
        "note": "local burst, not sustained 30-second production capacity",
    }))


def test_actual_notification_count_and_page_plans_in_exact_owned_context(
    make_school, make_user,
):
    """Explain the captured API SQL, including availability joins and forced RLS.

    A simple user-index projection cannot establish the cost of the actual inbox
    predicate. Capture its bound SQL in the live request and replay only SELECTs
    under that same non-bypass role, school and owner. Output contains plan metadata,
    never number/evidence data or raw request parameters.
    """
    approver, envs, owners, relations, clients = _fixtures(make_school, make_user)
    owner = owners[10]
    private_ids = list(
        ParentNotification.objects.filter(user=owner).order_by("id")
        .values_list("id", flat=True)[:250]
    )
    ParentNotification.objects.filter(id__in=private_ids).update(kind="ABSENCE")
    foreign_users = User.objects.bulk_create([
        User(mobile=f"+9665791{i:05d}") for i in range(2000)
    ])
    GuardianStudentRelation.objects.bulk_create([
        GuardianStudentRelation(
            user=user, school_id=relations[10][0].school_id,
            student=envs[0]["students"][-1], status="ACTIVE", contact_bound=False,
            approved_by=approver, approved_at=timezone.now(),
        ) for user in foreign_users
    ])
    with connection.cursor() as cursor:
        for table in (
            "parents_guardianstudentrelation", "parents_parentnotification",
            "students_student", "schools_school",
        ):
            cursor.execute(f"ANALYZE {connection.ops.quote_name(table)}")
    captured = []

    def capture(execute, sql, params, many, context):
        if not sql.startswith("SELECT ") or '"parents_parentnotification"' not in sql:
            return execute(sql, params, many, context)
        kind = (
            "count" if sql.startswith("SELECT COUNT(*) AS")
            else "page" if 'AS "parent_relation_available"' in sql and " LIMIT 20" in sql
            else None
        )
        if kind is None:
            return execute(sql, params, many, context)
        school_id, user_id, bypass = _settings()
        assert int(user_id) == owner.pk
        assert int(school_id) in {relation.school_id for relation in relations[10]}
        assert bypass == "off"
        assert not many
        start = perf_counter()
        result = execute(sql, params, many, context)
        captured.append({
            "kind": kind, "school_id": int(school_id), "sql": sql,
            "params": params, "request_sql_ms": round((perf_counter() - start) * 1000, 3),
        })
        return result

    def find_relation_scans(node):
        if node.get("Relation Name") == "parents_guardianstudentrelation":
            yield node
        for child in node.get("Plans", []):
            yield from find_relation_scans(child)

    reports = []
    with _application_role():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user",
            )
            assert cursor.fetchone() == (False, False)
        with connection.execute_wrapper(capture):
            response = clients[10].get("/api/v1/parent/notifications/?page_size=20")
        assert response.status_code == 200, response.content
        assert response.json()["count"] == 500
        assert len(response.json()["items"]) == 20
        assert len(captured) == 6  # Exact COUNT and page query for each of three schools.
        assert {query["kind"] for query in captured} == {"count", "page"}
        for query in captured:
            with tenant_context(school_id=query["school_id"], user_id=owner.pk):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query["sql"],
                        query["params"],
                    )
                    plan = cursor.fetchone()[0][0]
            relation_scans = list(find_relation_scans(plan["Plan"]))
            assert relation_scans
            # The joined ownership predicate must constrain relation access too.
            # Counting SQL alone missed a PK walk through 2000 foreign RLS rows.
            assert all(
                node["Actual Rows"] + node.get("Rows Removed by Filter", 0) <= len(relations[10])
                for node in relation_scans
            ), relation_scans
            reports.append({
                "query": query["kind"], "request_sql_ms": query["request_sql_ms"],
                "planning_ms": plan["Planning Time"], "execution_ms": plan["Execution Time"],
                "plan": plan["Plan"],
            })
    assert _settings() == ("", "", "off")
    print("release actual notification plans=" + json.dumps({
        "children": 10, "schools": 3, "notifications": 500,
        "unrelated_guardians": 2000, "restricted_role": True,
        "captured_count_page_queries": len(reports), "queries": reports,
        "joined_relation_rows_per_scan_bound": len(relations[10]),
        "limits": "single local request plus replayed exact SELECTs; not a capacity result",
    }))
