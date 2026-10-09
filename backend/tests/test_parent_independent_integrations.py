"""Independent legacy integration proofs, using real transactions and bounded races."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from django.db import DatabaseError, close_old_connections, connection, connections, transaction
from django.test import Client
from django.utils import timezone

from accounts.models import User
from audit.models import AuditLog
from common.errors import ApiError
from common.tenant_rls import clear_tenant_context, tenant_context
from memberships.models import SchoolMembership
from parents.models import (
    GuardianActivation,
    GuardianContactReview,
    GuardianStudentRelation,
    ParentNotification,
)
from parents.security import contact_hash
from students.models import (
    ImportJobStatus,
    StudentEnrollment,
    StudentImportJob,
    StudentImportRow,
)
from students.services.imports.commit import commit_import
from students.services.imports.comparison import categorize_rows
from tests import test_parent_portal as journeys
from tests import test_student_reconciliation_audit as reconciliation_cases
from tests.test_parent_contact_security import _relation, _student

portal_env = journeys.portal_env
parent_reconciliation_case = reconciliation_cases.parent_reconciliation_case
pytestmark = pytest.mark.django_db


def _token(decision):
    return parse_qs(urlsplit(decision["activation_url"]).fragment)["token"][0]


def _stage_noor(env, *, mobile="+966551900009", guardian_name=None):
    from students.services.imports.normalization import normalize_guardian_mobile

    student = env["student"]
    student.refresh_from_db()
    normalized = {
        "row_number": 2,
        "national_id_encrypted": student.national_id_encrypted,
        "national_id_hash": student.national_id_lookup_hash,
        "national_id_masked": student.national_id_masked,
        "student_number": student.student_number,
        "full_name": student.full_name,
        "guardian_name": student.guardian_name if guardian_name is None else guardian_name,
        "guardian_mobile": normalize_guardian_mobile(mobile),
        "grade_code": env["grade"].code,
        "grade_name": env["grade"].name,
        "grade_sequence": env["grade"].sequence,
        "section_code": env["section"].code,
        "section_name": env["section"].name,
        "department": env["section"].department,
        "errors": [],
    }
    staged = categorize_rows(env["school"], env["year"], [normalized])["rows"][0]
    job = StudentImportJob.objects.create(
        school=env["school"],
        academic_year=env["year"],
        uploaded_by=env["actor"],
        original_filename="independent-contact-race.xlsx",
        status=ImportJobStatus.READY_FOR_REVIEW,
    )
    StudentImportRow.objects.create(
        job=job,
        row_number=staged["row_number"],
        status=staged["status"],
        national_id_encrypted=staged["national_id_encrypted"],
        national_id_hash=staged["national_id_hash"],
        data={
            key: value
            for key, value in staged.items()
            if key not in {"national_id_encrypted", "national_id_hash", "errors", "row_number"}
        },
    )
    return job


def _thread_scope(env, callback, wrapper=None):
    close_old_connections()
    try:
        with tenant_context(school_id=env["school"].id, user_id=env["actor"].id):
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '15s'")
            if wrapper is None:
                return callback()
            with connection.execute_wrapper(wrapper):
                return callback()
    finally:
        connections.close_all()


def _ordered_school_race(env, first, second):
    """Release the first holder only when the second really attempts its school lock."""
    held, second_attempted = Event(), Event()

    def pause_first(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if "schools_school" in sql and "FOR " in sql.upper() and not held.is_set():
            held.set()
            assert second_attempted.wait(timeout=10), "second worker never attempted school lock"
        return result

    def announce_second(execute, sql, params, many, context):
        if "schools_school" in sql and "FOR " in sql.upper():
            second_attempted.set()
        return execute(sql, params, many, context)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_result = pool.submit(_thread_scope, env, first, pause_first)
        assert held.wait(timeout=10), "first worker never acquired school lock"
        second_result = pool.submit(_thread_scope, env, second, announce_second)
        return first_result.result(timeout=25), second_result.result(timeout=25)


def test_legacy_student_patch_retains_contact_verification_and_noop_evidence(portal_env):
    env = portal_env
    relation, _, _ = journeys.activate(env)
    student = env["student"]
    previous_mobile = student.guardian_mobile
    before = GuardianContactReview.objects.filter(student=student).count()
    proof = "تحققت المدرسة حضورياً من الوثائق الخاصة وصلة القرابة"
    reason = "تصحيح رقم التواصل بعد تحقق حضوري"
    response = env["staff"].patch(
        f"/api/v1/students/{student.id}/",
        {
            "guardian_mobile": "+966551900009",
            "contact_identity_verified": True,
            "contact_change_reason": reason,
            "contact_verification_note": proof,
        },
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    student.refresh_from_db()
    relation.refresh_from_db()
    assert relation.status == "SUSPENDED_CONTACT_REVIEW"
    assert GuardianContactReview.objects.filter(student=student).count() == before + 1
    review = GuardianContactReview.objects.get(
        student=student, current_revision=student.guardian_contact_revision
    )
    assert review.source == "MANUAL"
    assert review.actor_id == env["actor"].id
    assert review.reason == reason
    assert review.verification_note == proof
    assert review.previous_mobile_hash == contact_hash(previous_mobile)
    assert review.current_mobile_hash == contact_hash(student.guardian_mobile)
    assert not AuditLog.objects.filter(metadata__icontains=proof).exists()
    revision = student.guardian_contact_revision
    response = env["staff"].patch(
        f"/api/v1/students/{student.id}/",
        {
            "guardian_mobile": "0551900009",
            "contact_identity_verified": True,
            "contact_change_reason": "تأكيد الصيغة نفسها",
            "contact_verification_note": "دليل بديل لا يكتب",
        },
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    student.refresh_from_db()
    review.refresh_from_db()
    assert student.guardian_contact_revision == revision
    assert GuardianContactReview.objects.filter(student=student).count() == before + 1
    assert review.verification_note == proof and review.reason == reason


@pytest.mark.parametrize("existing_account", [False, True])
def test_corrected_student_identity_invalidates_inspection_and_activation_without_account_effect(
    portal_env,
    make_user,
    make_membership,
    existing_account,
):
    env = portal_env
    existing = None
    if existing_account:
        existing = make_user(env["student"].guardian_mobile)
        make_membership(existing, env["school"], ["TEACHER"])
        env["parent"].force_login(existing)
    item, _ = journeys.register(env)
    token = _token(journeys.approve(env, item))
    account_count = User.objects.count()
    original_password = existing.password if existing else None
    response = env["staff"].patch(
        f"/api/v1/students/{env['student'].id}/",
        {"national_id": "PCORRECT123"},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    check = journeys.post(env["parent"], "/api/v1/parent/activation/check/", {"token": token})
    assert check.status_code == 409, check.content
    assert check.json()["code"] == "ACTIVATION_INVALID"
    complete = journeys.post(
        env["parent"],
        "/api/v1/parent/activation/",
        {"token": token, "new_password": journeys.PASSWORD, "confirm_password": journeys.PASSWORD},
    )
    assert complete.status_code == 409, complete.content
    assert complete.json()["code"] == "ACTIVATION_INVALID"
    assert User.objects.count() == account_count
    assert not GuardianStudentRelation.objects.filter(student=env["student"]).exists()
    assert GuardianActivation.objects.get(request=item).used_at is None
    if existing:
        existing.refresh_from_db()
        assert existing.password == original_password
        assert SchoolMembership.objects.filter(
            user=existing, school=env["school"], roles__role="TEACHER"
        ).exists()


@pytest.mark.parametrize("field", ["user_id", "student_id", "school_id"])
def test_real_nobypass_role_cannot_reassign_approved_relation_identity(
    make_school,
    make_user,
    field,
):
    school = make_school()
    other_school = make_school()
    owner = make_user("0551100001")
    other_owner = make_user("0551100002")
    actor = make_user("0551100003")
    student = _student(school)
    other_student = _student(school, "b")
    foreign_student = _student(other_school, "c")
    relation = _relation(student, owner, actor)
    notice = ParentNotification.objects.create(
        school=school,
        relation=relation,
        user=owner,
        kind="SECURITY_PROOF",
        dedup_key="immutable-owner",
        title="إشعار صاحب العلاقة الأصلي",
    )
    changes = {
        "user_id": other_owner.id,
        "student_id": other_student.id,
        "school_id": other_school.id,
    }
    role = connection.ops.quote_name(f"independent_parent_{uuid4().hex}")
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
        with tenant_context(school_id=school.id, user_id=actor.id):
            with pytest.raises(DatabaseError, match="guardian relation identity is immutable"):
                with transaction.atomic():
                    if field == "school_id":
                        # Platform maintenance explicitly bypasses tenant RLS,
                        # but a consistent school/student pair must not reparent
                        # an existing relation or its historical dependents.
                        with tenant_context(bypass=True, user_id=actor.id):
                            GuardianStudentRelation.objects.filter(pk=relation.pk).update(
                                school_id=other_school.id,
                                student_id=foreign_student.id,
                                status="REVOKED",
                            )
                    else:
                        GuardianStudentRelation.objects.filter(pk=relation.pk).update(
                            **{field: changes[field]}
                        )
            relation.refresh_from_db()
            notice.refresh_from_db()
            assert (relation.user_id, relation.student_id, relation.school_id) == (
                owner.id,
                student.id,
                school.id,
            )
            assert notice.relation_id == relation.id and notice.user_id == owner.id
            # Legitimate status changes continue through the same guarded table.
            GuardianStudentRelation.objects.filter(pk=relation.pk).update(status="REVOKED")
            assert GuardianStudentRelation.objects.get(pk=relation.pk).status == "REVOKED"
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP OWNED BY {role}")
            cursor.execute(f"DROP ROLE IF EXISTS {role}")
        clear_tenant_context()


def test_parent_is_denied_actual_existing_gate_list_and_release_routes(portal_env):
    env = portal_env
    journeys.activate(env)
    assert env["parent"].get("/api/v1/gate/student-leaves/").status_code == 403
    assert (
        journeys.post(env["parent"], "/api/v1/gate/student-leaves/1/release/", {}).status_code
        == 403
    )


@pytest.mark.parametrize(
    "mobile,guardian_name,changed",
    [
        ("", None, False),
        ("invalid", None, False),
        ("٠٥٥١٩٠٠٠٠٣", None, False),
        ("00966551900003", None, False),
        ("+966551900009", None, True),
        ("+966551900003", "ولي أمر مختلف جوهرياً", True),
    ],
)
def test_real_noor_contact_variants_and_repeat_commit_preserve_security_contract(
    portal_env,
    mobile,
    guardian_name,
    changed,
):
    env = portal_env
    relation, _, _ = journeys.activate(env)
    item, _ = journeys.register(env)
    journeys.approve(env, item)
    student = env["student"]
    initial_revision = student.guardian_contact_revision
    initial_mobile = student.guardian_mobile
    reviews = GuardianContactReview.objects.filter(student=student).count()
    notices = ParentNotification.objects.filter(relation=relation).count()
    original_global_mobile = relation.user.mobile
    job = _stage_noor(env, mobile=mobile, guardian_name=guardian_name)
    assert commit_import(job_id=job.id, actor=env["actor"]).status == ImportJobStatus.COMPLETED
    student.refresh_from_db()
    relation.refresh_from_db()
    item.refresh_from_db()
    activation = GuardianActivation.objects.get(request=item)
    assert student.guardian_contact_revision == initial_revision + int(changed)
    assert relation.user.mobile == original_global_mobile
    assert relation.status == ("SUSPENDED_CONTACT_REVIEW" if changed else "ACTIVE")
    assert item.status == ("NEEDS_INFO" if changed else "APPROVED")
    assert (activation.revoked_at is not None) == changed
    assert GuardianContactReview.objects.filter(student=student).count() == reviews + int(changed)
    assert ParentNotification.objects.filter(relation=relation).count() == notices + int(changed)
    if mobile in ("", "invalid", "٠٥٥١٩٠٠٠٠٣", "00966551900003"):
        assert student.guardian_mobile == initial_mobile
    with pytest.raises(ApiError) as duplicate:
        commit_import(job_id=job.id, actor=env["actor"])
    assert duplicate.value.code == "IMPORT_ALREADY_COMMITTED"
    assert GuardianContactReview.objects.filter(student=student).count() == reviews + int(changed)
    # A fresh duplicate import of identical current contact does not increment again.
    repeated = _stage_noor(env, mobile=student.guardian_mobile, guardian_name=student.guardian_name)
    assert commit_import(job_id=repeated.id, actor=env["actor"]).status == ImportJobStatus.COMPLETED
    student.refresh_from_db()
    assert student.guardian_contact_revision == initial_revision + int(changed)
    assert GuardianContactReview.objects.filter(student=student).count() == reviews + int(changed)


def test_real_noor_failure_after_contact_write_rolls_back_grant_token_review_and_job(
    portal_env,
    monkeypatch,
):
    from students.services.imports import commit

    env = portal_env
    relation, _, _ = journeys.activate(env)
    item, _ = journeys.register(env)
    journeys.approve(env, item)
    activation = GuardianActivation.objects.get(request=item)
    student = env["student"]
    initial_contact = (student.guardian_mobile, student.guardian_contact_revision)
    reviews = GuardianContactReview.objects.filter(student=student).count()
    notices = ParentNotification.objects.filter(relation=relation).count()
    job = _stage_noor(env)
    audit = commit.record_event

    def fail_after_real_write(action, **kwargs):
        audit(action, **kwargs)
        if action == "STUDENT_UPDATED":
            raise RuntimeError("independent failure after real contact write")

    monkeypatch.setattr(commit, "record_event", fail_after_real_write)
    with pytest.raises(RuntimeError, match="failure after real contact write"):
        commit_import(job_id=job.id, actor=env["actor"])
    student.refresh_from_db()
    relation.refresh_from_db()
    item.refresh_from_db()
    activation.refresh_from_db()
    job.refresh_from_db()
    assert (student.guardian_mobile, student.guardian_contact_revision) == initial_contact
    assert relation.status == "ACTIVE"
    assert item.status == "APPROVED" and activation.revoked_at is None
    assert GuardianContactReview.objects.filter(student=student).count() == reviews
    assert ParentNotification.objects.filter(relation=relation).count() == notices
    assert job.status == ImportJobStatus.READY_FOR_REVIEW and job.rows.count() == 1


@pytest.mark.parametrize("provider", ["DREAMS", "MSEGAT"])
def test_queued_sms_contact_change_rechecks_and_explicit_retry_uses_current_number(
    role_client,
    provider,
):
    from school_sms.models import AbsenceSmsNotice
    from school_sms.providers import SmsProviderResult
    from school_sms.tasks import send_absence_notice
    from tests.test_school_sms import SEND_URL, _absence, _integration

    staff, school, _ = role_client(["SCHOOL_MANAGER"])
    student, _, day = _absence(school)
    old_mobile = student.guardian_mobile
    assert _integration(staff, provider=provider).status_code == 200
    with patch("school_sms.tasks.send_absence_notice.delay") as enqueue:
        queued = journeys.post(
            staff, SEND_URL, {"date": day.isoformat(), "student_ids": [student.id]}
        )
    assert queued.status_code == 202 and queued.json()["queued"] == 1
    enqueue.assert_called_once()
    notice = AbsenceSmsNotice.objects.get(student=student)
    assert notice.recipient_hash == contact_hash(old_mobile)
    student.guardian_mobile = "+966500000002"
    student.save(update_fields=["guardian_mobile"])
    with patch("school_sms.tasks.send_sms") as send:
        assert send_absence_notice(notice.id) == "failed"
    send.assert_not_called()
    notice.refresh_from_db()
    assert notice.status == "FAILED" and notice.failure_code == "PRE_SEND_STATE_CHANGED"
    assert notice.recipient_hash == contact_hash(old_mobile)
    with patch("school_sms.tasks.send_sms", return_value=SmsProviderResult()) as send:
        retried = journeys.post(
            staff, SEND_URL, {"date": day.isoformat(), "student_ids": [student.id]}
        )
    assert retried.status_code == 202 and retried.json()["queued"] == 1
    send.assert_called_once()
    assert send.call_args.kwargs["provider"] == provider
    assert send.call_args.kwargs["mobile"] == student.guardian_mobile
    notice.refresh_from_db()
    assert notice.recipient_hash == contact_hash(student.guardian_mobile)
    assert notice.status == "ACCEPTED" and notice.attempts == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("parent_operation", ["approval", "activation"])
@pytest.mark.parametrize("first_operation", ["noor", "parent"])
def test_real_noor_serializes_new_registration_approval_and_activation(
    portal_env,
    parent_operation,
    first_operation,
):
    from parents import services

    env = portal_env
    item, _ = journeys.register(env)
    token = _token(journeys.approve(env, item)) if parent_operation == "activation" else None
    membership = SchoolMembership.objects.get(user=env["actor"], school=env["school"])
    job = _stage_noor(env)
    initial_revision = env["student"].guardian_contact_revision

    def noor():
        return commit_import(job_id=job.id, actor=env["actor"]).status

    def parent():
        try:
            if parent_operation == "approval":
                services.decide_registration(
                    school=env["school"],
                    membership=membership,
                    request_id=item.id,
                    data={
                        "decision": "APPROVE",
                        "student_id": env["student"].id,
                        "verification_note": "تحقق موثق من الصفة والهوية الحالية",
                        "contact_bound": True,
                        "delivery": "MANUAL",
                    },
                )
            else:
                services.complete_activation(
                    token=token,
                    new_password=journeys.PASSWORD,
                    confirm_password=journeys.PASSWORD,
                )
            return "accepted"
        except ApiError as error:
            return error.code

    operations = {"noor": noor, "parent": parent}
    second_operation = "parent" if first_operation == "noor" else "noor"
    first, second = _ordered_school_race(
        env, operations[first_operation], operations[second_operation]
    )
    results = {first_operation: first, second_operation: second}
    assert results["noor"] == ImportJobStatus.COMPLETED
    if first_operation == "noor":
        assert results["parent"] == (
            "CONTACT_MISMATCH" if parent_operation == "approval" else "ACTIVATION_INVALID"
        )
    else:
        assert results["parent"] == "accepted"
    student = env["student"]
    student.refresh_from_db()
    item.refresh_from_db()
    assert student.guardian_mobile == "+966551900009"
    assert student.guardian_contact_revision == initial_revision + 1
    assert not GuardianStudentRelation.objects.filter(student=student, status="ACTIVE").exists()
    assert GuardianContactReview.objects.filter(student=student, source="NOOR_IMPORT").count() == 1
    if parent_operation == "activation" and first_operation == "parent":
        assert (
            GuardianStudentRelation.objects.get(student=student).status
            == "SUSPENDED_CONTACT_REVIEW"
        )
    else:
        assert not GuardianStudentRelation.objects.filter(student=student).exists()
        assert not User.objects.filter(mobile="+966551900003").exists()
    if first_operation == "parent" and parent_operation == "approval":
        assert item.status == "NEEDS_INFO"
        assert GuardianActivation.objects.get(request=item).revoked_at is not None


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("merge_operation", ["manual", "reconciliation"])
def test_merge_and_real_noor_share_school_before_student_lock_order(
    parent_reconciliation_case,
    merge_operation,
):
    from students.services.manual_merge import apply_manual_merge, preview_manual_merge
    from students.services.reconciliation import reconcile_group

    school, target, source, completed_job, actor = parent_reconciliation_case
    enrollment = StudentEnrollment.objects.select_related("grade", "section", "academic_year").get(
        student=target, status="ACTIVE"
    )
    env = {
        "school": school,
        "actor": actor,
        "student": target,
        "year": enrollment.academic_year,
        "grade": enrollment.grade,
        "section": enrollment.section,
    }
    preview = preview_manual_merge(school=school, actor=actor, ids=[target.id, source.id])
    assert preview["can_merge"], preview["blockers"]
    job = _stage_noor(env, mobile="+966551900009")
    merge_locked, noor_school_attempted, noor_school_locked = Event(), Event(), Event()
    first_table = []

    def pause_merge(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if "FOR " in sql.upper() and not merge_locked.is_set():
            first_table.append("school" if "schools_school" in sql else "student")
            merge_locked.set()
            if first_table[0] == "student":
                assert noor_school_locked.wait(timeout=10)
            else:
                assert noor_school_attempted.wait(timeout=10)
        return result

    def watch_noor(execute, sql, params, many, context):
        school_lock = "schools_school" in sql and "FOR UPDATE" in sql.upper()
        if school_lock:
            noor_school_attempted.set()
        result = execute(sql, params, many, context)
        if school_lock:
            noor_school_locked.set()
        return result

    def merge():
        if merge_operation == "manual":
            return apply_manual_merge(
                school=school, actor=actor, request=None, token=preview["confirmation_token"]
            )
        return reconcile_group(
            [target.id, source.id], school_id=school.id, expected_import_job_id=completed_job.id
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        merged = pool.submit(_thread_scope, env, merge, pause_merge)
        assert merge_locked.wait(timeout=10)
        imported = pool.submit(
            _thread_scope, env, lambda: commit_import(job_id=job.id, actor=actor), watch_noor
        )
        result = merged.result(timeout=25)
        assert imported.result(timeout=25).status == ImportJobStatus.COMPLETED
    assert first_table == ["school"]
    source.refresh_from_db()
    target.refresh_from_db()
    assert source.status == "ARCHIVED" and source.merged_into_id == target.id
    assert target.guardian_mobile == "+966551900009"
    assert result["target_id"] == target.id


@pytest.mark.django_db(transaction=True)
def test_initial_document_creation_and_parent_acknowledgement_do_not_deadlock(
    portal_env, monkeypatch
):
    from documents.models import GeneratedDocument
    from documents.services import generation
    from parents.request_models import WarningAcknowledgement
    from student_warnings.models import StudentWarning
    from tests.test_parent_requests import VALID_PDF

    env = portal_env
    relation, _, _ = journeys.activate(env)
    membership = SchoolMembership.objects.get(user=env["actor"], school=env["school"])
    warning = StudentWarning.objects.create(
        school=env["school"],
        student=env["student"],
        academic_year=env["year"],
        warning_type="UNEXCUSED_FULL_DAY_ABSENCE",
        level="LEVEL_1",
        status="ISSUED",
        threshold_at_issue=3,
        metric_value_at_issue=3,
        student_name_snapshot=env["student"].full_name,
        issued_by_membership=membership,
        issued_at=timezone.now(),
    )
    monkeypatch.setattr(generation, "_render", lambda **kwargs: VALID_PDF)
    document_locked, parent_school_attempted, parent_student_locked = Event(), Event(), Event()
    first_table = []

    def pause_creation(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if "FOR UPDATE" in sql.upper() and not document_locked.is_set():
            first_table.append("school" if "schools_school" in sql else "warning")
            document_locked.set()
            awaited = (
                parent_school_attempted if first_table[0] == "school" else parent_student_locked
            )
            assert awaited.wait(timeout=10), "parent did not reach the conflicting lock"
        return result

    def watch_parent(execute, sql, params, many, context):
        if "schools_school" in sql and "FOR KEY SHARE" in sql.upper():
            parent_school_attempted.set()
        result = execute(sql, params, many, context)
        if "students_student" in sql and "FOR UPDATE" in sql.upper():
            parent_student_locked.set()
        return result

    def create():
        return generation.generate_document(
            school=env["school"],
            membership=membership,
            student=env["student"],
            document_type="WARNING_LEVEL_1",
            warning_id=warning.id,
        ).id

    def acknowledge():
        client = Client()
        client.force_login(relation.user)
        return journeys.post(
            client, f"/api/v1/parent/children/{relation.id}/warnings/{warning.id}/acknowledge/", {}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        created = pool.submit(_thread_scope, env, create, pause_creation)
        assert document_locked.wait(timeout=10)
        acknowledged = pool.submit(_thread_scope, env, acknowledge, watch_parent)
        document_id = created.result(timeout=25)
        assert acknowledged.result(timeout=25) == 200
    assert first_table == ["school"]
    document = GeneratedDocument.objects.get(pk=document_id)
    assert document.status == "READY" and document.file.storage.exists(document.file.name)
    assert WarningAcknowledgement.objects.filter(relation=relation, warning=warning).count() == 1
