"""Independent HTTP, SQL and concurrency proofs of the closed recovery foundation.

No test claims successful ownership proof, recovery execution or old-session
revocation: those operations remain unimplemented while policy approval is absent.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import Client
from django.utils import timezone
from sentry_sdk.scrubber import EventScrubber

from accounts.models import User
from audit.models import AuditLog
from common.errors import ApiError
from common.tenant_rls import clear_tenant_context, tenant_context
from operations.error_tracking import before_send
from parents.models import GlobalMobileChangeRequest, GuardianStudentRelation
from parents.recovery_models import (
    GlobalAccountRecoveryCase,
    RecoveryEvidenceReference,
    RecoveryReviewAuthorization,
    RecoveryReviewDecision,
)
from parents.recovery_purge import recovery_purge_scope
from parents.recovery_services import record_reference, review_case, revoke_reference
from platform_team.models import PlatformStaffMembership
from students.models import Student, StudentPurgeJob
from students.services.purge import purge_student
from students.tasks import run_purge_job
from subscriptions.services.school_purge import permanently_delete_school
from tests.test_parent_recovery_independent_security import _relation, _restricted_role

pytestmark = pytest.mark.django_db(transaction=True)
CENTRAL = "/api/v1/identity-review/parent-recovery/"
PROPOSED = "+966559802099"
SENTINEL = "PRIVATE-RECOVERY-EVIDENCE-DO-NOT-DISCLOSE"


def signed_in(user, school=None):
    client = Client()
    client.force_login(user)
    if school is not None:
        session = client.session
        session["active_school_id"] = school.pk
        session.save()
    return client


@pytest.fixture
def family(make_school, make_user, make_membership):
    guardian = make_user("0559802001")
    requester = make_user("0559802002")
    schools = [make_school(f"مدرسة الاستعادة {i}") for i in range(3)]
    make_membership(requester, schools[0], ["SCHOOL_MANAGER"])
    relations = [
        _relation(school, guardian, requester, status)
        for school, status in zip(
            schools, ["ACTIVE", "SUSPENDED_CONTACT_REVIEW", "REVOKED"], strict=True
        )
    ]
    employment = make_membership(guardian, schools[2], ["TEACHER"])
    grant_owner = make_user("0559802003", is_superuser=True)
    reviewers = [make_user("0559802004"), make_user("0559802005")]
    grants = []
    for reviewer, stage in zip(reviewers, ["FIRST", "SECOND"], strict=True):
        PlatformStaffMembership.objects.create(user=reviewer, role="AUDITOR", status="ACTIVE")
        grants.append(
            RecoveryReviewAuthorization.objects.create(
                reviewer=reviewer,
                granted_by=grant_owner,
                stage=stage,
                authorization_reference=uuid4(),
                expires_at=timezone.now() + timedelta(days=60),
            )
        )
    return {
        "guardian": guardian,
        "requester": requester,
        "schools": schools,
        "relations": relations,
        "employment": employment,
        "grant_owner": grant_owner,
        "reviewers": reviewers,
        "grants": grants,
        "school_client": signed_in(requester, schools[0]),
        "owner_client": signed_in(guardian),
        "review_clients": [signed_in(user) for user in reviewers],
    }


def intake(family, operation="MOBILE_CHANGE", **extra):
    relation = family["relations"][0]
    body = {
        "relation_id": relation.pk,
        "operation": operation,
        "reason": "طلب مستقل لتهيئة مراجعة الحساب",
        "verification_note": SENTINEL,
        "identity_verified": True,
    }
    if operation != "PASSWORD_RECOVERY":
        body["new_mobile"] = PROPOSED
    body.update(extra)
    response = family["school_client"].post(
        f"/api/v1/staff/parents/students/{relation.student_id}/recovery/",
        body,
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    assert response.json()["execution_enabled"] is False
    with tenant_context(school_id=relation.school_id, user_id=family["requester"].pk):
        return GlobalAccountRecoveryCase.objects.get(pk=response.json()["id"])


def refs(family, case):
    rows = []
    for kind in ["ORIGINAL_ACCOUNT_BINDING", "NEW_NUMBER_OWNERSHIP"]:
        row, case = record_reference(
            family["reviewers"][0],
            case.pk,
            kind=kind,
            reference_id=uuid4(),
            expires_at=timezone.now() + timedelta(hours=1),
            expected_version=case.version,
        )
        rows.append(row)
    return rows, case


def first_review(family, case):
    return review_case(
        family["reviewers"][0],
        case.pk,
        stage="FIRST",
        recommendation="CONTINUE_REVIEW",
        expected_version=case.version,
        note=SENTINEL,
    )


def blocked(response, status=423, code="RECOVERY_POLICY_NOT_APPROVED"):
    assert response.status_code == status, response.content
    assert response.json()["code"] == code


def test_closed_execution_at_intake_first_review_and_two_distinct_reviews_preserves_identity(
    family,
):
    """Labels 3/4/7/10/11/12/16: denied execution, not a positive recovery proof."""
    owner = family["guardian"]
    before = User.objects.values("id", "mobile", "password", "is_active").get(pk=owner.pk)
    links = list(GuardianStudentRelation.objects.filter(user=owner).order_by("id").values())
    employment_before = dict(family["employment"].__dict__)
    session_key = family["owner_client"].session.session_key
    client = family["review_clients"][0]
    with _restricted_role():
        case = intake(family)
        path = f"{CENTRAL}{case.pk}/execute/"
        blocked(client.post(path, {}, content_type="application/json"))
        _, case = refs(family, case)
        assert case.version == 3 and case.status == "IDENTITY_REVIEW"
        case = first_review(family, case)
        assert case.status == "AWAITING_SECOND_REVIEW"
        blocked(client.post(path, {}, content_type="application/json"))
        case = review_case(
            family["reviewers"][1],
            case.pk,
            stage="SECOND",
            recommendation="CONTINUE_REVIEW",
            expected_version=case.version,
        )
        assert case.status == "POLICY_BLOCKED"
        for _ in range(2):
            blocked(client.post(path, {}, content_type="application/json"))
        assert (
            User.objects.values("id", "mobile", "password", "is_active").get(pk=owner.pk) == before
        )
        with tenant_context(user_id=owner.pk):
            assert (
                list(GuardianStudentRelation.objects.filter(user=owner).order_by("id").values())
                == links
            )
            family["employment"].refresh_from_db()
            assert family["employment"].status == employment_before["status"] == "ACTIVE"
        assert family["owner_client"].get("/api/v1/auth/me/").status_code == 200
        assert family["owner_client"].session.session_key == session_key
        real_login = Client().post(
            "/api/v1/auth/login/",
            {"mobile": "+966559802001", "password": "Str0ng-Pass-2026"},
            content_type="application/json",
        )
        assert real_login.status_code == 200, real_login.content
    assert RecoveryReviewDecision.objects.filter(case=case).count() == 2


@pytest.mark.parametrize("role", ["OWNER", "SUPPORT", "OPERATIONS_MANAGER", "BILLING", "AUDITOR"])
def test_central_permission_defaults_none_even_with_platform_bypass(family, make_user, role):
    actor = make_user("0559802011", is_superuser=role == "OWNER")
    if role != "OWNER":
        PlatformStaffMembership.objects.create(user=actor, role=role, status="ACTIVE")
    client = signed_in(actor)
    with _restricted_role():
        case = intake(family)
        with tenant_context(user_id=actor.pk, bypass=True):
            assert not GlobalAccountRecoveryCase.objects.exists()
            assert not RecoveryEvidenceReference.objects.exists()
            assert not RecoveryReviewAuthorization.objects.exists()
        blocked(client.get(CENTRAL), 403, "PERMISSION_DENIED")
        blocked(
            client.post(f"{CENTRAL}{case.pk}/execute/", {}, content_type="application/json"),
            403,
            "PERMISSION_DENIED",
        )


@pytest.mark.parametrize("material", ["self", "requester", "school_active", "school_left"])
def test_reviewer_independence_includes_subject_requester_and_all_school_memberships(
    family, make_membership, material
):
    if material == "self":
        actor = family["guardian"]
    elif material == "requester":
        actor = family["requester"]
    else:
        actor = family["reviewers"][0]
        make_membership(
            actor,
            family["schools"][0],
            ["TEACHER"],
            status="ACTIVE" if material == "school_active" else "LEFT",
        )
    if material in {"self", "requester"}:
        PlatformStaffMembership.objects.create(user=actor, role="AUDITOR", status="ACTIVE")
        RecoveryReviewAuthorization.objects.create(
            reviewer=actor,
            granted_by=family["grant_owner"],
            stage="FIRST",
            authorization_reference=uuid4(),
            expires_at=timezone.now() + timedelta(days=1),
        )
    with _restricted_role():
        case = intake(family)
        with pytest.raises(ApiError) as error:
            record_reference(
                actor,
                case.pk,
                kind="ORIGINAL_ACCOUNT_BINDING",
                reference_id=uuid4(),
                expires_at=timezone.now() + timedelta(hours=1),
                expected_version=case.version,
            )
        assert error.value.code == "RECOVERY_REVIEW_CONFLICT"
        with tenant_context(school_id=case.school_id, user_id=actor.pk):
            with pytest.raises(DatabaseError, match="reviewer or account binding"):
                with transaction.atomic():
                    RecoveryReviewDecision.objects.create(
                        case=case,
                        school_id=case.school_id,
                        reviewer=actor,
                        stage="FIRST",
                        recommendation="NEEDS_EVIDENCE",
                        case_version=case.version,
                        evidence_fingerprint="",
                        note_encrypted="",
                    )


@pytest.mark.parametrize("grant_change", ["expired", "revoked", "staff_suspended", "must_change"])
def test_fresh_authority_is_required_for_existing_case(family, grant_change):
    case = intake(family)
    actor = family["reviewers"][0]
    if grant_change == "expired":
        # Provisioning a historical expired grant is owner-only, never an API operation.
        family["grants"][0].delete()
        RecoveryReviewAuthorization.objects.create(
            reviewer=actor,
            granted_by=family["grant_owner"],
            stage="FIRST",
            authorization_reference=uuid4(),
            expires_at=timezone.now() - timedelta(seconds=1),
        )
    elif grant_change == "revoked":
        family["grants"][0].revoked_at = timezone.now()
        family["grants"][0].save(update_fields=["revoked_at"])
    elif grant_change == "staff_suspended":
        PlatformStaffMembership.objects.filter(user=actor).update(status="SUSPENDED")
    else:
        User.objects.filter(pk=actor.pk).update(must_change_password=True)
    with _restricted_role(), tenant_context(user_id=actor.pk, bypass=True):
        assert not GlobalAccountRecoveryCase.objects.filter(pk=case.pk).exists()
        blocked(family["review_clients"][0].get(f"{CENTRAL}{case.pk}/"), 403, "PERMISSION_DENIED")


def test_reference_revocation_resets_version_and_prevents_stale_second_review(family):
    with _restricted_role():
        case = intake(family)
        rows, case = refs(family, case)
        case = first_review(family, case)
        previous = case.version
        case = revoke_reference(
            family["reviewers"][0], case.pk, rows[0].pk, expected_version=case.version
        )
        assert case.version == previous + 1 and case.status == "IDENTITY_REVIEW"
        with pytest.raises(ApiError) as changed:
            review_case(
                family["reviewers"][1],
                case.pk,
                stage="SECOND",
                recommendation="CONTINUE_REVIEW",
                expected_version=previous,
            )
        assert changed.value.code == "RECOVERY_CASE_CHANGED"
        with pytest.raises(ApiError) as missing:
            first_review(family, case)
        assert missing.value.code == "RECOVERY_EVIDENCE_INCOMPLETE"


def test_expired_reference_is_rejected_without_partial_case_change(family):
    with _restricted_role():
        case = intake(family)
        with pytest.raises(ApiError):
            record_reference(
                family["reviewers"][0],
                case.pk,
                kind="ORIGINAL_ACCOUNT_BINDING",
                reference_id=uuid4(),
                expires_at=timezone.now() - timedelta(seconds=1),
                expected_version=case.version,
            )
        with tenant_context(user_id=family["reviewers"][0].pk):
            assert not RecoveryEvidenceReference.objects.filter(case=case).exists()
            case.refresh_from_db()
            assert case.version == 1 and case.status == "PENDING"


def test_actual_expired_evidence_cannot_satisfy_service_or_sql_review(family):
    with _restricted_role():
        case = intake(family, "PASSWORD_RECOVERY")
        _, case = record_reference(
            family["reviewers"][0],
            case.pk,
            kind="ORIGINAL_ACCOUNT_BINDING",
            reference_id=uuid4(),
            expires_at=timezone.now() + timedelta(milliseconds=200),
            expected_version=case.version,
        )
        time.sleep(0.25)
        with pytest.raises(ApiError) as error:
            first_review(family, case)
        assert error.value.code == "RECOVERY_EVIDENCE_INCOMPLETE"
        with tenant_context(school_id=case.school_id, user_id=family["reviewers"][0].pk):
            with pytest.raises(DatabaseError, match="current evidence"):
                with transaction.atomic():
                    RecoveryReviewDecision.objects.create(
                        case=case,
                        school_id=case.school_id,
                        reviewer=family["reviewers"][0],
                        stage="FIRST",
                        recommendation="CONTINUE_REVIEW",
                        case_version=case.version,
                        evidence_fingerprint="f" * 64,
                        note_encrypted="",
                    )


def test_account_password_change_invalidates_case_service_and_sql(family):
    case = intake(family)
    owner = family["guardian"]
    owner.set_password("Owner-New-Current-Password-2026!")
    owner.save(update_fields=["password"])
    with _restricted_role():
        with pytest.raises(ApiError) as error:
            record_reference(
                family["reviewers"][0],
                case.pk,
                kind="ORIGINAL_ACCOUNT_BINDING",
                reference_id=uuid4(),
                expires_at=timezone.now() + timedelta(hours=1),
                expected_version=case.version,
            )
        assert error.value.code == "RECOVERY_ACCOUNT_CHANGED"
        with tenant_context(school_id=case.school_id, user_id=family["reviewers"][0].pk):
            with pytest.raises(DatabaseError, match="account binding"):
                with transaction.atomic():
                    RecoveryReviewDecision.objects.create(
                        case=case,
                        school_id=case.school_id,
                        reviewer=family["reviewers"][0],
                        stage="FIRST",
                        recommendation="NEEDS_EVIDENCE",
                        case_version=case.version,
                        evidence_fingerprint="",
                        note_encrypted="",
                    )


def test_account_mobile_spelling_change_invalidates_bound_case(family):
    case = intake(family)
    # The existing global-mobile guard permits the same canonical number. Even
    # that material database value change must invalidate this case snapshot.
    User.objects.filter(pk=family["guardian"].pk).update(mobile="0559802001")
    with _restricted_role():
        with pytest.raises(ApiError) as error:
            record_reference(
                family["reviewers"][0],
                case.pk,
                kind="ORIGINAL_ACCOUNT_BINDING",
                reference_id=uuid4(),
                expires_at=timezone.now() + timedelta(hours=1),
                expected_version=case.version,
            )
        assert error.value.code == "RECOVERY_ACCOUNT_CHANGED"
        with tenant_context(school_id=case.school_id, user_id=family["reviewers"][0].pk):
            with pytest.raises(DatabaseError, match="account binding"):
                with transaction.atomic():
                    RecoveryReviewDecision.objects.create(
                        case=case,
                        school_id=case.school_id,
                        reviewer=family["reviewers"][0],
                        stage="FIRST",
                        recommendation="NEEDS_EVIDENCE",
                        case_version=case.version,
                        evidence_fingerprint="",
                        note_encrypted="",
                    )


def test_school_cannot_directly_change_global_guardian_mobile(family):
    owner = family["guardian"]
    with _restricted_role():
        intake(family)
        with tenant_context(school_id=family["schools"][0].pk, user_id=family["requester"].pk):
            with pytest.raises(DatabaseError, match="independent verification"):
                with transaction.atomic():
                    User.objects.filter(pk=owner.pk).update(mobile=PROPOSED)
            owner.refresh_from_db()
            assert owner.mobile == "+966559802001"


def test_first_authority_cannot_review_second_stage_and_second_cannot_skip_first(family):
    with _restricted_role():
        case = intake(family)
        _, case = refs(family, case)
        with pytest.raises(ApiError) as missing:
            review_case(
                family["reviewers"][1],
                case.pk,
                stage="SECOND",
                recommendation="CONTINUE_REVIEW",
                expected_version=case.version,
            )
        assert missing.value.code == "RECOVERY_SECOND_REVIEW_REQUIRED"
        case = first_review(family, case)
        with pytest.raises(ApiError) as permission:
            review_case(
                family["reviewers"][0],
                case.pk,
                stage="SECOND",
                recommendation="CONTINUE_REVIEW",
                expected_version=case.version,
            )
        assert permission.value.code == "PERMISSION_DENIED"
        with tenant_context(school_id=case.school_id, user_id=family["reviewers"][0].pk):
            with pytest.raises(DatabaseError, match="responsibility"):
                with transaction.atomic():
                    RecoveryReviewDecision.objects.create(
                        case=case,
                        school_id=case.school_id,
                        reviewer=family["reviewers"][0],
                        stage="SECOND",
                        recommendation="CONTINUE_REVIEW",
                        case_version=case.version,
                        evidence_fingerprint="f" * 64,
                        note_encrypted="",
                    )


def test_failed_reference_audit_rolls_back_metadata_without_any_credential_update(
    family, monkeypatch
):
    case = intake(family)
    before = User.objects.values("id", "mobile", "password").get(pk=case.user_id)

    def fail_audit(*args, **kwargs):
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr("parents.recovery_services.record_event", fail_audit)
    with _restricted_role():
        with pytest.raises(RuntimeError, match="synthetic audit failure"):
            record_reference(
                family["reviewers"][0],
                case.pk,
                kind="ORIGINAL_ACCOUNT_BINDING",
                reference_id=uuid4(),
                expires_at=timezone.now() + timedelta(hours=1),
                expected_version=case.version,
            )
        with tenant_context(user_id=family["reviewers"][0].pk):
            case.refresh_from_db()
            assert case.version == 1 and case.status == "PENDING"
            assert not RecoveryEvidenceReference.objects.filter(case=case).exists()
        assert User.objects.values("id", "mobile", "password").get(pk=case.user_id) == before


def test_existing_number_conflict_never_merges_accounts(family, make_user):
    other = make_user(PROPOSED)
    before = list(
        User.objects.filter(pk__in=[other.pk, family["guardian"].pk])
        .order_by("id")
        .values("id", "mobile", "password")
    )
    with _restricted_role():
        case = intake(family)
        _, case = refs(family, case)
        with pytest.raises(ApiError) as error:
            first_review(family, case)
        assert error.value.code == "RECOVERY_NUMBER_CONFLICT"
        assert (
            list(
                User.objects.filter(pk__in=[other.pk, family["guardian"].pk])
                .order_by("id")
                .values("id", "mobile", "password")
            )
            == before
        )
        with tenant_context(user_id=family["reviewers"][0].pk):
            assert not RecoveryReviewDecision.objects.filter(case=case).exists()


def test_school_has_no_foreign_cases_or_private_evidence_and_audit_has_no_raw_proof(
    family, make_membership, make_user
):
    foreign = make_user("0559802011")
    make_membership(foreign, family["schools"][1], ["SCHOOL_MANAGER"])
    foreign_client = signed_in(foreign, family["schools"][1])
    with _restricted_role():
        case = intake(family)
        rows, case = refs(family, case)
        first_review(family, case)
        response = family["school_client"].get("/api/v1/staff/parents/recovery-cases/")
        assert response.status_code == 200, response.content
        exposed = json.dumps(response.json())
        assert PROPOSED not in exposed and SENTINEL not in exposed
        assert "account_password_fingerprint" not in exposed and "source_mobile_hash" not in exposed
        assert all(str(row.reference_id) not in exposed for row in rows)
        assert "account_id" not in response.json()["results"][0]
        assert "no-store" in response["Cache-Control"]
        foreign_response = foreign_client.get("/api/v1/staff/parents/recovery-cases/")
        assert foreign_response.status_code == 200, foreign_response.content
        assert foreign_response.json()["count"] == 0
        cancelled = foreign_client.post(
            f"/api/v1/staff/parents/recovery-cases/{case.pk}/cancel/",
            {"expected_version": case.version},
            content_type="application/json",
        )
        assert cancelled.status_code == 404, cancelled.content
        for actor in [family["requester"], foreign, family["guardian"]]:
            with tenant_context(school_id=case.school_id, user_id=actor.pk, bypass=False):
                assert not RecoveryEvidenceReference.objects.filter(case=case).exists()
                assert not RecoveryReviewDecision.objects.filter(case=case).exists()
        blocked(
            family["school_client"].get(f"{CENTRAL}{case.pk}/references/"), 403, "PERMISSION_DENIED"
        )
    logs = list(AuditLog.objects.filter(action__startswith="PARENT_RECOVERY_").values("metadata"))
    serialized = json.dumps(logs)
    assert SENTINEL not in serialized and PROPOSED not in serialized
    assert all(str(row.reference_id) not in serialized for row in rows)


def test_password_only_intake_cannot_smuggle_mobile_change(family):
    relation = family["relations"][0]
    with _restricted_role():
        response = family["school_client"].post(
            f"/api/v1/staff/parents/students/{relation.student_id}/recovery/",
            {
                "relation_id": relation.pk,
                "operation": "PASSWORD_RECOVERY",
                "new_mobile": PROPOSED,
                "reason": "طلب استعادة كلمة المرور",
                "verification_note": SENTINEL,
                "identity_verified": True,
            },
            content_type="application/json",
        )
        assert response.status_code == 400, response.content
        with tenant_context(school_id=relation.school_id, user_id=family["requester"].pk):
            assert not GlobalMobileChangeRequest.objects.exists()
            assert not GlobalAccountRecoveryCase.objects.exists()


def test_foreign_school_actor_requires_explicit_central_authority_for_central_case_read(
    family, make_user, make_membership
):
    actor = make_user("0559802011")
    make_membership(actor, family["schools"][1], ["SCHOOL_MANAGER"])
    PlatformStaffMembership.objects.create(user=actor, role="AUDITOR", status="ACTIVE")
    client = signed_in(actor, family["schools"][1])
    case = intake(family)
    with _restricted_role():
        blocked(client.get(f"{CENTRAL}{case.pk}/"), 403, "PERMISSION_DENIED")
    RecoveryReviewAuthorization.objects.create(
        reviewer=actor,
        granted_by=family["grant_owner"],
        stage="FIRST",
        authorization_reference=uuid4(),
        expires_at=timezone.now() + timedelta(days=1),
    )
    with _restricted_role():
        response = client.get(f"{CENTRAL}{case.pk}/")
        assert response.status_code == 200, response.content
        assert response.json()["account_id"] == family["guardian"].pk
        _, case = record_reference(
            actor,
            case.pk,
            kind="ORIGINAL_ACCOUNT_BINDING",
            reference_id=uuid4(),
            expires_at=timezone.now() + timedelta(hours=1),
            expected_version=case.version,
        )
        references = client.get(f"{CENTRAL}{case.pk}/references/")
        assert references.status_code == 200, references.content
        assert references.json()[0]["verified"] is False


@pytest.mark.parametrize(
    "route",
    [
        f"{CENTRAL}{uuid4()}/review/",
        "/api/v1/staff/parents/students/42/recovery/",
    ],
)
def test_recovery_error_event_scrubs_evidence_and_credential_bindings_without_network(route):
    reference = str(uuid4())
    secrets = [
        reference,
        SENTINEL,
        PROPOSED,
        "synthetic-password-fingerprint",
        "synthetic-mobile-fingerprint",
        "synthetic-source-mobile-hash",
    ]
    event = {
        "request": {
            "url": f"https://review.example{route}",
            "data": {"reference_id": reference, "verification_note": SENTINEL},
        },
        "exception": {
            "values": [
                {
                    "type": "RuntimeError",
                    "value": SENTINEL,
                    "stacktrace": {
                        "frames": [{"module": "rest_framework.views", "vars": {"payload": secrets}}]
                    },
                }
            ]
        },
        "extra": {
            "nested": [
                {
                    "reference_id": reference,
                    "note_encrypted": SENTINEL,
                    "note": SENTINEL,
                    "reason": SENTINEL,
                    "new_mobile": PROPOSED,
                    "account_password_fingerprint": secrets[3],
                    "account_mobile_fingerprint": secrets[4],
                    "source_mobile_hash": secrets[5],
                }
            ],
            "error_code": "RECOVERY_POLICY_NOT_APPROVED",
            "request_id": "independent-recovery-request-id",
            "case_id": "safe-case-routing-id",
        },
    }
    EventScrubber().scrub_event(event)
    scrubbed = before_send(event, {})
    assert all(secret not in json.dumps(scrubbed) for secret in secrets)
    assert scrubbed["exception"]["values"][0]["type"] == "RuntimeError"
    assert scrubbed["extra"]["error_code"] == "RECOVERY_POLICY_NOT_APPROVED"
    assert scrubbed["extra"]["request_id"] == "independent-recovery-request-id"
    assert scrubbed["extra"]["case_id"] == "safe-case-routing-id"


def test_malformed_list_body_is_400_without_creating_recovery_records(family):
    relation = family["relations"][0]
    with _restricted_role():
        response = family["school_client"].post(
            f"/api/v1/staff/parents/students/{relation.student_id}/recovery/",
            ["synthetic-invalid-recovery-input"],
            content_type="application/json",
        )
        assert response.status_code == 400, response.content
        with tenant_context(school_id=relation.school_id, user_id=family["requester"].pk):
            assert not GlobalMobileChangeRequest.objects.exists()
            assert not GlobalAccountRecoveryCase.objects.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "APPROVED"),
        ("status", "EXECUTED"),
        ("version", 8),
        ("source_mobile_hash", "f" * 64),
        ("account_password_fingerprint", "e" * 64),
        ("operation", "PASSWORD_RECOVERY"),
    ],
)
def test_raw_sql_cannot_promote_or_rebind_case(family, field, value):
    with _restricted_role():
        case = intake(family)
        with tenant_context(school_id=case.school_id, user_id=family["reviewers"][0].pk):
            with pytest.raises(DatabaseError):
                with transaction.atomic():
                    GlobalAccountRecoveryCase.objects.filter(pk=case.pk).update(**{field: value})
            case.refresh_from_db()
            assert case.status == "PENDING" and case.version == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("new_mobile_encrypted", "replacement-encrypted-value"),
        ("new_mobile_hash", "a" * 64),
        ("reason", "replacement reason"),
        ("verification_note", "replacement proof"),
        ("status", "APPROVED"),
    ],
)
def test_raw_sql_cannot_change_material_intake_after_case_binding(family, field, value):
    with _restricted_role():
        case = intake(family)
        with tenant_context(school_id=case.school_id, user_id=family["requester"].pk):
            with pytest.raises(DatabaseError):
                with transaction.atomic():
                    GlobalMobileChangeRequest.objects.filter(pk=case.source_request_id).update(
                        **{field: value}
                    )


def test_application_cannot_self_grant_and_decisions_are_append_only(family):
    with _restricted_role():
        case = intake(family)
        rows, case = refs(family, case)
        case = first_review(family, case)
        actor = family["reviewers"][0]
        with tenant_context(school_id=case.school_id, user_id=actor.pk, bypass=False):
            decision = RecoveryReviewDecision.objects.get(case=case)
            with pytest.raises(DatabaseError, match="append only"):
                with transaction.atomic():
                    RecoveryReviewDecision.objects.filter(pk=decision.pk).update(
                        recommendation="REJECT"
                    )
            assert RecoveryReviewDecision.objects.filter(pk=decision.pk).delete()[0] == 0
            with pytest.raises(DatabaseError, match="immutable"):
                with transaction.atomic():
                    RecoveryEvidenceReference.objects.filter(pk=rows[0].pk).update(
                        reference_id=uuid4()
                    )
            with pytest.raises(DatabaseError):
                with transaction.atomic():
                    RecoveryReviewAuthorization.objects.create(
                        reviewer=family["requester"],
                        granted_by=actor,
                        stage="SECOND",
                        authorization_reference=uuid4(),
                        expires_at=timezone.now() + timedelta(days=1),
                    )
            assert (
                RecoveryReviewAuthorization.objects.filter(reviewer=actor).update(
                    revoked_at=timezone.now()
                )
                == 0
            )


def test_scoped_purge_cannot_read_other_student_or_write_reviews(family):
    case = intake(family)
    with _restricted_role():
        _, case = refs(family, case)
        case = first_review(family, case)
        with tenant_context(school_id=case.school_id, user_id=family["requester"].pk):
            with (
                transaction.atomic(),
                recovery_purge_scope(
                    school_id=case.school_id,
                    actor_id=family["requester"].pk,
                    student_id=family["relations"][1].student_id,
                ),
            ):
                assert not RecoveryEvidenceReference.objects.filter(case=case).exists()
            with (
                transaction.atomic(),
                recovery_purge_scope(
                    school_id=case.school_id,
                    actor_id=family["requester"].pk,
                    student_id=case.student_id,
                ),
            ):
                assert RecoveryEvidenceReference.objects.filter(case=case).count() == 2
                with pytest.raises(DatabaseError):
                    with transaction.atomic():
                        GlobalAccountRecoveryCase.objects.filter(pk=case.pk).update(
                            status="POLICY_BLOCKED"
                        )
                RecoveryReviewDecision.objects.filter(case=case).delete()
                RecoveryEvidenceReference.objects.filter(case=case).delete()
                assert GlobalAccountRecoveryCase.objects.filter(pk=case.pk).delete()[0] == 1
            assert not GlobalAccountRecoveryCase.objects.filter(pk=case.pk).exists()


@pytest.mark.parametrize(
    "kind,actor_key,session_user",
    [
        ("SCHOOL", "grant_owner", "requester"),
        ("STUDENT", "requester", "reviewer"),
        ("STUDENT", "requester", None),
    ],
)
def test_purge_actor_cannot_be_impersonated_by_setting_purpose_gucs(
    family, kind, actor_key, session_user
):
    case = intake(family)
    with _restricted_role():
        _, case = refs(family, case)
        current_actor = (
            family["reviewers"][0] if session_user == "reviewer" else family.get(session_user)
        )
        with tenant_context(
            school_id=case.school_id, user_id=current_actor.pk if current_actor else None
        ):
            with (
                transaction.atomic(),
                recovery_purge_scope(
                    school_id=case.school_id,
                    actor_id=family[actor_key].pk,
                    student_id=case.student_id if kind == "STUDENT" else None,
                ),
            ):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT public.xmansx_recovery_purge_allowed(%s, %s)",
                        [case.school_id, case.student_id],
                    )
                    assert cursor.fetchone()[0] is False


@pytest.mark.parametrize("valid_job", [True, False])
def test_worker_empty_user_requires_actual_running_job_bound_to_actor_school_and_student(
    family, valid_job
):
    case = intake(family)
    job = StudentPurgeJob.objects.create(
        school_id=case.school_id,
        created_by=family["requester"],
        status="RUNNING" if valid_job else "PENDING",
        student_ids=[case.student_id],
    )
    with _restricted_role():
        _, case = refs(family, case)
        with tenant_context(school_id=case.school_id):
            with (
                transaction.atomic(),
                recovery_purge_scope(
                    school_id=case.school_id,
                    actor_id=family["requester"].pk,
                    student_id=case.student_id,
                    job_id=job.pk,
                ),
            ):
                count = RecoveryEvidenceReference.objects.filter(case=case).count()
                assert count == (2 if valid_job else 0)
                if valid_job:
                    RecoveryEvidenceReference.objects.filter(case=case).delete()
                    assert GlobalAccountRecoveryCase.objects.filter(pk=case.pk).delete()[0] == 1


@pytest.mark.parametrize("workflow", ["synchronous_student", "worker_student", "platform_school"])
def test_existing_actual_purge_workflows_remove_recovery_metadata_under_nonbypass_role(
    family, workflow
):
    case = intake(family)
    guardian = family["guardian"]
    before = User.objects.values("id", "mobile", "password").get(pk=guardian.pk)
    student = Student.objects.get(pk=case.student_id)
    student.status = "GRADUATED"
    student.save(update_fields=["status"])
    job = None
    if workflow == "worker_student":
        job = StudentPurgeJob.objects.create(
            school=student.school,
            created_by=family["requester"],
            status="PENDING",
            student_ids=[student.pk],
            total_students=1,
        )
    with _restricted_role():
        rows, case = refs(family, case)
        case = first_review(family, case)
        if workflow == "synchronous_student":
            with tenant_context(school_id=case.school_id, user_id=family["requester"].pk):
                deleted, storage_ok, storage_failed = purge_student(
                    student, actor=family["requester"]
                )
                assert deleted > 0 and storage_ok == storage_failed == 0
        elif workflow == "worker_student":
            assert run_purge_job(job.pk) == "COMPLETED"
            with tenant_context(school_id=case.school_id):
                job.refresh_from_db()
                assert job.deleted_students == 1 and job.failed_students == 0
                assert job.student_ids == []
        else:
            with tenant_context(bypass=True):
                result = permanently_delete_school(
                    school_id=case.school_id,
                    confirmation_name=family["schools"][0].name,
                    actor=family["grant_owner"],
                )
                assert result["deleted"] is True
        assert User.objects.values("id", "mobile", "password").get(pk=guardian.pk) == before
        with tenant_context(user_id=guardian.pk):
            assert set(
                GuardianStudentRelation.objects.filter(user=guardian).values_list(
                    "status", flat=True
                )
            ) == {"SUSPENDED_CONTACT_REVIEW", "REVOKED"}
            family["employment"].refresh_from_db()
            assert family["employment"].status == "ACTIVE"
    assert not Student.objects.filter(pk=case.student_id).exists()
    assert not GlobalAccountRecoveryCase.objects.filter(pk=case.pk).exists()
    assert not RecoveryEvidenceReference.objects.filter(pk__in=[row.pk for row in rows]).exists()
    assert not RecoveryReviewDecision.objects.filter(case_id=case.pk).exists()
    assert not GlobalMobileChangeRequest.objects.filter(pk=case.source_request_id).exists()


def test_simultaneous_first_reviews_record_one_decision_under_actual_rls(family):
    with _restricted_role() as role:
        case = intake(family)
        _, case = refs(family, case)
        actor = family["reviewers"][0]

        def attempt():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"SET ROLE {role}")
                clear_tenant_context()
                try:
                    result = review_case(
                        actor,
                        case.pk,
                        stage="FIRST",
                        recommendation="CONTINUE_REVIEW",
                        expected_version=case.version,
                    )
                    return result.status
                except ApiError as error:
                    return error.code
            finally:
                with connection.cursor() as cursor:
                    cursor.execute("RESET ROLE")
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: attempt(), range(2)))
        assert sorted(outcomes) == ["AWAITING_SECOND_REVIEW", "RECOVERY_REVIEW_ALREADY_RECORDED"]
        with tenant_context(user_id=actor.pk):
            assert RecoveryReviewDecision.objects.filter(case=case).count() == 1
