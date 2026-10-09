"""School-reviewed families; one private SMS bearer, exact grants per child."""

import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import Case, CharField, Count, F, Func, Q, Value, When
from django.db.models.functions import Cast, Concat, Replace
from django.utils import timezone

from accounts.mobile import mask_mobile
from accounts.models import User
from audit.services import record_event
from common.errors import ApiError
from common.tenant_rls import tenant_context
from parents.access import lock_parent_school
from parents.contact_security import blocked_student_ids
from parents.models import (
    GuardianActivation,
    GuardianFamilyInvitation,
    GuardianFamilyInvitationChild,
    GuardianRegistrationRequest,
    RegistrationStatus,
)
from parents.security import contact_hash, decrypt_value, encrypt_value, mobile_hash, token_hash
from parents.services import (
    _require_staff,
    _validate_activation,
    activation_account,
    apply_activation_relation,
    bearer_context,
)
from school_sms.models import SchoolSmsIntegration
from students.models import Student
from students.services.imports.normalization import normalize_text

MAX_CHILDREN = 50


def lock_family(school_id, digest):
    """Serialize this contact's issue/send/consume operations before child row locks."""
    key = int.from_bytes(
        hashlib.sha256(f"parent-family:{school_id}:{digest}".encode()).digest()[:8],
        "big",
        signed=True,
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def invalid():
    return ApiError(
        "INVITATION_INVALID",
        "الدعوة غير متاحة أو تغيرت بياناتها. تواصل مع المدرسة.",
        status_code=409,
    )


def _students(school):
    return (
        Student.objects.filter(school=school, status="ACTIVE", merged_into__isnull=True)
        .annotate(
            mobile_key=Func(
                F("guardian_mobile"),
                function="public.xmansx_parent_mobile_key",
                output_field=CharField(),
            ),
        )
        .annotate(
            family_key=Case(
                When(mobile_key__regex=r"^\+9665[0-9]{8}$", then=F("mobile_key")),
                default=Concat(Value("invalid:"), Cast("id", CharField())),
                output_field=CharField(),
            )
        )
    )


def _child_token(token, activation_id):
    return hmac.new(
        token.encode(), f"family-child:{activation_id}".encode(), hashlib.sha256
    ).hexdigest()


def _valid_locked(invitation, children, school):
    from subscriptions.entitlements import has_entitlement

    if not has_entitlement(school, "PARENT_PORTAL"):
        raise invalid()
    if (
        invitation.consumed_at
        or invitation.revoked_at
        or invitation.expires_at <= timezone.now()
        or not children
        or invitation.delivery_status not in {"SENT", "SENDING", "UNKNOWN"}
    ):
        raise invalid()
    for child in children:
        _validate_activation(
            child.activation,
            child.activation.request,
            child.student,
            school,
            allow_family=True,
        )
        if (
            child.student.status != "ACTIVE"
            or child.student.merged_into_id
            or contact_hash(child.student.mobile_key)
            != child.activation.request.approved_contact_hash
        ):
            raise invalid()
    if blocked_student_ids(school=school, students=[child.student for child in children]):
        raise invalid()


def invitation_row(invitation, *, current_student_ids=None):
    children = list(invitation.children.all())
    now = timezone.now()
    stale = any(
        child.activation.revoked_at
        or child.activation.contact_revision != child.student.guardian_contact_revision
        or child.student.status != "ACTIVE"
        or child.student.merged_into_id
        for child in children
    )
    lifecycle = (
        "NEEDS_REVIEW"
        if stale or not children
        else "ACTIVATED"
        if invitation.consumed_at
        else "REVOKED"
        if invitation.revoked_at
        else "EXPIRED"
        if invitation.expires_at <= now
        else "OPEN"
    )
    status = invitation.delivery_status
    if status == "SENDING" and invitation.updated_at < now - timedelta(minutes=5):
        status = "UNKNOWN"
    return {
        "id": str(invitation.id),
        "name": invitation.name,
        "mobile_masked": invitation.mobile_masked,
        "delivery_status": status,
        "lifecycle": lifecycle,
        "created_at": invitation.created_at.isoformat(),
        "expires_at": invitation.expires_at.isoformat(),
        "consumed_at": invitation.consumed_at.isoformat() if invitation.consumed_at else None,
        "failure_code": invitation.failure_code,
        "student_ids": [child.student_id for child in children],
        "partial": bool(
            current_student_ids is not None
            and set(current_student_ids) != {child.student_id for child in children}
        ),
    }


def families_page(school, page, request):
    base = _students(school)
    search = normalize_text(request.query_params.get("search", ""))
    if len(search) > 150:
        raise ApiError("VALIDATION_ERROR", "اكتب بحثاً لا يتجاوز 150 حرفاً.", status_code=400)
    matching = base
    if search:
        # Match contacts first, then retrieve the whole family before pagination.
        # Filtering the child rows themselves would silently omit siblings.
        def name_key(expression):
            for source, target in [("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي")]:
                expression = Replace(expression, Value(source), Value(target))
            return Func(
                expression,
                Value("[ـً-ٟ]"),
                Value(""),
                Value("g"),
                function="regexp_replace",
                output_field=CharField(),
            )

        needle = re.sub("[ـً-ٟ]", "", search.translate(str.maketrans("أإآى", "اااي")))
        matching = base.annotate(
            guardian_search=name_key(F("guardian_name")), child_search=name_key(F("full_name"))
        )
        guardian_match, child_match = Q(), Q()
        for word in needle.split():
            guardian_match &= Q(guardian_search__icontains=word)
            child_match &= Q(child_search__icontains=word)
        predicate = guardian_match | child_match
        digits = search.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
        digits = re.sub(r"[\s()+-]", "", digits)
        if digits.isascii() and digits.isdigit():
            if digits.startswith("00966"):
                digits = digits[2:]
            elif digits.startswith("05"):
                digits = "966" + digits[1:]
            predicate |= Q(mobile_key__contains=digits)
        # A school may have reviewed a different guardian name for the invitation.
        invitation_matches = GuardianFamilyInvitation.objects.filter(school=school).annotate(
            reviewed_search=name_key(F("name"))
        )
        for word in needle.split():
            invitation_matches = invitation_matches.filter(reviewed_search__icontains=word)
        predicate |= Q(id__in=invitation_matches.values("children__student_id"))
        matching = matching.filter(predicate)
        base_groups = base.filter(family_key__in=matching.order_by().values("family_key"))
    else:
        base_groups = base
    groups = (
        base_groups.order_by()
        .values("family_key")
        .annotate(child_count=Count("id"))
        .order_by("family_key")
    )
    group_page = page.paginate_queryset(groups, request)
    keys = [row["family_key"] for row in group_page]
    students = list(base.filter(family_key__in=keys).order_by("id"))
    by_key = {key: [] for key in keys}
    for student in students:
        by_key[student.family_key].append(student)
    hashes = [mobile_hash(key) for key in keys if not key.startswith("invalid:")]
    latest = {}
    invitations = (
        GuardianFamilyInvitation.objects.filter(school=school, mobile_hash__in=hashes)
        .prefetch_related(
            "children__student",
            "children__activation",
        )
        .order_by("mobile_hash", "-created_at", "-id")
        .distinct("mobile_hash")
    )
    for invitation in invitations:
        latest.setdefault(invitation.mobile_hash, invitation)
    rows = []
    for group in group_page:
        key = group["family_key"]
        family = by_key[key]
        names = sorted(
            {
                normalize_text(student.guardian_name)
                for student in family
                if normalize_text(student.guardian_name)
            }
        )
        missing = any(not normalize_text(student.guardian_name) for student in family)
        valid_mobile = bool(re.fullmatch(r"\+9665[0-9]{8}", key))
        previous = latest.get(mobile_hash(key)) if valid_mobile else None
        rows.append(
            {
                "key": mobile_hash(key),
                "name": names[0] if len(names) == 1 else "تحتاج مراجعة الأسماء",
                "names": names,
                "mobile": key if valid_mobile else "",
                "mobile_masked": mask_mobile(key) if valid_mobile else "جوال غير صالح أو مفقود",
                "needs_review": missing or len(names) != 1 or not valid_mobile,
                "child_count": group["child_count"],
                "children": [
                    {
                        "id": student.id,
                        "name": student.full_name,
                        "revision": student.guardian_contact_revision,
                    }
                    for student in family[:MAX_CHILDREN]
                ],
                "invitation": invitation_row(
                    previous, current_student_ids=[student.id for student in family]
                )
                if previous
                else None,
            }
        )
    payload = page.get_paginated_response(rows).data
    payload["sms_enabled"] = settings.PARENT_FAMILY_INVITATION_SMS_ENABLED
    payload["sms_configured"] = SchoolSmsIntegration.objects.filter(
        school=school, is_active=True
    ).exists()
    return payload


def create_invitation(*, school, membership, data, request=None):
    _require_staff(school, membership)
    from subscriptions.entitlements import require_feature

    require_feature(school, "PARENT_PORTAL")
    if not settings.PARENT_FAMILY_INVITATION_SMS_ENABLED:
        raise ApiError(
            "INVITATION_SMS_DISABLED", "إرسال دعوات الأسرة غير مفعل تشغيلياً.", status_code=503
        )
    if not SchoolSmsIntegration.objects.filter(school=school, is_active=True).exists():
        raise ApiError("SMS_UNAVAILABLE", "هيئ مزود SMS للمدرسة قبل إرسال الدعوة.", status_code=409)
    selected = {child["id"]: child["revision"] for child in data["children"]}
    token = secrets.token_urlsafe(32)
    try:
        with transaction.atomic():
            lock_parent_school(school.id)
            lock_family(school.id, mobile_hash(data["mobile"]))
            students = list(
                _students(school).filter(id__in=selected).order_by("id").select_for_update()
            )
            if len(students) != len(selected) or any(
                student.guardian_contact_revision != selected[student.id] for student in students
            ):
                raise invalid()
            mobile = data["mobile"]
            if any(student.mobile_key != mobile for student in students):
                raise invalid()
            if blocked_student_ids(school=school, students=students):
                raise invalid()
            previous = (
                GuardianFamilyInvitation.objects.select_for_update()
                .filter(
                    school=school,
                    mobile_hash=mobile_hash(mobile),
                    revoked_at__isnull=True,
                    consumed_at__isnull=True,
                )
                .first()
            )
            if previous:
                if not data.get("reissue") and previous.expires_at > timezone.now():
                    raise ApiError(
                        "INVITATION_EXISTS",
                        "توجد دعوة بالفعل. استخدم إعادة الإصدار بعد المراجعة.",
                        status_code=409,
                    )
                previous.revoked_at = timezone.now()
                previous.save(update_fields=["revoked_at", "updated_at"])
                GuardianActivation.objects.filter(
                    family_child__invitation=previous, used_at__isnull=True,
                    revoked_at__isnull=True,
                ).update(revoked_at=timezone.now())
                GuardianRegistrationRequest.objects.filter(
                    activations__family_child__invitation=previous,
                    status__in=["APPROVED", "NEEDS_INFO", "PENDING"],
                ).update(status="CANCELLED")
            expires = timezone.now() + timedelta(
                seconds=min(max(settings.PARENT_FAMILY_INVITATION_TTL_SECONDS, 300), 172800)
            )
            invitation = GuardianFamilyInvitation.objects.create(
                school=school,
                name=data["name"],
                mobile_encrypted=encrypt_value(mobile),
                mobile_hash=mobile_hash(mobile),
                mobile_masked=mask_mobile(mobile),
                token_hash=token_hash(token),
                verification_note=data["verification_note"],
                approved_by=membership.user,
                expires_at=expires,
            )
            for student in students:
                item = GuardianRegistrationRequest.objects.create(
                    school=school,
                    student=student,
                    name=data["name"],
                    mobile_encrypted=invitation.mobile_encrypted,
                    mobile_hash=invitation.mobile_hash,
                    mobile_masked=invitation.mobile_masked,
                    identifier_encrypted=student.national_id_encrypted,
                    identifier_hash=student.national_id_lookup_hash,
                    receipt_hash=token_hash(secrets.token_urlsafe(32)),
                    relationship_type=data["relationship_type"],
                    status=RegistrationStatus.APPROVED,
                    contact_bound=True,
                    contact_revision=student.guardian_contact_revision,
                    approved_contact_hash=contact_hash(mobile),
                    approved_by=membership.user,
                    approved_at=timezone.now(),
                    reviewed_at=timezone.now(),
                    verification_note=data["verification_note"],
                )
                # A deterministic child secret exists only while this family bearer is in memory.
                activation = GuardianActivation.objects.create(
                    school=school,
                    student=student,
                    request=item,
                    token_hash=token_hash(secrets.token_urlsafe(32)),
                    contact_revision=student.guardian_contact_revision,
                    expires_at=expires,
                    delivery_status="PENDING",
                    delivery_channel="SMS",
                )
                activation.token_hash = token_hash(_child_token(token, activation.id))
                activation.save(update_fields=["token_hash", "updated_at"])
                GuardianFamilyInvitationChild.objects.create(
                    school=school, invitation=invitation, student=student, activation=activation
                )
            record_event(
                "PARENT_FAMILY_INVITATION_APPROVED",
                school=school,
                actor=membership.user,
                request=request,
                target_type="GuardianFamilyInvitation",
                target_id=invitation.id,
                metadata={"children_count": len(students)},
            )
            transaction.on_commit(lambda: safe_delivery(school.id, invitation.id, token))
    except IntegrityError as exc:
        raise ApiError(
            "INVITATION_CONFLICT",
            "يوجد طلب أو دعوة متزامنة لهذه الأسرة. حدّث القائمة.",
            status_code=409,
        ) from exc
    return invitation


def invitation_index(token):
    with bearer_context("family", token_hash(token)):
        invitation = (
            GuardianFamilyInvitation.objects.filter(token_hash=token_hash(token))
            .values("id", "school_id")
            .first()
        )
    if invitation is None:
        raise invalid()
    return invitation


def _load_children(invitation, *, locked=False):
    children = list(
        GuardianFamilyInvitationChild.objects.filter(invitation=invitation)
        .select_related(
            "student",
            "activation__request",
        )
        .order_by("student_id")
    )
    if locked:
        students = {
            student.id: student
            for student in _students(invitation.school)
            .filter(id__in=[child.student_id for child in children])
            .order_by("id")
            .select_for_update()
        }
        for child in children:
            if child.student_id not in students:
                raise invalid()
            child.student = students[child.student_id]
        # Same school -> ordered students -> requests -> activations -> invitation.
        list(
            GuardianRegistrationRequest.objects.filter(
                id__in=[child.activation.request_id for child in children]
            )
            .order_by("id")
            .select_for_update()
        )
        activations = {
            activation.id: activation
            for activation in GuardianActivation.objects.filter(
                id__in=[child.activation_id for child in children]
            )
            .select_related("request")
            .order_by("id")
            .select_for_update(of=("self",))
        }
        for child in children:
            child.activation = activations[child.activation_id]
    else:
        for child in children:
            child.student.mobile_key = _mobile_key(child.student.guardian_mobile)
    return children


def _mobile_key(value):
    from django.core.exceptions import ValidationError

    from accounts.mobile import normalize_mobile

    try:
        return normalize_mobile(value)
    except ValidationError:
        return ""


def inspect_invitation(token, user=None):
    index = invitation_index(token)
    with tenant_context(school_id=index["school_id"]):
        invitation = GuardianFamilyInvitation.objects.select_related("school").get(id=index["id"])
        children = _load_children(invitation)
        _valid_locked(invitation, children, invitation.school)
        existing = User.objects.filter(mobile=decrypt_value(invitation.mobile_encrypted)).first()
        verified = False
        if existing and user is not None and user.is_authenticated and user.id == existing.id:
            from parents.email_recovery_models import AccountRecoveryEmail
            from parents.email_recovery_services import email_scope

            with email_scope(user_id=existing.id):
                verified = AccountRecoveryEmail.objects.filter(
                    user=existing, verified_at__isnull=False
                ).exists()
        return {
            "school_name": invitation.school.name,
            "children_count": len(children),
            "account_exists": bool(existing),
            "requires_login": bool(
                existing and (user is None or not user.is_authenticated or user.id != existing.id)
            ),
            "email_verified": verified,
        }


def complete_invitation(
    *,
    token,
    email="",
    user=None,
    new_password=None,
    confirm_password=None,
    current_password=None,
    request=None,
):
    from parents.email_recovery_models import AccountRecoveryEmail
    from parents.email_recovery_services import (
        email_scope,
        enroll_recovery_email,
        enroll_registration_email,
    )

    index = invitation_index(token)
    with tenant_context(school_id=index["school_id"]), transaction.atomic():
        lock_parent_school(index["school_id"])
        invitation = GuardianFamilyInvitation.objects.select_related("school").get(id=index["id"])
        lock_family(index["school_id"], invitation.mobile_hash)
        children = _load_children(invitation, locked=True)
        invitation = GuardianFamilyInvitation.objects.select_for_update().get(id=invitation.id)
        _valid_locked(invitation, children, invitation.school)
        if (
            user is not None
            and user.is_authenticated
            and user.mobile != decrypt_value(invitation.mobile_encrypted)
        ):
            raise ApiError(
                "EXISTING_ACCOUNT_LOGIN_REQUIRED",
                "هذه الدعوة لا تغير رقم حسابك العالمي. تواصل مع المدرسة لمراجعة الربط.",
                status_code=403,
            )
        account, existing = activation_account(
            item=children[0].activation.request,
            user=user,
            new_password=new_password,
            confirm_password=confirm_password,
            request=request,
        )
        for child in children:
            if child.activation.token_hash != token_hash(_child_token(token, child.activation_id)):
                raise invalid()
            with (
                bearer_context("family", invitation.token_hash),
                bearer_context("activation", child.activation.token_hash),
            ):
                relation = apply_activation_relation(
                    account=account,
                    item=child.activation.request,
                    activation=child.activation,
                    student=child.student,
                )
                record_event(
                    "PARENT_RELATION_ACTIVATED",
                    school=invitation.school,
                    actor=account,
                    request=request,
                    target_type="GuardianStudentRelation",
                    target_id=relation.id,
                )
        with email_scope(user_id=account.id):
            verified = AccountRecoveryEmail.objects.filter(
                user=account, verified_at__isnull=False
            ).exists()
        if not verified:
            if not email:
                raise ApiError("VALIDATION_ERROR", "البريد الإلكتروني مطلوب.", status_code=400)
            if existing:
                enroll_recovery_email(account, email, current_password or "")
            else:
                enroll_registration_email(account, email, new_account=True)
        invitation.consumed_at = timezone.now()
        invitation.activated_user = account
        with bearer_context("family", invitation.token_hash):
            invitation.save(update_fields=["consumed_at", "activated_user", "updated_at"])
        record_event(
            "PARENT_FAMILY_INVITATION_ACTIVATED",
            school=invitation.school,
            actor=account,
            request=request,
            target_type="GuardianFamilyInvitation",
            target_id=invitation.id,
            metadata={"children_count": len(children)},
        )
        return account


def safe_delivery(school_id, invitation_id, token):
    """An already committed approval reports uncertainty rather than false delivery."""
    try:
        deliver_invitation(school_id, invitation_id, token)
    except Exception:
        # No exception text, bearer or provider payload enters application logs.
        # A DB outage leaves a visibly pending/stale attempt for operational review.
        try:
            with tenant_context(school_id=school_id), transaction.atomic():
                item = (
                    GuardianFamilyInvitation.objects.select_for_update()
                    .filter(id=invitation_id)
                    .first()
                )
                if item and item.delivery_status in {"PENDING", "SENDING"}:
                    item.delivery_status = (
                        "FAILED" if item.delivery_status == "PENDING" else "UNKNOWN"
                    )
                    item.failure_code = "DELIVERY_PROCESS_INTERRUPTED"
                    item.save(update_fields=["delivery_status", "failure_code", "updated_at"])
        except Exception:
            return


def deliver_invitation(school_id, invitation_id, token):
    from parents.family_invitation_sms import send_family_sms

    with tenant_context(school_id=school_id), transaction.atomic():
        lock_parent_school(school_id)
        invitation = (
            GuardianFamilyInvitation.objects.select_related("school")
            .filter(id=invitation_id)
            .first()
        )
        if invitation is None:
            return
        lock_family(school_id, invitation.mobile_hash)
        children = _load_children(invitation, locked=True)
        invitation = GuardianFamilyInvitation.objects.select_for_update().get(id=invitation_id)
        if invitation.delivery_status != "PENDING":
            return
        try:
            # PENDING is allowed only to prepare the single delivery attempt.
            invitation.delivery_status = "SENDING"
            _valid_locked(invitation, children, invitation.school)
            if invitation.token_hash != token_hash(token):
                raise invalid()
        except ApiError:
            invitation.delivery_status = "FAILED"
            invitation.failure_code = "PRE_SEND_STATE_CHANGED"
            invitation.save(update_fields=["delivery_status", "failure_code", "updated_at"])
            return
        invitation.save(update_fields=["delivery_status", "updated_at"])
    try:
        status, code, reference = send_family_sms(invitation, token)
    except Exception:
        status, code, reference = "UNKNOWN", "SMS_DELIVERY_UNKNOWN", ""
    with tenant_context(school_id=school_id), transaction.atomic():
        updated = GuardianFamilyInvitation.objects.filter(
            id=invitation_id, delivery_status="SENDING"
        ).update(
            delivery_status=status,
            failure_code=code,
            provider_reference=reference,
            updated_at=timezone.now(),
        )
        if updated:
            GuardianActivation.objects.filter(
                family_child__invitation_id=invitation_id, delivery_status="PENDING"
            ).update(delivery_status=status)
            record_event(
                "PARENT_FAMILY_INVITATION_DELIVERY",
                school=invitation.school,
                target_type="GuardianFamilyInvitation",
                target_id=invitation.id,
                metadata={"status": status},
            )
