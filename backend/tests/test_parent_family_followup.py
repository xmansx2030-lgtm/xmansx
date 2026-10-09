"""School family queue, exact deep links and detail reads under real PostgreSQL RLS."""

from uuid import uuid4

import pytest
from django.db import connection
from django.test import override_settings

from common.tenant_rls import clear_tenant_context
from parents.models import ParentExcuseRequest
from school_dashboard.selectors.attention import MAX_ITEMS_PER_KIND
from tests import test_parent_requests as family_helpers
from tests.excuse_env import build_env
from tests.test_parent_requests import approve, post, submit

pytestmark = pytest.mark.django_db
family_env = family_helpers.family_env
BASE = "/api/v1/staff/parents"


def correction(env):
    response = post(
        env["client"],
        f"{env['prefix']}/corrections/",
        {"session_id": env["session"].id, "reason": "طلب تصحيح للمراجعة"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize("role", ["SCHOOL_MANAGER", "VICE_PRINCIPAL"])
def test_family_attention_opens_exact_requests_and_disappears_after_decision(
    family_env, role_client, role
):
    env = family_env
    client, _, _ = role_client([role], school=env["school"])
    excuse = submit(env).json()
    attendance = correction(env)
    queue = client.get("/api/v1/dashboard/attention/")
    assert queue.status_code == 200
    rows = {item["kind"]: item for item in queue.json()["items"]}
    for kind, obj, request_type, resource in (
        ("PARENT_EXCUSE_PENDING", excuse, "EXCUSE", "excuses"),
        ("PARENT_CORRECTION_PENDING", attendance, "CORRECTION", "corrections"),
    ):
        row = rows[kind]
        assert row["entity_id"] == obj["id"]
        assert (
            row["target_url"]
            == f"/parent-management?tab=requests&type={request_type}&request={obj['id']}"
        )
        detail = client.get(f"{BASE}/{resource}/{obj['id']}/")
        assert detail.status_code == 200
        assert detail.json()["student_name"] == env["relation"].student.full_name
        assert detail.json()["requester_name"] == env["user"].display_name
        assert "notes" not in row and "attachments" not in row
    assert approve(env, excuse["id"], decision="REJECTED").status_code == 200
    response = post(
        client,
        f"{BASE}/corrections/{attendance['id']}/decision/",
        {
            "decision": "REJECTED",
            "note": "تمت المراجعة دون تعديل الحضور",
        },
    )
    assert response.status_code == 200
    remaining = client.get("/api/v1/dashboard/attention/").json()
    assert remaining["counts"]["parent_excuse_pending"] == 0
    assert remaining["counts"]["parent_correction_pending"] == 0
    history = client.get(f"{BASE}/excuses/{excuse['id']}/").json()
    assert history["status"] == "REJECTED"
    assert history["decision_note"] == "تم التحقق"
    assert history["reviewed_at"]
    assert history["reviewer_name"] == "موظف المدرسة"


def test_decision_names_never_fall_back_to_global_login_numbers(family_env):
    env = family_env
    env["user"].first_name = ""
    env["user"].save(update_fields=["first_name"])
    excuse = submit(env).json()
    assert approve(env, excuse["id"], decision="REJECTED").status_code == 200
    detail = env["staff_client"].get(f"{BASE}/excuses/{excuse['id']}/").json()
    assert detail["requester_name"] == "ولي الأمر"
    assert detail["reviewer_name"] == "موظف المدرسة"
    from staff.models import StaffProfile

    StaffProfile.objects.create(
        school=env["school"], membership=env["vice"], display_name="وكيل المدرسة الموثق"
    )
    detail = env["staff_client"].get(f"{BASE}/excuses/{excuse['id']}/").json()
    assert detail["reviewer_name"] == "وكيل المدرسة الموثق"
    listing = env["staff_client"].get(f"{BASE}/requests/").json()["excuses"][0]
    assert listing["reviewer_name"] == "وكيل المدرسة الموثق"
    assert listing["requester_name"] == "ولي الأمر"


def test_needs_information_stays_visible_but_cancelled_and_final_do_not(family_env):
    env = family_env
    obj = submit(env).json()
    assert approve(env, obj["id"], decision="NEEDS_INFO").status_code == 200
    rows = env["staff_client"].get("/api/v1/dashboard/attention/").json()["items"]
    row = next(item for item in rows if item["kind"] == "PARENT_EXCUSE_PENDING")
    assert row["reason_code"] == "FAMILY_AWAITING_INFORMATION"
    assert "يحتاج استكمالاً" in row["display_text"]
    assert post(env["client"], f"{env['prefix']}/excuses/{obj['id']}/cancel/").status_code == 200
    rows = env["staff_client"].get("/api/v1/dashboard/attention/").json()["items"]
    assert not any(item["kind"] == "PARENT_EXCUSE_PENDING" for item in rows)


def test_old_queue_request_detail_does_not_depend_on_first_history_page(family_env):
    env = family_env
    oldest = submit(env).json()
    for index in range(30):
        ParentExcuseRequest.objects.create(
            school=env["school"],
            student=env["relation"].student,
            relation=env["relation"],
            requester=env["user"],
            reason_type="OTHER",
            targets=[],
            target_fingerprint=f"{index + 100:064x}",
            status="REJECTED",
        )
    page = env["staff_client"].get(f"{BASE}/requests/").json()
    assert oldest["id"] not in [row["id"] for row in page["excuses"]]
    detail = env["staff_client"].get(f"{BASE}/excuses/{oldest['id']}/")
    assert detail.status_code == 200 and detail.json()["id"] == oldest["id"]


def test_family_queue_limit_is_per_kind_and_oldest_first(family_env):
    env = family_env
    oldest = submit(env).json()
    for index in range(MAX_ITEMS_PER_KIND + 2):
        ParentExcuseRequest.objects.create(
            school=env["school"],
            student=env["relation"].student,
            relation=env["relation"],
            requester=env["user"],
            reason_type="OTHER",
            targets=[],
            target_fingerprint=f"{index + 200:064x}",
        )
    queue = env["staff_client"].get("/api/v1/dashboard/attention/").json()
    rows = [item for item in queue["items"] if item["kind"] == "PARENT_EXCUSE_PENDING"]
    assert len(rows) == MAX_ITEMS_PER_KIND
    assert rows[0]["entity_id"] == oldest["id"]


@pytest.mark.parametrize("roles", [["TEACHER"], ["COUNSELOR"], []])
def test_non_reviewers_cannot_read_family_details_or_attention(family_env, role_client, roles):
    env = family_env
    excuse = submit(env).json()
    attendance = correction(env)
    client, _, _ = role_client(roles, school=env["school"])
    for path in (
        f"{BASE}/excuses/{excuse['id']}/",
        f"{BASE}/corrections/{attendance['id']}/",
        "/api/v1/dashboard/attention/",
    ):
        assert client.get(path).status_code == 403


@pytest.mark.django_db(transaction=True)
def test_school_queue_and_details_are_isolated_under_nobypassrls(
    family_env, role_client, make_user, make_membership
):
    env = family_env
    own = submit(env).json()
    attendance = correction(env)
    foreign_client, school_b, vice_b = role_client(["VICE_PRINCIPAL"])
    teacher_b = make_membership(make_user("0551799991"), school_b, ["TEACHER"])
    build_env(school=school_b, teacher_membership=teacher_b, vice_membership=vice_b, prefix="37999")
    role = connection.ops.quote_name(f"family_followup_{uuid4().hex}")
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {role} NOSUPERUSER NOBYPASSRLS")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            cursor.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"
            )
            cursor.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
            cursor.execute(f"SET ROLE {role}")
        clear_tenant_context()
        with override_settings(DATABASE_RLS_ENFORCED=True):
            assert env["staff_client"].get(f"{BASE}/excuses/{own['id']}/").status_code == 200
            assert (
                env["staff_client"].get(f"{BASE}/corrections/{attendance['id']}/").status_code
                == 200
            )
            queue = env["staff_client"].get("/api/v1/dashboard/attention/").json()
            assert queue["counts"]["parent_excuse_pending"] == 1
            for resource, obj in (("excuses", own), ("corrections", attendance)):
                assert foreign_client.get(f"{BASE}/{resource}/{obj['id']}/").status_code == 404
            foreign = foreign_client.get("/api/v1/dashboard/attention/").json()
            assert foreign["counts"]["parent_excuse_pending"] == 0
            assert foreign["counts"]["parent_correction_pending"] == 0
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP OWNED BY {role}")
            cursor.execute(f"DROP ROLE IF EXISTS {role}")
        clear_tenant_context()
