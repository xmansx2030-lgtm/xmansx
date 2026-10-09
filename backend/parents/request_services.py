"""Reviewed parent requests reuse authoritative school services; no SMS here."""

import hashlib
import json
from datetime import date, timedelta
from functools import wraps

from django.db import IntegrityError, transaction
from django.utils import timezone

from attendance.models import AttendanceMark, AttendanceSession
from attendance.services.sessions import correct_student_attendance
from audit.services import record_event
from common.errors import ApiError
from documents.models import DocumentStatus, GeneratedDocument
from excuses.services.excuses import _validate_targets, create_excuse
from excuses.validators import validate_excuse_attachment
from memberships.models import SchoolRole
from parents.request_models import (
    AttendanceCorrectionRequest,
    FamilyPublication,
    ParentExcuseAttachment,
    ParentExcuseRequest,
    ParentNotification,
    ParentRequestStatus,
)
from subscriptions.entitlements import require_storage_capacity

OPEN_STATUSES = (ParentRequestStatus.PENDING, ParentRequestStatus.NEEDS_INFO)


def _missing():
    return ApiError("NOT_FOUND", "المورد المطلوب غير موجود.", status_code=404)


def ensure_active(relation, user=None):
    if relation.status != "ACTIVE" or (
        user and (relation.user_id != user.id or not user.is_active)
    ):
        raise _missing()
    if relation.student.school_id != relation.school_id:
        raise _missing()


def _parent_write(service):
    """Recheck ownership, contact revision and subscription even for direct calls."""

    @wraps(service)
    def scoped(*, relation, user, **kwargs):
        from parents.access import parent_scope

        if not user.is_active:
            raise _missing()
        with parent_scope(user, relation.id, write=True, lock=True) as current:
            return service(relation=current, user=user, **kwargs)

    return scoped


def _audit(action, obj, actor, request=None, **metadata):
    record_event(
        action,
        school=obj.school,
        actor=actor,
        request=request,
        target_type=type(obj).__name__,
        target_id=obj.id,
        metadata=metadata,
    )


def notify(relation, *, kind, key, title, body="", requires_action=False):
    return ParentNotification.objects.get_or_create(
        school=relation.school,
        relation=relation,
        user_id=relation.user_id,
        dedup_key=key,
        defaults={
            "kind": kind,
            "title": title,
            "body": body[:500],
            "requires_action": requires_action,
        },
    )[0]


def _targets(relation, targets):
    targets = _validate_targets(relation.school, relation.student, targets, allow_future=False)
    for target in targets:
        absent = AttendanceMark.objects.filter(
            school=relation.school,
            student=relation.student,
            session__attendance_date=target["attendance_date"],
            session__status="SUBMITTED",
            status="ABSENT",
        )
        if target.get("period_sequence") is not None:
            absent = absent.filter(session__period_sequence=target["period_sequence"])
        if not absent.exists():
            raise ApiError("PARENT_EXCUSE_NO_ABSENCE", "لا يوجد غياب معتمد ضمن النطاق المحدد.")
    serialized = sorted(
        [
            {
                "attendance_date": t["attendance_date"].isoformat(),
                "period_sequence": t.get("period_sequence"),
            }
            for t in targets
        ],
        key=lambda t: (t["attendance_date"], t["period_sequence"] or 0),
    )
    fingerprint = hashlib.sha256(json.dumps(serialized, sort_keys=True).encode()).hexdigest()
    return serialized, fingerprint


@_parent_write
def submit_excuse(*, relation, user, reason_type, notes, targets, request=None):
    ensure_active(relation, user)
    serialized, fingerprint = _targets(relation, targets)
    try:
        with transaction.atomic():
            obj = ParentExcuseRequest.objects.create(
                school=relation.school,
                student=relation.student,
                relation=relation,
                requester=user,
                reason_type=reason_type,
                notes=notes,
                targets=serialized,
                target_fingerprint=fingerprint,
            )
            _audit("PARENT_EXCUSE_SUBMITTED", obj, user, request, targets=len(targets))
            return obj
    except IntegrityError as exc:
        raise ApiError(
            "PARENT_REQUEST_DUPLICATE", "يوجد طلب مفتوح للنطاق نفسه.", status_code=409
        ) from exc


@_parent_write
def resubmit_excuse(*, obj, relation, user, notes=None, targets=None, request=None):
    ensure_active(relation, user)
    with transaction.atomic():
        obj = ParentExcuseRequest.objects.select_for_update().get(
            id=obj.id, relation=relation, requester=user
        )
        if obj.status != ParentRequestStatus.NEEDS_INFO:
            raise ApiError("PARENT_REQUEST_STATE", "الطلب لا يحتاج إلى استكمال.", status_code=409)
        if notes is not None:
            obj.notes = notes
        if targets is not None:
            obj.targets, obj.target_fingerprint = _targets(relation, targets)
        obj.status = ParentRequestStatus.PENDING
        try:
            with transaction.atomic():
                obj.save()
        except IntegrityError as exc:
            raise ApiError(
                "PARENT_REQUEST_DUPLICATE", "يوجد طلب مفتوح للنطاق نفسه.", status_code=409
            ) from exc
        _audit("PARENT_EXCUSE_RESUBMITTED", obj, user, request)
    return obj


@_parent_write
def upload_attachment(*, obj, relation, user, uploaded_file, request=None):
    ensure_active(relation, user)
    mime_type = validate_excuse_attachment(uploaded_file)
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    attachment = None
    try:
        with transaction.atomic():
            from schools.models import School

            # KEY SHARE from parent_scope must not be upgraded to FOR UPDATE:
            # concurrent parents may each hold that shared lock. NO KEY UPDATE
            # still serializes quota writes and conflicts with ordinary capacity locks.
            School.objects.select_for_update(no_key=True).only("id").get(id=relation.school_id)
            obj = ParentExcuseRequest.objects.select_for_update().get(
                id=obj.id, relation=relation, requester=user
            )
            if obj.status not in OPEN_STATUSES:
                raise ApiError(
                    "PARENT_REQUEST_STATE", "لا يمكن إضافة مرفقات بعد قرار الطلب.", status_code=409
                )
            if obj.attachments.count() >= 5:
                raise ApiError("EXCUSE_ATTACHMENT_INVALID", "الحد الأعلى خمسة مرفقات لكل طلب.")
            require_storage_capacity(relation.school, adding_bytes=uploaded_file.size)
            attachment = ParentExcuseAttachment(
                school=relation.school,
                parent_request=obj,
                file=uploaded_file,
                original_filename=uploaded_file.name[:255],
                mime_type=mime_type,
                size_bytes=uploaded_file.size,
                checksum=digest.hexdigest(),
                uploaded_by=user,
            )
            attachment.save()
            _audit(
                "PARENT_ATTACHMENT_UPLOADED",
                attachment,
                user,
                request,
                size_bytes=attachment.size_bytes,
            )
        return attachment
    except Exception:
        if attachment and attachment.file and attachment.file._committed:
            attachment.file.delete(save=False)
        raise


@_parent_write
def cancel_request(*, obj, relation, user, request=None):
    ensure_active(relation, user)
    with transaction.atomic():
        obj = (
            type(obj).objects.select_for_update().get(id=obj.id, relation=relation, requester=user)
        )
        if obj.status not in OPEN_STATUSES:
            raise ApiError("PARENT_REQUEST_STATE", "لا يمكن إلغاء طلب صدر قراره.", status_code=409)
        obj.status = ParentRequestStatus.CANCELLED
        obj.save(update_fields=["status", "updated_at"])
        _audit("PARENT_REQUEST_CANCELLED", obj, user, request)
    return obj


@_parent_write
def submit_correction(*, relation, user, session_id, reason, request=None):
    ensure_active(relation, user)
    session = AttendanceSession.objects.filter(
        id=session_id,
        school=relation.school,
        status="SUBMITTED",
        marks__student=relation.student,
        marks__status="ABSENT",
    ).first()
    if session is None:
        raise _missing()
    try:
        with transaction.atomic():
            obj = AttendanceCorrectionRequest.objects.create(
                school=relation.school,
                student=relation.student,
                relation=relation,
                requester=user,
                session=session,
                reason=reason,
            )
            _audit("PARENT_CORRECTION_SUBMITTED", obj, user, request, session_id=session.id)
        return obj
    except IntegrityError as exc:
        raise ApiError(
            "PARENT_REQUEST_DUPLICATE", "يوجد طلب مراجعة مفتوح لهذا الغياب.", status_code=409
        ) from exc


def decide_request(
    *, obj, school, membership, decision, note, expected_updated_at=None, request=None
):
    if not set(membership.role_codes()) & {SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL}:
        raise ApiError("PERMISSION_DENIED", "ليست لديك صلاحية مراجعة الطلب.", status_code=403)
    if decision not in ("APPROVED", "REJECTED", "NEEDS_INFO"):
        raise ApiError("VALIDATION_ERROR", "قرار المراجعة غير صحيح.")
    if decision != "APPROVED" and not note.strip():
        raise ApiError("VALIDATION_ERROR", "سبب القرار مطلوب.")
    if isinstance(obj, AttendanceCorrectionRequest) and decision == "NEEDS_INFO":
        raise ApiError("VALIDATION_ERROR", "يقبل طلب التصحيح الموافقة أو الرفض.")
    with transaction.atomic():
        # Match import and parent writes: school, student, relation, then request.
        from parents.access import lock_parent_school
        from parents.models import GuardianStudentRelation
        from students.models import Student

        lock_parent_school(school.id)
        Student.objects.select_for_update().get(id=obj.student_id, school=school)
        relation = (
            GuardianStudentRelation.objects.select_for_update(of=("self",))
            .select_related("student", "school")
            .get(id=obj.relation_id, school=school)
        )
        obj = (
            type(obj)
            .objects.select_for_update(of=("self",))
            .select_related("relation__student", "relation__school")
            .get(id=obj.id, school=school)
        )
        if obj.status not in OPEN_STATUSES:
            raise ApiError(
                "PARENT_REQUEST_ALREADY_DECIDED", "سبق إصدار قرار الطلب.", status_code=409
            )
        if decision == "APPROVED":
            if relation.status != "ACTIVE":
                raise ApiError(
                    "PARENT_RELATION_INACTIVE",
                    "أعد اعتماد علاقة ولي الأمر قبل الموافقة على الطلب.",
                    status_code=409,
                )
            if isinstance(obj, ParentExcuseRequest):
                targets = [
                    {**t, "attendance_date": date.fromisoformat(t["attendance_date"])}
                    for t in obj.targets
                ]
                # Serialize review with session corrections, then revalidate every
                # stored target against current submitted ABSENT truth.
                list(
                    AttendanceSession.objects.select_for_update(of=("self",))
                    .filter(
                        school=school,
                        attendance_date__in={target["attendance_date"] for target in targets},
                        marks__student_id=obj.student_id,
                        marks__status="ABSENT",
                    )
                    .order_by("id")
                )
                _targets(relation, targets)
                obj.administrative_excuse = create_excuse(
                    school=school,
                    membership=membership,
                    student=obj.student,
                    reason_type=obj.reason_type,
                    notes=obj.notes,
                    targets=targets,
                    approve_immediately=True,
                    request=request,
                )
            else:
                session = AttendanceSession.objects.select_for_update().get(
                    id=obj.session_id, school=school
                )
                if (
                    session.status != "SUBMITTED"
                    or not AttendanceMark.objects.filter(
                        school=school, session=session, student_id=obj.student_id, status="ABSENT"
                    ).exists()
                ):
                    raise ApiError(
                        "PARENT_CORRECTION_NO_ABSENCE",
                        "لم يعد الغياب المطلوب تصحيحه موجوداً في حصة معتمدة.",
                        status_code=409,
                    )
                correct_student_attendance(
                    session_id=session.id,
                    student_id=obj.student_id,
                    school=school,
                    membership=membership,
                    status="PRESENT",
                    reason=note or obj.reason,
                    expected_updated_at=expected_updated_at or session.updated_at,
                    request=request,
                )
        obj.status = decision
        obj.decision_note = note
        obj.reviewed_by_membership = membership
        obj.reviewed_at = timezone.now()
        obj.save()
        _audit("PARENT_REQUEST_DECIDED", obj, membership.user, request, decision=decision)
        notify(
            obj.relation,
            kind="EXCUSE" if isinstance(obj, ParentExcuseRequest) else "CORRECTION",
            key=f"request:{type(obj).__name__}:{obj.id}:{obj.updated_at.isoformat()}",
            title="صدر قرار طلب ولي الأمر",
            body=note or obj.get_status_display(),
            requires_action=decision == "NEEDS_INFO",
        )
    return obj


def lock_family_document(*, document_id, school, student):
    """Use the same warning-before-document order as generation and warning voiding."""
    from student_warnings.models import StudentWarning

    indexed = (
        GeneratedDocument.objects.filter(id=document_id, school=school, student=student)
        .values("warning_id")
        .first()
    )
    if indexed is None:
        raise _missing()
    if indexed["warning_id"]:
        warning = (
            StudentWarning.objects.select_for_update()
            .filter(id=indexed["warning_id"], school=school, student=student)
            .first()
        )
        if warning is None:
            raise _missing()
    document = (
        GeneratedDocument.objects.select_for_update(of=("self",))
        .select_related("warning")
        .filter(id=document_id, school=school, student=student)
        .first()
    )
    if document is None or document.warning_id != indexed["warning_id"]:
        raise _missing()
    return document


def publish_family(
    *,
    school,
    membership,
    student,
    title,
    body,
    required_action="",
    due_at=None,
    case=None,
    document=None,
    request=None,
):
    with transaction.atomic():
        from counseling.models import CounselorCase
        from parents.access import lock_parent_school
        from students.models import Student

        if membership.school_id != school.id:
            raise _missing()
        lock_parent_school(school.id)
        student = Student.objects.select_for_update().filter(id=student.id, school=school).first()
        if student is None:
            raise _missing()
        if case:
            case = (
                CounselorCase.objects.select_for_update()
                .filter(id=case.id, school=school, student=student)
                .first()
            )
            if case is None:
                raise _missing()
        roles = set(membership.role_codes())
        administrators = roles & {SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL}
        if not administrators:
            if (
                SchoolRole.COUNSELOR not in roles
                or not case
                or case.assigned_counselor_membership_id != membership.id
            ):
                raise ApiError(
                    "PERMISSION_DENIED",
                    "النشر الإرشادي متاح للمرشد المسؤول عن الحالة فقط.",
                    status_code=403,
                )
            if document:
                raise ApiError(
                    "PERMISSION_DENIED",
                    "نشر المستندات الإدارية يتطلب صلاحية المدير أو الوكيل.",
                    status_code=403,
                )
        if document:
            document = lock_family_document(document_id=document.id, school=school, student=student)
            if document.status != DocumentStatus.READY or (
                document.warning_id and document.warning.status != "ISSUED"
            ):
                raise ApiError(
                    "DOCUMENT_NOT_READY", "المستند غير متاح للنشر للأسرة.", status_code=409
                )
        obj = FamilyPublication.objects.create(
            school=school,
            student=student,
            case=case,
            document=document,
            title=title,
            body=body,
            required_action=required_action,
            due_at=due_at,
            published_by_membership=membership,
            published_at=timezone.now(),
        )
        _audit(
            "FAMILY_CONTENT_PUBLISHED", obj, membership.user, request, has_document=bool(document)
        )
        from parents.models import GuardianStudentRelation

        for relation in GuardianStudentRelation.objects.filter(
            school=school, student=student, status="ACTIVE"
        ):
            notify(
                relation,
                kind="FAMILY_PUBLICATION",
                key=f"publication:{obj.id}",
                title=title,
                body=required_action,
                requires_action=bool(required_action),
            )
    return obj


def revoke_publication(*, publication, membership, reason, request=None):
    with transaction.atomic():
        from counseling.models import CounselorCase
        from parents.access import lock_parent_school
        from students.models import Student

        lock_parent_school(membership.school_id)
        student = (
            Student.objects.select_for_update()
            .filter(id=publication.student_id, school=membership.school)
            .first()
        )
        if student is None:
            raise _missing()
        publication = (
            FamilyPublication.objects.select_for_update()
            .filter(id=publication.id, school=membership.school, student=student)
            .first()
        )
        if publication is None:
            raise _missing()
        roles = set(membership.role_codes())
        if not roles & {SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL}:
            case = (
                CounselorCase.objects.select_for_update()
                .filter(id=publication.case_id, school=membership.school, student=student)
                .first()
                if publication.case_id
                else None
            )
            if (
                SchoolRole.COUNSELOR not in roles
                or not case
                or case.assigned_counselor_membership_id != membership.id
            ):
                raise _missing()
        if publication.revoked_at:
            return publication
        publication.revoked_at = timezone.now()
        publication.revoked_by_membership = membership
        publication.revocation_reason = reason
        publication.save()
        ParentNotification.objects.filter(
            school=publication.school,
            relation__student=student,
            kind="FAMILY_PUBLICATION",
            dedup_key=f"publication:{publication.id}",
        ).update(
            title="أُلغي المحتوى المنشور للأسرة",
            body="",
            requires_action=False,
            action_completed_at=publication.revoked_at,
            updated_at=publication.revoked_at,
        )
        _audit("FAMILY_CONTENT_REVOKED", publication, membership.user, request)
    return publication


@transaction.atomic
def sync_activity_notifications(relation):
    """Idempotent inbox catch-up from submitted truth, independent of school SMS."""
    from devices.models import SchoolArrival
    from parents.access import lock_parent_school
    from parents.models import GuardianStudentRelation
    from parents.request_models import WarningAcknowledgement
    from student_warnings.models import StudentWarning

    lock_parent_school(relation.school_id)
    # Lock the relation before warnings/FK inserts, matching explicit acknowledgement.
    relation = (
        GuardianStudentRelation.objects.select_for_update(no_key=True, of=("self",))
        .select_related("school", "student")
        .filter(
            id=relation.id, school_id=relation.school_id, user_id=relation.user_id, status="ACTIVE"
        )
        .first()
    )
    if relation is None:
        return
    since = timezone.localdate() - timedelta(days=30)
    pending = {}

    def add(kind, key, title, body, requires_action=False, action_completed_at=None):
        pending[key] = ParentNotification(
            school=relation.school,
            relation=relation,
            user_id=relation.user_id,
            kind=kind,
            dedup_key=key,
            title=title,
            body=body[:500],
            requires_action=requires_action,
            action_completed_at=action_completed_at,
        )

    absences = (
        AttendanceMark.objects.filter(
            school=relation.school,
            student=relation.student,
            status="ABSENT",
            session__status="SUBMITTED",
            session__attendance_date__gte=since,
        )
        .select_related("session")
        .order_by("session_id")
    )
    for mark in absences:
        add(
            kind="ABSENCE",
            key=f"absence:{mark.session_id}",
            title="تم تسجيل غياب حصة",
            body=(
                f"{mark.session.attendance_date.isoformat()} — الحصة {mark.session.period_sequence}"
            ),
        )
    for arrival in SchoolArrival.objects.filter(
        school=relation.school, student=relation.student, status="LATE", attendance_date__gte=since
    ):
        add(
            kind="MORNING_LATE",
            key=f"arrival:{arrival.id}",
            title="تأخر صباحي مسجل",
            body=f"{arrival.attendance_date.isoformat()} — {arrival.counted_late_minutes} دقيقة",
        )
    warnings = list(
        StudentWarning.objects.select_for_update()
        .filter(school=relation.school, student=relation.student)
        .order_by("id")
    )
    acknowledged = dict(
        WarningAcknowledgement.objects.filter(
            relation=relation,
            user_id=relation.user_id,
            warning_id__in=[warning.id for warning in warnings],
        ).values_list("warning_id", "acknowledged_at")
    )
    for warning in warnings:
        if warning.status != "ISSUED":
            continue
        add(
            kind="WARNING",
            key=f"warning:{warning.id}",
            title="إنذار طالب صادر",
            body=f"{warning.get_warning_type_display()} — {warning.get_level_display()}",
            requires_action=True,
            action_completed_at=acknowledged.get(warning.id),
        )
    if pending:
        existing = set(
            ParentNotification.objects.filter(
                relation=relation,
                dedup_key__in=pending,
            ).values_list("dedup_key", flat=True)
        )
        ParentNotification.objects.bulk_create(
            [obj for key, obj in pending.items() if key not in existing],
            ignore_conflicts=True,
        )
    acknowledged_keys = {f"warning:{warning_id}": at for warning_id, at in acknowledged.items()}
    if acknowledged_keys:
        completed = list(
            ParentNotification.objects.filter(
                relation=relation,
                kind="WARNING",
                dedup_key__in=acknowledged_keys,
                action_completed_at__isnull=True,
            )
        )
        for notice in completed:
            notice.action_completed_at = acknowledged_keys[notice.dedup_key]
            notice.updated_at = timezone.now()
        if completed:
            ParentNotification.objects.bulk_update(completed, ["action_completed_at", "updated_at"])
    # A cancelled warning no longer asks the family to acknowledge it. Keep the
    # historical notice but reflect the authoritative cancellation.
    voided_keys = [f"warning:{warning.id}" for warning in warnings if warning.status == "VOIDED"]
    if voided_keys:
        ParentNotification.objects.filter(
            relation=relation,
            kind="WARNING",
            dedup_key__in=voided_keys,
            requires_action=True,
        ).update(
            requires_action=False,
            action_completed_at=timezone.now(),
            title="أُلغي إنذار الطالب",
            body="راجع حالة الإنذار المحدثة في سجل الطالب.",
        )
