"""Independent, synthetic restricted-role workloads; these are local measurements."""

import json
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from time import perf_counter

import pytest
from django.core.files.base import ContentFile
from django.db import close_old_connections, connection, connections
from django.test import Client
from django.utils import timezone

from accounts.models import User
from attendance.models import DailyAttendanceSummary
from documents.models import GeneratedDocument
from parents.models import GuardianStudentRelation
from parents.request_models import ParentNotification
from tests.attendance_helpers import setup_attendance_env
from tests.test_parent_independent_account_security import _application_role
from tests.test_parent_requests import VALID_PDF, family_env, make_warning, post

family_env = family_env


def _workload(make_school, make_user):
    owner = make_user("0550079001", recovery_email_verified=True)
    approver = make_user("0550079002")
    relations = []
    environments = []
    for school_index, count in enumerate((3, 1, 1)):
        school = make_school(f"مدرسة قياس مستقلة {school_index}")
        env = setup_attendance_env(school, students_count=count + 1)
        environments.append(env)
        for student in env["students"][:count]:
            relations.append(GuardianStudentRelation.objects.create(
                school=school, student=student, user=owner, status="ACTIVE",
                contact_bound=False, approved_by=approver, approved_at=timezone.now(),
            ))
    client = Client()
    client.force_login(owner)
    return owner, approver, relations, environments, client


def _sample(client, urls):
    queries = 0

    def count(execute, sql, params, many, context):
        nonlocal queries
        queries += 1
        return execute(sql, params, many, context)

    durations, responses = [], []
    with connection.execute_wrapper(count):
        for url in urls:
            start = perf_counter()
            response = client.get(url)
            assert response.status_code == 200, response.content
            if getattr(response, "streaming", False):
                assert b"".join(response.streaming_content)
            durations.append(round((perf_counter() - start) * 1000, 2))
            responses.append(response)
    return {"queries": queries, "milliseconds": durations}, responses


@pytest.mark.django_db(transaction=True)
def test_restricted_role_five_children_three_schools_and_long_history(
    make_school, make_user,
):
    owner, approver, relations, envs, client = _workload(make_school, make_user)
    urls = [f"/api/v1/parent/children/{r.pk}/" for r in relations]
    with _application_role():
        # Warm authentication/configuration paths before comparing equal requests.
        _sample(client, urls)
        single, _ = _sample(client, urls[:1])
        before, _ = _sample(client, urls)
        listing_before, _ = _sample(client, ["/api/v1/parent/children/"])

    foreign_users = User.objects.bulk_create([
        User(mobile=f"+9665800{i:05d}") for i in range(2000)
    ])
    GuardianStudentRelation.objects.bulk_create([
        GuardianStudentRelation(
            user=user, school=relations[0].school, student=envs[0]["students"][-1],
            status="ACTIVE", contact_bound=False, approved_by=approver,
            approved_at=timezone.now(),
        ) for user in foreign_users
    ])
    first = relations[0]
    end = envs[0]["local_now"].date()
    start = end - timedelta(days=365)
    DailyAttendanceSummary.objects.bulk_create([
        DailyAttendanceSummary(
            school=first.school, student=first.student, academic_year=envs[0]["year"],
            section=envs[0]["section"], attendance_date=start + timedelta(days=i),
            expected_periods=7, submitted_periods=7, absent_periods=1,
            present_periods=6, unexcused_absent_periods=1,
            completeness_status="COMPLETE", absence_status="PARTIAL",
            calculated_at=timezone.now(),
        ) for i in range(366)
    ])
    ParentNotification.objects.bulk_create([
        ParentNotification(
            school=r.school, relation=r, user=owner, kind="RELATION_STATUS",
            dedup_key=f"measurement:{i}", title="إشعار قياس صناعي",
        ) for r in relations for i in range(100)
    ])
    with connection.cursor() as cursor:
        cursor.execute("ANALYZE parents_guardianstudentrelation")
    with _application_role():
        after, _ = _sample(client, urls)
        listing_after, listing = _sample(client, ["/api/v1/parent/children/"])
        assert len(listing[0].json()["results"]) == 5
        assert before["queries"] == after["queries"]
        assert listing_before["queries"] == listing_after["queries"]
        assert after["queries"] <= 175
        history_url = f"{urls[0]}history/?from_date={start}&to_date={end}"
        history, response = _sample(client, [history_url])
        assert len(response[0].json()["results"]) == 366
        short, _ = _sample(client, [f"{urls[0]}history/?from_date={end}&to_date={end}"])
        assert history["queries"] == short["queries"]
        assert history["queries"] <= 45
        notices, response = _sample(client, ["/api/v1/parent/notifications/?page_size=20"])
        assert len(response[0].json()["items"]) == 20
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.current_user_id', %s, false)", [str(owner.pk)])
            plan = GuardianStudentRelation.objects.filter(user=owner).explain(
                analyze=True, buffers=True,
            )
        assert "Index" in plan and "Seq Scan" not in plan, plan
        tracemalloc.start()
        _sample(client, [history_url])
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    print("independent workload=" + json.dumps({
        "single_child": single, "five_before_foreign": before,
        "five_after_2000_foreign": after, "children_list": listing_after,
        "history_366": history, "history_1": short, "notifications_500_page20": notices,
        "history_python_peak_bytes": peak,
    }))
    print("independent owned-index plan:\n" + plan)


@pytest.mark.django_db(transaction=True)
def test_twelve_concurrent_child_reads_on_restricted_role(make_school, make_user):
    owner, _, relations, _, _ = _workload(make_school, make_user)
    with _application_role():
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            role = cursor.fetchone()[0]

        def read(index):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"SET ROLE {connection.ops.quote_name(role)}")
                client = Client()
                client.force_login(owner)
                result, _ = _sample(client, [
                    f"/api/v1/parent/children/{relations[index % 5].pk}/",
                ])
                return result
            finally:
                connections.close_all()

        start = perf_counter()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(read, range(12)))
        elapsed = round((perf_counter() - start) * 1000, 2)
    assert len(results) == 12
    assert len({item["queries"] for item in results}) == 1
    print("independent concurrency=" + json.dumps({
        "requests": 12, "workers": 6, "wall_ms": elapsed, "samples": results,
    }))


@pytest.mark.django_db(transaction=True)
def test_restricted_private_download_measurement_and_revocation(family_env):
    env = family_env
    document = GeneratedDocument.objects.create(
        school=env["school"], student=env["relation"].student, warning=make_warning(env),
        document_type="WARNING_LEVEL_1", template_key="warning", template_version="v3",
        generated_by_membership=env["vice"],
    )
    document.file.save("measurement.pdf", ContentFile(VALID_PDF))
    document.status = "READY"
    document.save()
    response = post(env["staff_client"], "/api/v1/staff/parents/publications/", {
        "student_id": env["relation"].student_id, "title": "مستند قياس صناعي",
        "document_id": document.pk,
    })
    assert response.status_code == 201
    url = f"{env['prefix']}/publications/{response.json()['id']}/download/"
    with _application_role():
        measurements, _ = _sample(env["client"], [url] * 3)
    GuardianStudentRelation.objects.filter(pk=env["relation"].pk).update(status="REVOKED")
    with _application_role():
        assert env["client"].get(url).status_code == 404
    print("independent private download=" + json.dumps(measurements))
