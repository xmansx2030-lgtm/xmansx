"""Contract and isolation proofs for grouped school-scoped parent reads."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.db import close_old_connections, connection, connections
from django.test import Client
from django.utils import timezone

from common.errors import ApiError
from common.tenant_rls import tenant_context
from parents.access import parent_school_read
from parents.models import GuardianStudentRelation
from parents.request_models import ParentNotification
from schools.models import SchoolStatus
from student_warnings.models import StudentWarning
from subscriptions.models import SaaSPlan, SchoolSubscription
from tests.attendance_helpers import setup_attendance_env
from tests.test_parent_independent_account_security import _application_role

pytestmark = pytest.mark.django_db(transaction=True)


def _family(make_school, make_user):
    owner = make_user("0550078501")
    other = make_user("0550078502")
    approver = make_user("0550078503")
    envs = [setup_attendance_env(make_school(), students_count=2) for _ in range(3)]
    relations = [
        GuardianStudentRelation.objects.create(
            school_id=envs[i % 3]["students"][i // 3].school_id,
            student=envs[i % 3]["students"][i // 3], user=owner, status="ACTIVE",
            contact_bound=True, approved_by=approver, approved_at=timezone.now(),
        ) for i in range(5)
    ]
    foreign = GuardianStudentRelation.objects.create(
        school_id=envs[2]["students"][1].school_id,
        student=envs[2]["students"][1], user=other, status="ACTIVE",
        contact_bound=False, approved_by=approver, approved_at=timezone.now(),
    )
    notices = []
    for relation in [*relations, foreign]:
        notices.append(ParentNotification.objects.create(
            school_id=relation.school_id, user_id=relation.user_id, relation=relation,
            kind="RELATION_STATUS", dedup_key="read-proof:generic", title="حالة العلاقة",
            body="إشعار علاقة عام",
        ))
        ParentNotification.objects.create(
            school_id=relation.school_id, user_id=relation.user_id, relation=relation,
            kind="ABSENCE", dedup_key="read-proof:private", title="غياب الطالب",
            body=f"تفصيل خاص للطالب {relation.student_id}",
        )
    client = Client()
    client.force_login(owner)
    return owner, relations, foreign, notices, envs, client


def test_multi_school_order_pagination_and_suspended_details(make_school, make_user):
    _, relations, foreign, notices, _, client = _family(make_school, make_user)
    GuardianStudentRelation.objects.filter(pk=relations[1].pk).update(status="REVOKED")
    GuardianStudentRelation.objects.filter(pk=relations[3].pk).update(
        status="SUSPENDED_CONTACT_REVIEW",
    )
    relations[2].school.status = SchoolStatus.SUSPENDED
    relations[2].school.save(update_fields=["status"])
    with _application_role():
        children = client.get("/api/v1/parent/children/?page_size=20")
        assert children.status_code == 200, children.content
        rows = children.json()["results"]
        assert [row["relation_id"] for row in rows] == [relation.pk for relation in relations]
        assert rows[0]["student"]["id"] == relations[0].student_id
        assert rows[4]["student"]["id"] == relations[4].student_id
        assert rows[1]["status"] == "REVOKED" and rows[1]["student"] is None
        assert rows[2]["status"] == "UNAVAILABLE" and rows[2]["student"] is None
        assert rows[3]["status"] == "SUSPENDED_CONTACT_REVIEW" and rows[3]["student"] is None
        inbox = client.get("/api/v1/parent/notifications/?page_size=2").json()
        # Active 0/4 have generic+private; revoked/suspended/blocked have generic only.
        assert inbox["count"] == 7
        seen = list(inbox["items"])
        for page in range(2, 5):
            response = client.get(f"/api/v1/parent/notifications/?page_size=2&page={page}")
            assert response.status_code == 200, response.content
            seen.extend(response.json()["items"])
        assert len(seen) == len({row["id"] for row in seen}) == 7
        assert [row["id"] for row in seen] == sorted([row["id"] for row in seen], reverse=True)
        assert not any(row["relation_id"] == foreign.pk for row in seen)
        hidden = {relations[i].pk for i in (1, 2, 3)}
        for row in seen:
            if row["relation_id"] in hidden:
                assert row["kind"] == "RELATION_STATUS"
                assert row["student_name"] is None and row["school_name"] is None
        foreign_filter = client.get(
            f"/api/v1/parent/notifications/?relation_id={foreign.pk}",
        )
        assert foreign_filter.status_code == 200 and foreign_filter.json()["count"] == 0
        assert client.get("/api/v1/parent/notifications/?page=10").status_code == 404
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.rls_bypass', true)")
            assert cursor.fetchone()[0] != "on"


@pytest.mark.parametrize("subscription_status,visible", [("EXPIRED", True), ("SUSPENDED", False)])
def test_grouped_reads_keep_current_subscription_access(
    make_school, make_user, subscription_status, visible,
):
    _, relations, _, _, _, client = _family(make_school, make_user)
    school = relations[0].school
    now = timezone.now()
    plan = SaaSPlan.objects.create(code="read-scope-proof", name_ar="باقة قياس")
    SchoolSubscription.objects.create(
        school=school, plan=plan, status=subscription_status,
        starts_at=now - timedelta(days=10), ends_at=now - timedelta(days=1),
        suspended_at=now if not visible else None,
        suspension_reason="توقيف قياس صناعي" if not visible else "",
    )
    with _application_role():
        response = client.get("/api/v1/parent/children/")
        assert response.status_code == 200
        rows = {row["relation_id"]: row for row in response.json()["results"]}
        assert bool(rows[relations[0].pk]["student"]) is visible
        assert bool(rows[relations[3].pk]["student"]) is visible
        assert rows[relations[1].pk]["student"]["id"] == relations[1].student_id
        inbox = client.get(
            f"/api/v1/parent/notifications/?relation_id={relations[0].pk}",
        )
        assert inbox.status_code == 200
        assert inbox.json()["count"] == (2 if visible else 1)


def test_current_contact_guard_wins_over_discovery_snapshot(make_school, make_user, monkeypatch):
    import parents.api

    owner, relations, _, _, _, client = _family(make_school, make_user)
    original_discovery = parents.api.owned_relation_index

    def discover_then_update(user):
        rows = original_discovery(user)
        with tenant_context(school_id=relations[0].school_id, user_id=owner.pk):
            type(relations[0].student).objects.filter(pk=relations[0].student_id).update(
                guardian_mobile="+966550078599",
            )
        return rows

    monkeypatch.setattr(parents.api, "owned_relation_index", discover_then_update)
    with _application_role():
        response = client.get("/api/v1/parent/children/")
        assert response.status_code == 200, response.content
        rows = {row["relation_id"]: row for row in response.json()["results"]}
        assert rows[relations[0].pk]["student"] is None
        assert rows[relations[0].pk]["status"] == "UNAVAILABLE"
        assert rows[relations[3].pk]["student"]["id"] == relations[3].student_id
        assert client.get(f"/api/v1/parent/children/{relations[0].pk}/").status_code == 404


@pytest.mark.parametrize("endpoint", ["children", "notifications"])
def test_withdrawal_during_sibling_processing_scrubs_later_child(
    make_school, make_user, monkeypatch, endpoint,
):
    import parents.request_services

    _, relations, _, _, _, client = _family(make_school, make_user)
    original_sync = parents.request_services.sync_activity_notifications

    def sync_then_withdraw_sibling(relation):
        original_sync(relation)
        if relation.pk == relations[0].pk:
            GuardianStudentRelation.objects.filter(pk=relations[3].pk).update(status="REVOKED")

    monkeypatch.setattr(
        parents.request_services, "sync_activity_notifications", sync_then_withdraw_sibling,
    )
    with _application_role():
        response = client.get(f"/api/v1/parent/{endpoint}/")
        assert response.status_code == 200, response.content
        if endpoint == "children":
            row = next(
                row for row in response.json()["results"]
                if row["relation_id"] == relations[3].pk
            )
            assert row["student"] is None and row["status"] == "UNAVAILABLE"
        else:
            rows = [
                row for row in response.json()["items"]
                if row["relation_id"] == relations[3].pk
            ]
            assert len(rows) == 1 and rows[0]["kind"] == "RELATION_STATUS"
            assert rows[0]["student_name"] is None
        assert client.get(f"/api/v1/parent/children/{relations[3].pk}/").status_code == 404


def test_group_scope_rejects_forged_foreign_school_and_relation(make_school, make_user):
    owner, relations, foreign, _, _, _ = _family(make_school, make_user)
    with _application_role():
        with pytest.raises(ApiError) as rejected:
            with parent_school_read(owner, foreign.school_id, [foreign.pk]):
                pytest.fail("Foreign ownership must fail before choosing a school context")
        assert rejected.value.status_code == 404
        with pytest.raises(ApiError):
            with parent_school_read(owner, foreign.school_id, [relations[0].pk]):
                pytest.fail("An owned ID must not authorize a different school")
        with parent_school_read(
            owner, relations[2].school_id, [relations[2].pk, foreign.pk],
        ) as scope:
            assert scope.owned_ids == [relations[2].pk]
            assert set(scope.current_relations()) == {relations[2].pk}
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_setting('app.current_school_id', true), "
                "current_setting('app.rls_bypass', true)",
            )
            school_id, bypass = cursor.fetchone()
            assert not school_id and bypass != "on"


def test_notification_page_sql_rechecks_withdrawal_after_scope_lookup(make_school, make_user):
    _, relations, _, _, _, client = _family(make_school, make_user)
    withdrawn = False

    def withdraw_before_page_count(execute, sql, params, many, context):
        nonlocal withdrawn
        if not withdrawn and "SELECT COUNT(" in sql and '"parents_parentnotification"' in sql:
            withdrawn = True
            GuardianStudentRelation.objects.filter(pk=relations[0].pk).update(status="REVOKED")
        return execute(sql, params, many, context)

    with _application_role(), connection.execute_wrapper(withdraw_before_page_count):
        response = client.get(
            f"/api/v1/parent/notifications/?relation_id={relations[0].pk}",
        )
        assert withdrawn and response.status_code == 200, response.content
        assert response.json()["count"] == 1
        row = response.json()["items"][0]
        assert row["kind"] == "RELATION_STATUS"
        assert row["student_name"] is None and row["school_name"] is None


@pytest.mark.parametrize("endpoint", ["children", "notifications"])
@pytest.mark.parametrize("blocking_source", ["school", "subscription"])
def test_single_child_rechecks_school_access_after_notification_sync(
    make_school, make_user, monkeypatch, endpoint, blocking_source,
):
    import parents.request_services

    _, relations, _, _, _, client = _family(make_school, make_user)
    school = relations[0].school
    now = timezone.now()
    subscription = SchoolSubscription.objects.create(
        school=school, plan=SaaSPlan.objects.create(code="live-access", name_ar="وصول حي"),
        status="ACTIVE", starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=30),
    )
    original_sync = parents.request_services.sync_activity_notifications

    def sync_then_block_access(relation):
        original_sync(relation)
        if relation.pk == relations[0].pk:
            if blocking_source == "school":
                type(school).objects.filter(pk=school.pk).update(status="SUSPENDED")
            else:
                SchoolSubscription.objects.filter(pk=subscription.pk).update(
                    status="SUSPENDED", suspended_at=timezone.now(),
                    suspension_reason="توقيف أثناء قراءة صناعية",
                )

    monkeypatch.setattr(
        parents.request_services, "sync_activity_notifications", sync_then_block_access,
    )
    url = (
        "/api/v1/parent/children/?page_size=1" if endpoint == "children"
        else f"/api/v1/parent/notifications/?relation_id={relations[0].pk}"
    )
    with _application_role():
        response = client.get(url)
        assert response.status_code == 200, response.content
        if endpoint == "children":
            row = response.json()["results"][0]
            assert row["relation_id"] == relations[0].pk
            assert row["student"] is None and row["status"] == "UNAVAILABLE"
        else:
            assert response.json()["count"] == 1
            row = response.json()["items"][0]
            assert row["kind"] == "RELATION_STATUS"
            assert row["student_name"] is None


def test_two_guardians_with_opposite_sibling_order_do_not_deadlock(
    make_school, make_user, make_membership, monkeypatch,
):
    import parents.request_services

    school = make_school("مدرسة تزامن إخوة")
    env = setup_attendance_env(school, students_count=2)
    approver = make_user("0550078600")
    vice = make_membership(approver, school, ["VICE_PRINCIPAL"])
    owners = [make_user("0550078601"), make_user("0550078602")]
    own_relations = []
    for owner, students in zip(
        owners, [env["students"], list(reversed(env["students"]))], strict=True,
    ):
        own_relations.append([GuardianStudentRelation.objects.create(
            school=school, student=student, user=owner, status="ACTIVE",
            contact_bound=False, approved_by=approver, approved_at=timezone.now(),
        ) for student in students])
    for student in env["students"]:
        StudentWarning.objects.create(
            school=school, student=student, academic_year=env["year"],
            warning_type="UNEXCUSED_FULL_DAY_ABSENCE", level="LEVEL_1",
            threshold_at_issue=3, metric_value_at_issue=3,
            student_name_snapshot=student.full_name, issued_by_membership=vice,
            issued_at=timezone.now(),
        )
    aligned = Barrier(2)
    original_sync = parents.request_services.sync_activity_notifications
    first_ids = {own_relations[0][0].pk, own_relations[1][0].pk}

    def align_after_first_warning(relation):
        original_sync(relation)
        if relation.pk in first_ids:
            aligned.wait(timeout=10)

    monkeypatch.setattr(
        parents.request_services, "sync_activity_notifications", align_after_first_warning,
    )
    with _application_role():
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            role = cursor.fetchone()[0]

        def read(index):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"SET ROLE {connection.ops.quote_name(role)}")
                    cursor.execute("SET statement_timeout = '10s'")
                client = Client()
                client.force_login(owners[index])
                response = client.get("/api/v1/parent/notifications/")
                assert response.status_code == 200, response.content
                assert response.json()["count"] == 2
                assert {row["relation_id"] for row in response.json()["items"]} == {
                    relation.pk for relation in own_relations[index]
                }
                assert all(row["kind"] == "WARNING" for row in response.json()["items"])
                return response.json()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(read, index) for index in range(2)]
            results = [future.result(timeout=30) for future in futures]
    assert len(results) == 2


def test_publication_withdrawal_during_inbox_sync_scrubs_copied_notice(
    make_school, make_user, make_membership, monkeypatch,
):
    import parents.request_services

    _, relations, _, _, _, client = _family(make_school, make_user)
    relation = relations[0]
    vice = make_membership(make_user("0550078700"), relation.school, ["VICE_PRINCIPAL"])
    publication = parents.request_services.publish_family(
        school=relation.school, membership=vice, student=relation.student,
        title="عنوان أسري خاص قبل الإلغاء", body="محتوى مسموح قبل السحب",
        required_action="طلب متابعة خاص قبل الإلغاء",
    )
    original_sync = parents.request_services.sync_activity_notifications

    def sync_then_revoke_publication(current):
        original_sync(current)
        if current.pk == relation.pk:
            parents.request_services.revoke_publication(
                publication=publication, membership=vice, reason="سحب صناعي أثناء القراءة",
            )

    monkeypatch.setattr(
        parents.request_services, "sync_activity_notifications", sync_then_revoke_publication,
    )
    with _application_role():
        response = client.get(f"/api/v1/parent/notifications/?relation_id={relation.pk}")
        assert response.status_code == 200, response.content
        notice = next(
            row for row in response.json()["items"] if row["kind"] == "FAMILY_PUBLICATION"
        )
        assert notice["body"] == "" and notice["state"] == "ACTION_COMPLETED"
        assert not notice["requires_action"]
        assert "عنوان أسري خاص قبل الإلغاء" not in response.content.decode()
        publications = client.get(f"/api/v1/parent/children/{relation.pk}/publications/")
        assert publications.status_code == 200 and publications.json()["count"] == 0
        assert client.get(f"/api/v1/parent/children/{relation.pk}/").status_code == 200
