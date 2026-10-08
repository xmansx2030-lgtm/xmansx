"""Registration/activation with explicit approval, identity reuse and atomic grants."""

import secrets
from contextlib import contextmanager
from datetime import timedelta
from urllib.parse import quote, urlsplit

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from accounts.models import User
from audit.services import record_event
from common.errors import ApiError
from common.security.identifiers import national_id_lookup_hash
from common.tenant_rls import can_restore_tenant_context, tenant_context
from parents.access import lock_parent_school
from parents.contact_security import normalized_contact
from parents.models import (
    GuardianActivation,
    GuardianRegistrationRequest,
    GuardianStudentRelation,
    ParentRegistrationConfig,
    RegistrationStatus,
    RelationStatus,
)
from parents.security import contact_hash, decrypt_value, encrypt_value, mobile_hash, token_hash
from schools.models import School, SchoolStatus
from students.models import Student
from subscriptions.access import FULL, get_school_access_mode

GENERIC_RECEIPT = "تم استلام طلبك، وستقوم المدرسة بمراجعته."


@contextmanager
def bearer_context(kind: str, digest: str):
    # Names are constants selected by code, never SQL supplied by the caller.
    names = {"activation": "app.parent_activation_hash", "receipt": "app.parent_receipt_hash"}
    name = names[kind]
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [name])
        previous = cursor.fetchone()[0] or ""
        cursor.execute("SELECT set_config(%s, %s, false)", [name, digest])
    try:
        yield
    finally:
        if can_restore_tenant_context():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config(%s, %s, false)", [name, previous])


def portal_url(path: str):
    origin = settings.PARENT_PORTAL_BASE_URL.rstrip("/")
    parsed = urlsplit(origin)
    if not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ApiError("PORTAL_URL_UNCONFIGURED", "عنوان بوابة الأسرة غير مهيأ.", status_code=503)
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ApiError("PORTAL_URL_UNCONFIGURED", "يلزم عنوان HTTPS للبوابة.", status_code=503)
    return f"{origin}{path}"


def registration_config(token):
    item = (
        ParentRegistrationConfig.objects.filter(token=token, enabled=True)
        .values(
            "school_id",
            "enabled",
        )
        .first()
    )
    if item is None:
        raise ApiError("REGISTRATION_UNAVAILABLE", "التسجيل غير متاح حالياً.", status_code=404)
    with tenant_context(school_id=item["school_id"]):
        school = School.objects.filter(id=item["school_id"], status=SchoolStatus.ACTIVE).first()
        if school is None or get_school_access_mode(school) != FULL:
            raise ApiError("REGISTRATION_UNAVAILABLE", "التسجيل غير متاح حالياً.", status_code=404)
        return school


def submit_registration(*, school, data, user=None, request=None):
    from accounts.mobile import mask_mobile

    receipt = secrets.token_urlsafe(32)
    with tenant_context(school_id=school.id), transaction.atomic():
        lock_parent_school(school.id)
        # Duplicate and unmatched submissions receive identical public output.
        try:
            with transaction.atomic():
                item = GuardianRegistrationRequest.objects.create(
                    school=school,
                    name=data["name"],
                    mobile_encrypted=encrypt_value(data["mobile"]),
                    mobile_hash=mobile_hash(data["mobile"]),
                    mobile_masked=mask_mobile(data["mobile"]),
                    identifier_encrypted=encrypt_value(data["student_identifier"]),
                    identifier_hash=national_id_lookup_hash(data["student_identifier"]),
                    relationship_type=data["relationship_type"],
                    receipt_hash=token_hash(receipt),
                    requested_by=user if user and user.is_authenticated else None,
                )
                record_event(
                    "PARENT_REGISTRATION_SUBMITTED",
                    school=school,
                    request=request,
                    target_type="GuardianRegistrationRequest",
                    target_id=item.id,
                )
        except IntegrityError:
            # No match/account/duplicate indication; a fresh opaque receipt preserves
            # a uniform public response without handing another submitter a receipt.
            pass
    return {"message": GENERIC_RECEIPT, "receipt_token": receipt}


def receipt_status(receipt: str, *, applicant_note=None):
    digest = token_hash(receipt)
    with bearer_context("receipt", digest):
        index = (
            GuardianRegistrationRequest.objects.filter(receipt_hash=digest)
            .values(
                "id",
                "school_id",
            )
            .first()
        )
    if index is None:
        return {"status": "PENDING", "message": GENERIC_RECEIPT}
    with tenant_context(school_id=index["school_id"]), transaction.atomic():
        lock_parent_school(index["school_id"])
        item = GuardianRegistrationRequest.objects.select_for_update().get(id=index["id"])
        if applicant_note and item.status == RegistrationStatus.NEEDS_INFO:
            item.applicant_note = applicant_note
            item.status = RegistrationStatus.PENDING
            item.save(update_fields=["applicant_note", "status", "updated_at"])
        return {"status": item.status, "message": item.decision_reason or GENERIC_RECEIPT}


def registration_payload(item):
    return {
        "id": item.id,
        "name": item.name,
        "mobile_masked": item.mobile_masked,
        "relationship_type": item.relationship_type,
        "status": item.status,
        "student_id": item.student_id,
        "created_at": item.created_at.isoformat(),
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "decision_reason": item.decision_reason,
        "applicant_note": item.applicant_note,
    }


def registration_review(*, school, request_id):
    item = GuardianRegistrationRequest.objects.filter(school=school, id=request_id).first()
    if item is None:
        raise ApiError("NOT_FOUND", "المورد المطلوب غير موجود.", status_code=404)
    student = Student.objects.filter(
        school=school, national_id_lookup_hash=item.identifier_hash
    ).first()
    mobile = decrypt_value(item.mobile_encrypted)
    # Imported matching is only a staff aid; no grant is created by this read.
    candidates = list(
        Student.objects.filter(school=school, guardian_mobile=mobile).values(
            "id",
            "full_name",
            "national_id_masked",
        )[:50]
    )
    existing = (
        list(
            GuardianStudentRelation.objects.filter(school=school, student=student).values(
                "id",
                "status",
                "relationship_type",
                "contact_bound",
            )
        )
        if student
        else []
    )
    return {
        "request": {**registration_payload(item), "mobile": mobile},
        "student_match": {
            "id": student.id,
            "full_name": student.full_name,
            "national_id_masked": student.national_id_masked,
            "guardian_name": student.guardian_name,
            "guardian_mobile": student.guardian_mobile,
            "contact_revision": student.guardian_contact_revision,
        }
        if student
        else None,
        "sibling_candidates": candidates,
        "existing_relations": existing,
        "activations": [
            {
                "id": activation.id,
                "delivery_status": "UNKNOWN"
                if activation.delivery_status == "SENDING"
                and (activation.updated_at < timezone.now() - timedelta(minutes=5))
                else activation.delivery_status,
                "failure_code": activation.failure_code,
                "created_at": activation.created_at.isoformat(),
                "expires_at": activation.expires_at.isoformat(),
                "used_at": activation.used_at.isoformat() if activation.used_at else None,
                "revoked_at": activation.revoked_at.isoformat() if activation.revoked_at else None,
            }
            for activation in GuardianActivation.objects.filter(
                school=school, request=item
            ).order_by("-created_at")[:10]
        ],
    }


def _require_staff(school, membership):
    if (
        membership.school_id != school.id
        or not membership.is_active_membership
        or not set(membership.role_codes()) & {"SCHOOL_MANAGER", "VICE_PRINCIPAL"}
    ):
        raise ApiError("PERMISSION_DENIED", "ليست لديك صلاحية لتنفيذ الإجراء.", status_code=403)


def decide_registration(*, school, membership, request_id, data, request=None):
    _require_staff(school, membership)
    raw_token = None
    with transaction.atomic():
        lock_parent_school(school.id)
        student = None
        if data["decision"] == "APPROVE":
            student = (
                Student.objects.select_for_update()
                .filter(
                    school=school,
                    id=data.get("student_id"),
                    merged_into__isnull=True,
                )
                .first()
            )
            if student is None:
                raise ApiError("NOT_FOUND", "الطالب غير متاح.", status_code=404)
        item = (
            GuardianRegistrationRequest.objects.select_for_update()
            .filter(
                school=school,
                id=request_id,
            )
            .first()
        )
        if item is None:
            raise ApiError("NOT_FOUND", "المورد المطلوب غير موجود.", status_code=404)
        if item.status not in {RegistrationStatus.PENDING, RegistrationStatus.NEEDS_INFO}:
            raise ApiError(
                "REQUEST_ALREADY_REVIEWED", "سبق إصدار قرار لهذا الطلب.", status_code=409
            )
        note = data.get("verification_note", "").strip()
        reason = data.get("decision_reason", "").strip()
        if data["decision"] == "APPROVE":
            if len(note) < 10:
                raise ApiError("VERIFICATION_REQUIRED", "وثّق التحقق من هوية صاحب الصفة.")
            if student.national_id_lookup_hash != item.identifier_hash:
                raise ApiError("STUDENT_IDENTIFIER_MISMATCH", "الطالب لا يطابق معرف الطلب.")
            mobile = decrypt_value(item.mobile_encrypted)
            if data["contact_bound"] and mobile != normalized_contact(student.guardian_mobile):
                raise ApiError("CONTACT_MISMATCH", "تحقق مستقلاً من الصفة عند اختلاف رقم نور.")
            item.student = student
            item.contact_revision = student.guardian_contact_revision
            item.contact_bound = data["contact_bound"]
            item.approved_contact_hash = contact_hash(normalized_contact(student.guardian_mobile))
            item.approved_by = membership.user
            item.approved_at = timezone.now()
            item.verification_note = note
            item.status = RegistrationStatus.APPROVED
            # The exact-child database guard must see the persisted approval
            # before inserting its activation; both writes share this transaction.
            item.save()
            raw_token = secrets.token_urlsafe(32)
            GuardianActivation.objects.filter(
                request=item, used_at__isnull=True, revoked_at__isnull=True
            ).update(revoked_at=timezone.now())
            activation = GuardianActivation.objects.create(
                school=school,
                student=student,
                request=item,
                token_hash=token_hash(raw_token),
                contact_revision=student.guardian_contact_revision,
                expires_at=timezone.now()
                + timedelta(seconds=settings.PARENT_ACTIVATION_TTL_SECONDS),
                delivery_status="MANUAL" if data["delivery"] == "MANUAL" else "PENDING",
            )
        else:
            if len(reason) < 3:
                raise ApiError("REASON_REQUIRED", "أدخل سبب القرار.")
            item.status = (
                RegistrationStatus.REJECTED
                if data["decision"] == "REJECT"
                else RegistrationStatus.NEEDS_INFO
            )
        item.decision_reason = reason
        item.reviewed_at = timezone.now()
        item.save()
        record_event(
            "PARENT_REGISTRATION_REVIEWED",
            school=school,
            actor=membership.user,
            request=request,
            target_type="GuardianRegistrationRequest",
            target_id=item.id,
            metadata={"status": item.status},
        )
    result = {"request": registration_payload(item)}
    if raw_token:
        url = portal_url(f"/parent/activate#token={quote(raw_token)}")
        if data["delivery"] == "MANUAL":
            result["activation_url"] = url
            result["delivery_status"] = "MANUAL"
        else:
            result["delivery_status"] = deliver_activation(
                school=school,
                activation_id=activation.id,
                token=raw_token,
            )
    return result


def deliver_activation(*, school, activation_id, token):
    from school_sms.models import SchoolSmsIntegration
    from school_sms.providers import SmsProviderError, send_sms
    from school_sms.security import decrypt_secret

    with tenant_context(school_id=school.id), transaction.atomic():
        lock_parent_school(school.id)
        index = (
            GuardianActivation.objects.filter(school=school, id=activation_id)
            .values(
                "student_id",
                "request_id",
            )
            .first()
        )
        if index is None:
            return "FAILED"
        student = Student.objects.select_for_update().get(id=index["student_id"], school=school)
        approved_request = GuardianRegistrationRequest.objects.select_for_update().get(
            id=index["request_id"],
            school=school,
        )
        activation = (
            GuardianActivation.objects.select_for_update(of=("self",))
            .select_related("request")
            .get(
                school=school,
                id=activation_id,
            )
        )
        if activation.delivery_status != "PENDING" or activation.revoked_at or activation.used_at:
            return activation.delivery_status
        try:
            _validate_activation(activation, approved_request, student, school)
        except ApiError:
            activation.delivery_status = "FAILED"
            activation.failure_code = "PRE_SEND_STATE_CHANGED"
            activation.save(update_fields=["delivery_status", "failure_code", "updated_at"])
            return "FAILED"
        integration = SchoolSmsIntegration.objects.filter(school=school, is_active=True).first()
        if integration is None:
            activation.delivery_status = "FAILED"
            activation.failure_code = "SMS_UNAVAILABLE"
            activation.save(update_fields=["delivery_status", "failure_code", "updated_at"])
            return "FAILED"
        try:
            secret = decrypt_secret(integration.secret_encrypted)
        except ApiError:
            activation.delivery_status = "FAILED"
            activation.failure_code = "CREDENTIAL_UNAVAILABLE"
            activation.save(update_fields=["delivery_status", "failure_code", "updated_at"])
            return "FAILED"
        mobile = decrypt_value(activation.request.mobile_encrypted)
        activation.delivery_status = "SENDING"
        activation.save(update_fields=["delivery_status", "updated_at"])
        provider, username, sender = (
            integration.provider,
            integration.username,
            integration.sender_name,
        )
    try:
        outcome = send_sms(
            provider=provider,
            username=username,
            secret=secret,
            sender=sender,
            mobile=mobile,
            message=f"تفعيل بوابة ولي الأمر: {portal_url('/parent/activate')}#token={quote(token)}",
        )
        status, code, reference = "SENT", "", outcome.reference
    except SmsProviderError as exc:
        status, code, reference = "UNKNOWN" if exc.ambiguous else "FAILED", exc.code, ""
    except Exception:
        # No exception logging: a transport exception may contain message/token.
        status, code, reference = "UNKNOWN", "UNEXPECTED_ERROR", ""
    with tenant_context(school_id=school.id), transaction.atomic():
        lock_parent_school(school.id)
        GuardianActivation.objects.filter(
            id=activation_id, school=school, delivery_status="SENDING"
        ).update(
            delivery_status=status,
            failure_code=code,
            provider_reference=reference[:100],
            updated_at=timezone.now(),
        )
        record_event(
            "PARENT_ACTIVATION_DELIVERY",
            school=school,
            target_type="GuardianActivation",
            target_id=activation_id,
            metadata={"status": status, "code": code},
        )
    return status


def reissue_activation(*, school, membership, request_id, data, request=None):
    _require_staff(school, membership)
    index = (
        GuardianRegistrationRequest.objects.filter(id=request_id, school=school)
        .values(
            "student_id",
        )
        .first()
    )
    if not index or not index["student_id"]:
        raise ApiError("NOT_FOUND", "المورد المطلوب غير موجود.", status_code=404)
    if len(data.get("verification_note", "").strip()) < 10:
        raise ApiError("VERIFICATION_REQUIRED", "وثّق التحقق قبل إعادة إصدار التفعيل.")
    portal_url("/parent/activate")
    with transaction.atomic():
        lock_parent_school(school.id)
        student = Student.objects.select_for_update().get(id=index["student_id"], school=school)
        item = GuardianRegistrationRequest.objects.select_for_update().get(
            id=request_id, school=school
        )
        if item.status != RegistrationStatus.APPROVED or (
            item.contact_bound and item.contact_revision != student.guardian_contact_revision
        ) or item.identifier_hash != student.national_id_lookup_hash:
            raise ApiError(
                "ACTIVATION_INVALID", "يلزم مراجعة الطلب واعتماده مجدداً.", status_code=409
            )
        GuardianActivation.objects.filter(
            request=item, used_at__isnull=True, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())
        token = secrets.token_urlsafe(32)
        delivery = data.get("delivery", "SMS")
        activation = GuardianActivation.objects.create(
            school=school,
            student=student,
            request=item,
            token_hash=token_hash(token),
            contact_revision=student.guardian_contact_revision,
            expires_at=timezone.now() + timedelta(seconds=settings.PARENT_ACTIVATION_TTL_SECONDS),
            delivery_status="MANUAL" if delivery == "MANUAL" else "PENDING",
        )
        record_event(
            "PARENT_ACTIVATION_REISSUED",
            school=school,
            actor=membership.user,
            request=request,
            target_type="GuardianActivation",
            target_id=activation.id,
        )
    if delivery == "MANUAL":
        return {
            "activation_url": portal_url(f"/parent/activate#token={quote(token)}"),
            "delivery_status": "MANUAL",
        }
    return {
        "delivery_status": deliver_activation(
            school=school, activation_id=activation.id, token=token
        )
    }


def activation_index(token):
    digest = token_hash(token)
    with bearer_context("activation", digest):
        index = (
            GuardianActivation.objects.filter(token_hash=digest)
            .values(
                "id",
                "school_id",
                "student_id",
                "request_id",
            )
            .first()
        )
    if index is None:
        raise ApiError(
            "ACTIVATION_INVALID", "رابط التفعيل غير صالح أو انتهت صلاحيته.", status_code=404
        )
    return index


def _validate_activation(activation, item, student, school):
    if (
        activation.used_at
        or activation.revoked_at
        or activation.expires_at <= timezone.now()
        or item.status != RegistrationStatus.APPROVED
        or item.student_id != student.id
        or item.identifier_hash != student.national_id_lookup_hash
        or (item.contact_bound and activation.contact_revision != student.guardian_contact_revision)
        or school.status != SchoolStatus.ACTIVE
        or get_school_access_mode(school) != FULL
    ):
        raise ApiError(
            "ACTIVATION_INVALID", "رابط التفعيل غير صالح أو انتهت صلاحيته.", status_code=409
        )


def inspect_activation(token, *, user=None):
    index = activation_index(token)
    with tenant_context(school_id=index["school_id"]):
        activation = GuardianActivation.objects.select_related("school", "request", "student").get(
            id=index["id"],
            school_id=index["school_id"],
        )
        _validate_activation(activation, activation.request, activation.student, activation.school)
        existing = User.objects.filter(
            mobile=decrypt_value(activation.request.mobile_encrypted)
        ).first()
        return {
            "status": "VALID",
            "school_name": activation.school.name,
            "account_exists": existing is not None,
            "requires_login": bool(
                existing and (user is None or not user.is_authenticated or user.id != existing.id)
            ),
        }


def complete_activation(
    *, token, user=None, new_password=None, confirm_password=None, request=None
):
    index = activation_index(token)
    with tenant_context(school_id=index["school_id"]), transaction.atomic():
        lock_parent_school(index["school_id"])
        student = Student.objects.select_for_update().get(
            id=index["student_id"], school_id=index["school_id"]
        )
        item = GuardianRegistrationRequest.objects.select_for_update().get(id=index["request_id"])
        activation = (
            GuardianActivation.objects.select_for_update(of=("self",))
            .select_related("school")
            .get(id=index["id"])
        )
        _validate_activation(activation, item, student, activation.school)
        mobile = decrypt_value(item.mobile_encrypted)
        existing = User.objects.select_for_update().filter(mobile=mobile).first()
        if existing:
            if (
                user is None
                or not user.is_authenticated
                or user.id != existing.id
                or not existing.is_active
                or not constant_time_compare(
                    user.get_session_auth_hash(), existing.get_session_auth_hash()
                )
                or (
                    request is not None
                    and not constant_time_compare(
                        request.session.get("_auth_user_hash", ""), existing.get_session_auth_hash()
                    )
                )
            ):
                raise ApiError(
                    "EXISTING_ACCOUNT_LOGIN_REQUIRED",
                    "سجّل الدخول إلى حسابك الحالي لإتمام الربط.",
                    status_code=403,
                )
            from accounts.api.views import require_password_changed

            require_password_changed(existing)
            account = existing
        else:
            if not new_password or new_password != confirm_password:
                raise ApiError("VALIDATION_ERROR", "أدخل كلمة مرور وتأكيداً مطابقاً.")
            account = User(mobile=mobile, first_name=item.name)
            try:
                validate_password(new_password, user=account)
            except ValidationError as exc:
                raise ApiError(
                    "VALIDATION_ERROR",
                    "كلمة المرور لا تستوفي متطلبات الأمان.",
                    details={"new_password": exc.messages},
                ) from exc
            account.set_password(new_password)
            try:
                with transaction.atomic():
                    account.save()
            except IntegrityError as exc:
                raise ApiError(
                    "EXISTING_ACCOUNT_LOGIN_REQUIRED",
                    "سجّل الدخول إلى حسابك الحالي.",
                    status_code=409,
                ) from exc
        relation, _ = GuardianStudentRelation.objects.select_for_update().get_or_create(
            school=activation.school,
            student=student,
            user=account,
        )
        relation.status = RelationStatus.ACTIVE
        relation.relationship_type = item.relationship_type
        relation.approved_by = item.approved_by
        relation.approved_at = item.approved_at
        relation.approval_revision += 1
        relation.contact_bound = item.contact_bound
        relation.contact_revision = student.guardian_contact_revision
        relation.approved_contact_hash = item.approved_contact_hash
        relation.verification_note = item.verification_note
        relation.suspended_at = None
        relation.suspension_reason = ""
        relation.revoked_at = None
        relation.revoked_by = None
        relation.save()
        activation.used_at = timezone.now()
        activation.save(update_fields=["used_at", "updated_at"])
        item.status = RegistrationStatus.ACTIVATED
        item.save(update_fields=["status", "updated_at"])
        record_event(
            "PARENT_RELATION_ACTIVATED",
            school=activation.school,
            actor=account,
            request=request,
            target_type="GuardianStudentRelation",
            target_id=relation.id,
        )
        return account


def decide_relation(*, school, membership, relation_id, data, request=None):
    _require_staff(school, membership)
    index = (
        GuardianStudentRelation.objects.filter(id=relation_id, school=school)
        .values("student_id")
        .first()
    )
    if index is None:
        raise ApiError("NOT_FOUND", "المورد المطلوب غير موجود.", status_code=404)
    with transaction.atomic():
        lock_parent_school(school.id)
        student = Student.objects.select_for_update().get(id=index["student_id"], school=school)
        relation = GuardianStudentRelation.objects.select_for_update().get(
            id=relation_id, school=school
        )
        if data["status"] == "ACTIVE":
            if len(data.get("verification_note", "").strip()) < 10:
                raise ApiError("VERIFICATION_REQUIRED", "وثّق إعادة التحقق من صاحب الصفة.")
            relation.contact_bound = data.get("contact_bound", relation.contact_bound)
            if relation.contact_bound and relation.user.mobile != normalized_contact(
                student.guardian_mobile
            ):
                raise ApiError("CONTACT_MISMATCH", "يلزم التحقق المستقل عند اختلاف رقم التواصل.")
            relation.contact_revision = student.guardian_contact_revision
            relation.approved_contact_hash = contact_hash(
                normalized_contact(student.guardian_mobile)
            )
            relation.approval_revision += 1
            relation.approved_by = membership.user
            relation.approved_at = timezone.now()
            relation.verification_note = data["verification_note"]
            relation.suspended_at = None
            relation.suspension_reason = ""
            relation.revoked_at = None
            relation.revoked_by = None
        elif data["status"] == "REVOKED":
            relation.revoked_at = timezone.now()
            relation.revoked_by = membership.user
            relation.suspension_reason = data["reason"]
        else:
            relation.suspended_at = timezone.now()
            relation.suspension_reason = data["reason"]
        relation.status = data["status"]
        relation.save()
        from parents.request_models import ParentNotification

        if relation.status == RelationStatus.ACTIVE:
            ParentNotification.objects.filter(
                relation=relation,
                kind="RELATION_STATUS",
                requires_action=True,
                action_completed_at__isnull=True,
            ).update(action_completed_at=timezone.now(), updated_at=timezone.now())
        ParentNotification.objects.get_or_create(
            school=school,
            relation=relation,
            user=relation.user,
            dedup_key=f"relation:{relation.id}:{relation.status}:{relation.updated_at.timestamp()}",
            defaults={
                "kind": "RELATION_STATUS",
                "title": "تغيّرت حالة علاقة أحد الأبناء",
                "body": "راجع المدرسة لاستكمال التحقق عند الحاجة.",
                "requires_action": False,
            },
        )
        record_event(
            "PARENT_RELATION_REVIEWED",
            school=school,
            actor=membership.user,
            request=request,
            target_type="GuardianStudentRelation",
            target_id=relation.id,
            metadata={"status": relation.status, "approval_revision": relation.approval_revision},
        )
    return {"id": relation.id, "status": relation.status}
