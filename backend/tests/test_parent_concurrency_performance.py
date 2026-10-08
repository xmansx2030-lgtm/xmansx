"""Measured local workload and concurrent lifecycle invariants on PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from urllib.parse import parse_qs, urlsplit

import pytest
from django.db import close_old_connections, connection, connections
from django.test import Client
from django.utils import timezone

from accounts.models import User
from common.security.identifiers import decrypt_national_id
from parents.models import GuardianRegistrationRequest, GuardianStudentRelation
from tests import test_parent_portal as journeys
from tests.test_parent_portal import (
    PASSWORD,
    activate,
    approve,
    post,
    register,
)

portal_env = journeys.portal_env


@pytest.mark.django_db(transaction=True)
def test_concurrent_activation_consumes_token_once(portal_env):
    env = portal_env
    item, _ = register(env)
    result = approve(env, item)
    token = parse_qs(urlsplit(result["activation_url"]).fragment)["token"][0]

    def complete(_):
        close_old_connections()
        try:
            return post(
                Client(),
                "/api/v1/parent/activation/",
                {
                    "token": token,
                    "new_password": PASSWORD,
                    "confirm_password": PASSWORD,
                },
            ).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(complete, range(2)))
    assert sorted(statuses) == [200, 409]
    assert User.objects.filter(mobile=env["student"].guardian_mobile).count() == 1
    assert GuardianStudentRelation.objects.filter(student=env["student"]).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_registration_creates_one_pending_request(portal_env):
    env = portal_env
    data = {
        "name": "ولي أمر موثق",
        "mobile": env["student"].guardian_mobile,
        "student_identifier": decrypt_national_id(env["student"].national_id_encrypted),
        "relationship_type": "أب",
    }

    def submit(_):
        close_old_connections()
        try:
            return post(Client(), env["url"], data).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(submit, range(4))) == [202] * 4
    assert GuardianRegistrationRequest.objects.count() == 1


@pytest.mark.django_db
def test_two_thousand_global_guardians_do_not_expand_owned_polling(portal_env):
    env = portal_env
    relation, _, _ = activate(env)
    users = User.objects.bulk_create([User(mobile=f"+9665700{i:05d}") for i in range(2000)])
    GuardianStudentRelation.objects.bulk_create(
        [
            GuardianStudentRelation(
                user=user,
                school=env["school"],
                student=env["students"][1],
                status="ACTIVE",
                contact_bound=False,
                approved_by=env["actor"],
                approved_at=timezone.now(),
            )
            for user in users
        ]
    )
    samples = []
    query_count = 0

    def count_query(execute, sql, params, many, context):
        nonlocal query_count
        query_count += 1
        return execute(sql, params, many, context)

    with connection.execute_wrapper(count_query):
        for _ in range(5):
            started = perf_counter()
            response = env["parent"].get(f"/api/v1/parent/children/{relation.id}/")
            samples.append(round((perf_counter() - started) * 1000, 2))
            assert response.status_code == 200
    assert 0 < query_count <= 175
    assert len(env["parent"].get("/api/v1/parent/children/").json()["results"]) == 1
    print(f"parent workload:2000 other guardians;5 polls;queries={query_count};ms={samples}")
