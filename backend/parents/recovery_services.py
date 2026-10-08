"""Central review preparation only; credential execution is deliberately absent."""

import hashlib
import hmac
from contextlib import contextmanager
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from audit.services import record_event
from common.errors import ApiError
from common.tenant_rls import tenant_context
from memberships.models import SchoolMembership
from parents.access import lock_parent_school, not_found
from parents.recovery_models import (
    GlobalAccountRecoveryCase,
    RecoveryEvidenceKind,
    RecoveryEvidenceReference,
    RecoveryOperation,
    RecoveryRecommendation,
    RecoveryReviewAuthorization,
    RecoveryReviewDecision,
    RecoveryReviewStage,
    RecoveryStatus,
)
from parents.security import decrypt_value, encrypt_value
from platform_team.models import PlatformStaffMembership, PlatformStaffStatus

TERMINAL = {RecoveryStatus.REJECTED, RecoveryStatus.EXPIRED, RecoveryStatus.CANCELLED}


def credential_fingerprint(user):
    return hashlib.sha256(user.password.encode()).hexdigest()


def login_mobile_fingerprint(user):
    return hashlib.sha256(user.mobile.encode()).hexdigest()


def require_reviewer(actor, *, stage=None):
    """No owner/capability shortcut. Recheck current, explicit central employment/grant."""
    if not getattr(actor, "is_authenticated", False):
        raise ApiError("PERMISSION_DENIED", "يلزم مراجع مركزي مخول.", status_code=403)
    with tenant_context(user_id=actor.id):
        grant = RecoveryReviewAuthorization.objects.filter(
            reviewer_id=actor.id, revoked_at__isnull=True, expires_at__gt=timezone.now()
        ).first()
        employed = PlatformStaffMembership.objects.filter(
            user_id=actor.id,
            status=PlatformStaffStatus.ACTIVE,
            user__is_active=True,
            user__must_change_password=False,
        ).exists()
    if grant is None or not employed or (stage is not None and grant.stage != stage):
        raise ApiError("PERMISSION_DENIED", "لا يوجد تفويض مستقل لهذه المراجعة.", status_code=403)
    return grant


def open_case_from_source(source, *, operation=RecoveryOperation.MOBILE_CHANGE):
    """Called inside the authorized school's locked intake transaction."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Recovery intake requires a school-scoped atomic transaction")
    if operation not in RecoveryOperation.values:
        raise ApiError("VALIDATION_ERROR", "نوع طلب الاستعادة غير صالح.")
    user = User.objects.get(id=source.user_id)
    case, created = GlobalAccountRecoveryCase.objects.get_or_create(
        source_request=source,
        defaults={
            "school_id": source.school_id,
            "student_id": source.student_id,
            "user_id": source.user_id,
            "requested_by_id": source.requested_by_id,
            "operation": operation,
            "source_mobile_hash": source.new_mobile_hash,
            "account_password_fingerprint": credential_fingerprint(user),
            "account_mobile_fingerprint": login_mobile_fingerprint(user),
            "expires_at": timezone.now() + timedelta(days=30),
        },
    )
    if not created and case.operation != operation:
        raise ApiError("RECOVERY_CASE_CONFLICT", "الطلب مرتبط بقضية مختلفة.", status_code=409)
    if created:
        record_event(
            "PARENT_RECOVERY_CASE_OPENED",
            school=source.school,
            actor=User.objects.get(id=source.requested_by_id),
            target_type="GlobalAccountRecoveryCase",
            target_id=case.id,
            metadata={"operation": operation, "execution_enabled": False},
        )
    return case


@contextmanager
def recovery_scope(actor, case_id, *, write=False):
    require_reviewer(actor)
    with tenant_context(user_id=actor.id):
        index = GlobalAccountRecoveryCase.objects.filter(id=case_id).values("school_id").first()
    if index is None:
        raise not_found()
    with tenant_context(school_id=index["school_id"], user_id=actor.id), transaction.atomic():
        if write:
            lock_parent_school(index["school_id"])
        query = GlobalAccountRecoveryCase.objects.filter(id=case_id)
        if write:
            query = query.select_for_update(of=("self",))
        case = query.select_related("source_request", "user", "school").first()
        if case is None:
            raise not_found()
        require_reviewer(actor)
        yield case


def ensure_open(case):
    if case.status in TERMINAL:
        raise ApiError("RECOVERY_CASE_CLOSED", "قضية الاستعادة مغلقة.", status_code=409)
    if case.expires_at <= timezone.now():
        raise ApiError("RECOVERY_CASE_EXPIRED", "انتهت صلاحية طلب الاستعادة.", status_code=409)
    case.user.refresh_from_db(fields=["password", "mobile", "is_active"])
    if (
        not case.user.is_active
        or not hmac.compare_digest(
            case.account_password_fingerprint, credential_fingerprint(case.user)
        )
        or not hmac.compare_digest(
            case.account_mobile_fingerprint, login_mobile_fingerprint(case.user)
        )
    ):
        raise ApiError(
            "RECOVERY_ACCOUNT_CHANGED", "تغيرت بيانات الحساب؛ يلزم طلب جديد.", status_code=409
        )
    if case.source_mobile_hash != case.source_request.new_mobile_hash:
        raise ApiError("RECOVERY_REQUEST_CHANGED", "تغير الطلب؛ يلزم طلب جديد.", status_code=409)


def ensure_independent(actor, case):
    if (
        actor.id in {case.user_id, case.requested_by_id}
        or SchoolMembership.objects.filter(school_id=case.school_id, user_id=actor.id).exists()
    ):
        raise ApiError("RECOVERY_REVIEW_CONFLICT", "المراجع ليس مستقلاً عن الطلب.", status_code=409)


def evidence_digest(case):
    rows = list(
        RecoveryEvidenceReference.objects.filter(
            case=case, revoked_at__isnull=True, expires_at__gt=timezone.now()
        ).order_by("id")
    )
    kinds = {row.kind for row in rows}
    required = {RecoveryEvidenceKind.ORIGINAL_ACCOUNT_BINDING}
    if case.operation != RecoveryOperation.PASSWORD_RECOVERY:
        required.add(RecoveryEvidenceKind.NEW_NUMBER_OWNERSHIP)
    if not required <= kinds:
        raise ApiError(
            "RECOVERY_EVIDENCE_INCOMPLETE", "تنقص مراجع أدلة مستقلة سارية.", status_code=409
        )
    binding = "|".join(
        f"{row.id}:{row.kind}:{row.reference_id}:{row.expires_at.isoformat()}" for row in rows
    )
    return hashlib.sha256(binding.encode()).hexdigest()


def check_number_conflict(case):
    mobile = decrypt_value(case.source_request.new_mobile_encrypted)
    if User.objects.filter(mobile=mobile).exclude(id=case.user_id).exists():
        raise ApiError(
            "RECOVERY_NUMBER_CONFLICT", "الرقم مرتبط بحساب آخر؛ لا دمج تلقائي.", status_code=409
        )


def case_payload(case, *, central=False):
    payload = {
        "id": str(case.id),
        "source_request_id": case.source_request_id,
        "school_id": case.school_id,
        "student_id": case.student_id,
        "operation": case.operation,
        "status": case.status,
        "version": case.version,
        "expires_at": case.expires_at,
        "created_at": case.created_at,
        "execution_enabled": False,
        "policy_code": "RECOVERY_POLICY_NOT_APPROVED",
        "new_mobile_masked": "",
    }
    from accounts.mobile import mask_mobile

    payload["new_mobile_masked"] = mask_mobile(
        decrypt_value(case.source_request.new_mobile_encrypted)
    )
    if central:
        payload["account_id"] = case.user_id
        payload["requester_id"] = case.requested_by_id
    return payload


def record_reference(actor, case_id, *, kind, reference_id, expires_at, expected_version):
    with recovery_scope(actor, case_id, write=True) as case:
        ensure_open(case)
        ensure_independent(actor, case)
        if case.version != expected_version:
            raise ApiError("RECOVERY_CASE_CHANGED", "تغيرت القضية؛ أعد تحميلها.", status_code=409)
        if not timezone.now() < expires_at <= case.expires_at:
            raise ApiError("VALIDATION_ERROR", "صلاحية المرجع خارج مدة القضية.")
        row = RecoveryEvidenceReference.objects.create(
            case=case,
            school_id=case.school_id,
            kind=kind,
            reference_id=reference_id,
            recorded_by=actor,
            expires_at=expires_at,
        )
        case.refresh_from_db()
        record_event(
            "PARENT_RECOVERY_REFERENCE_RECORDED",
            actor=actor,
            school=case.school,
            target_type="GlobalAccountRecoveryCase",
            target_id=case.id,
            metadata={"evidence_id": row.id, "kind": kind, "verified": False},
        )
        return row, case


def revoke_reference(actor, case_id, reference_id, *, expected_version):
    with recovery_scope(actor, case_id, write=True) as case:
        ensure_open(case)
        ensure_independent(actor, case)
        if case.version != expected_version:
            raise ApiError("RECOVERY_CASE_CHANGED", "تغيرت القضية؛ أعد تحميلها.", status_code=409)
        row = (
            RecoveryEvidenceReference.objects.select_for_update()
            .filter(id=reference_id, case=case, revoked_at__isnull=True)
            .first()
        )
        if row is None:
            raise not_found()
        row.revoked_at = timezone.now()
        row.save(update_fields=["revoked_at", "updated_at"])
        case.refresh_from_db()
        record_event(
            "PARENT_RECOVERY_REFERENCE_REVOKED",
            actor=actor,
            school=case.school,
            target_type="GlobalAccountRecoveryCase",
            target_id=case.id,
            metadata={"evidence_id": row.id},
        )
        return case


def review_case(actor, case_id, *, stage, recommendation, expected_version, note=""):
    require_reviewer(actor, stage=stage)
    with recovery_scope(actor, case_id, write=True) as case:
        ensure_open(case)
        ensure_independent(actor, case)
        if case.version != expected_version:
            raise ApiError("RECOVERY_CASE_CHANGED", "تغيرت القضية؛ أعد تحميلها.", status_code=409)
        if case.status == RecoveryStatus.POLICY_BLOCKED:
            raise ApiError(
                "RECOVERY_POLICY_NOT_APPROVED", "إتمام الاستعادة محجوب.", status_code=423
            )
        previous = RecoveryReviewDecision.objects.filter(case=case, case_version=case.version)
        if previous.filter(stage=stage).exists():
            raise ApiError(
                "RECOVERY_REVIEW_ALREADY_RECORDED", "المراجعة مسجلة بالفعل.", status_code=409
            )
        if stage == RecoveryReviewStage.SECOND:
            first = previous.filter(stage=RecoveryReviewStage.FIRST).first()
            if (
                first is None
                or first.reviewer_id == actor.id
                or case.status != "AWAITING_SECOND_REVIEW"
            ):
                raise ApiError(
                    "RECOVERY_SECOND_REVIEW_REQUIRED",
                    "يلزم قرار أول ومراجع مستقل ثان.",
                    status_code=409,
                )
        elif case.status == RecoveryStatus.AWAITING_SECOND_REVIEW:
            raise ApiError(
                "RECOVERY_SECOND_REVIEW_REQUIRED", "القضية تنتظر مراجعاً ثانياً.", status_code=409
            )
        digest = ""
        if recommendation == RecoveryRecommendation.CONTINUE_REVIEW:
            digest = evidence_digest(case)
            check_number_conflict(case)
            if stage == RecoveryReviewStage.SECOND and first.evidence_fingerprint != digest:
                raise ApiError("RECOVERY_CASE_CHANGED", "تغيرت مراجع الأدلة.", status_code=409)
        RecoveryReviewDecision.objects.create(
            case=case,
            school_id=case.school_id,
            reviewer=actor,
            stage=stage,
            recommendation=recommendation,
            case_version=case.version,
            evidence_fingerprint=digest,
            note_encrypted=encrypt_value(note) if note else "",
        )
        if recommendation == RecoveryRecommendation.REJECT:
            case.status = RecoveryStatus.REJECTED
        elif recommendation == RecoveryRecommendation.NEEDS_EVIDENCE:
            case.status = RecoveryStatus.NEEDS_EVIDENCE
        elif stage == RecoveryReviewStage.FIRST:
            case.status = RecoveryStatus.AWAITING_SECOND_REVIEW
        else:
            case.status = RecoveryStatus.POLICY_BLOCKED
        case.save(update_fields=["status", "updated_at"])
        record_event(
            "PARENT_RECOVERY_REVIEW_RECORDED",
            actor=actor,
            school=case.school,
            target_type="GlobalAccountRecoveryCase",
            target_id=case.id,
            metadata={
                "stage": stage,
                "recommendation": recommendation,
                "case_version": case.version,
                "execution_enabled": False,
            },
        )
        return case


def execute_recovery(*, actor, case_id):
    """No feature flag, OTP, credential override, session or SQL bypass exists here."""
    require_reviewer(actor)
    with recovery_scope(actor, case_id):
        raise ApiError(
            "RECOVERY_POLICY_NOT_APPROVED",
            "إتمام الاستعادة معطل حتى اعتماد وتنفيذ إثبات ملكية الحساب والرقم.",
            status_code=423,
        )
