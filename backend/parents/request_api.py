"""Narrow relation-scoped family DTOs and separate school review endpoints."""

from django.db import transaction
from django.db.models import BooleanField, Case, Count, F, Prefetch, Q, Value, When
from django.http import FileResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param

from audit.services import record_event
from common.errors import ApiError
from common.pagination import DefaultPagination
from common.tenant_rls import tenant_context
from counseling.models import CaseEventType, CounselorCase
from documents.models import GeneratedDocument
from documents.services.generation import open_for_download
from excuses.models import ExcuseReasonType
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from parents import request_serializers as output
from parents import request_services as services
from parents.access import (
    ParentAPIView,
    not_found,
    owned_relation_index,
    parent_school_read,
    parent_scope,
    relation_school_groups,
)
from parents.counseling_integration import attach_family_action_progress, record_family_case_event
from parents.rate_limit import consume
from parents.request_models import (
    AttendanceCorrectionRequest,
    FamilyPublication,
    FamilyPublicationAcknowledgement,
    ParentExcuseRequest,
    ParentNotification,
    WarningAcknowledgement,
)
from student_warnings.models import StudentWarning
from students.models import Student

REVIEW_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)
FAMILY_WRITE_LIMIT = 120


class FamilyRequestAPIView(ParentAPIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method == "POST":
            consume(kind="family-write", value=str(request.user.id), limit=FAMILY_WRITE_LIMIT)


def _pagination_window(request):
    query = output.PaginationQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    page = query.validated_data.get("page", 1)
    size = query.validated_data.get("page_size", DefaultPagination.page_size)
    return page, size, (page - 1) * size


def _paged(queryset, request, row):
    _pagination_window(request)
    paginator = DefaultPagination()
    items = paginator.paginate_queryset(queryset, request)
    return Response(
        {
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "items": [row(obj) for obj in items],
        }
    )


def _aggregate_page(request, items, count, *, page, size, offset, sort_field="created_at"):
    if page > 1 and offset >= count:
        raise not_found()
    uri = request.build_absolute_uri()
    ordered = sorted(
        items,
        key=lambda item: (item[sort_field], item["id"], item.get("type", item.get("kind", ""))),
        reverse=True,
    )
    return {
        "count": count,
        "next": replace_query_param(uri, "page", page + 1) if offset + size < count else None,
        "previous": replace_query_param(uri, "page", page - 1) if page > 1 else None,
        "items": ordered[offset : offset + size],
    }


class TargetSerializer(serializers.Serializer):
    attendance_date = serializers.DateField()
    period_sequence = serializers.IntegerField(
        min_value=1, max_value=30, allow_null=True, required=False
    )


class ExcuseInputSerializer(serializers.Serializer):
    reason_type = serializers.ChoiceField(choices=ExcuseReasonType.choices)
    notes = serializers.CharField(max_length=500, allow_blank=True, required=False, default="")
    targets = TargetSerializer(many=True, allow_empty=False)


class ResubmitSerializer(serializers.Serializer):
    notes = serializers.CharField(max_length=500, allow_blank=True, required=False)
    targets = TargetSerializer(many=True, allow_empty=False, required=False)


class CorrectionInputSerializer(serializers.Serializer):
    session_id = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500, allow_blank=False)


class DecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["APPROVED", "REJECTED", "NEEDS_INFO"])
    note = serializers.CharField(max_length=500, allow_blank=True, required=False, default="")
    expected_updated_at = serializers.DateTimeField(required=False)


class PublicationSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=180)
    body = serializers.CharField(max_length=4000, allow_blank=True, required=False, default="")
    required_action = serializers.CharField(
        max_length=500, allow_blank=True, required=False, default=""
    )
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    case_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    document_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)


def _data(serializer_class, request):
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _iso(value):
    return value.isoformat() if value else None


def attachment_row(attachment):
    return {
        "id": attachment.id,
        "filename": attachment.original_filename,
        "mime_type": attachment.mime_type,
        "size_bytes": attachment.size_bytes,
    }


def _reviewer_name(obj):
    if not obj.reviewed_by_membership_id:
        return ""
    membership = obj.reviewed_by_membership
    if membership is None:
        return "موظف المدرسة"
    profile = getattr(membership, "staff_profile", None)
    return (
        (profile.display_name if profile else "")
        or membership.user.get_full_name()
        or "موظف المدرسة"
    )


def excuse_row(obj, *, staff=False):
    row = {
        "id": obj.id,
        "type": "EXCUSE",
        "relation_id": obj.relation_id,
        "student_id": obj.student_id,
        "status": obj.status,
        "reason_type": obj.reason_type,
        "notes": obj.notes,
        "targets": obj.targets,
        "decision_note": obj.decision_note,
        "administrative_excuse_id": obj.administrative_excuse_id,
        "created_at": _iso(obj.created_at),
        "updated_at": _iso(obj.updated_at),
        "attachments": [attachment_row(a) for a in obj.attachments.all()],
    }
    if staff:
        row["student_name"] = obj.student.full_name
        row["requester_name"] = obj.requester.get_full_name() or "ولي الأمر"
        row["reviewed_at"] = _iso(obj.reviewed_at)
        row["reviewer_name"] = _reviewer_name(obj)
    return row


def correction_row(obj, *, staff=False):
    row = {
        "id": obj.id,
        "type": "CORRECTION",
        "relation_id": obj.relation_id,
        "student_id": obj.student_id,
        "session_id": obj.session_id,
        "attendance_date": obj.session.attendance_date.isoformat(),
        "period_sequence": obj.session.period_sequence,
        "session_updated_at": _iso(obj.session.updated_at),
        "status": obj.status,
        "reason": obj.reason,
        "decision_note": obj.decision_note,
        "created_at": _iso(obj.created_at),
        "updated_at": _iso(obj.updated_at),
    }
    if staff:
        row["student_name"] = obj.student.full_name
        row["requester_name"] = obj.requester.get_full_name() or "ولي الأمر"
        row["reviewed_at"] = _iso(obj.reviewed_at)
        row["reviewer_name"] = _reviewer_name(obj)
    return row


def _excuse(relation, request_id):
    obj = (
        ParentExcuseRequest.objects.filter(
            id=request_id, relation=relation, requester_id=relation.user_id
        )
        .prefetch_related("attachments")
        .first()
    )
    if obj is None:
        raise not_found()
    return obj


def _correction(relation, request_id):
    obj = (
        AttendanceCorrectionRequest.objects.filter(
            id=request_id, relation=relation, requester_id=relation.user_id
        )
        .select_related("session")
        .first()
    )
    if obj is None:
        raise not_found()
    return obj


def _file(field, *, filename, mime_type):
    try:
        handle = field.open("rb")
    except FileNotFoundError as exc:
        raise ApiError("DOCUMENT_FILE_MISSING", "المرفق غير متاح حالياً.", status_code=409) from exc
    response = FileResponse(handle, as_attachment=True, filename=filename, content_type=mime_type)
    response["Cache-Control"] = "no-store, private"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class ParentExcusesView(FamilyRequestAPIView):
    @extend_schema(
        responses=output.ExcusePageOutputSerializer, parameters=[output.PaginationQuerySerializer]
    )
    def get(self, request, relation_id):
        with parent_scope(request.user, relation_id) as relation:
            items = (
                ParentExcuseRequest.objects.filter(relation=relation, requester=request.user)
                .prefetch_related("attachments")
                .order_by("-created_at", "-id")
            )
            return _paged(items, request, excuse_row)

    @extend_schema(request=ExcuseInputSerializer, responses={201: output.ExcuseOutputSerializer})
    def post(self, request, relation_id):
        data = _data(ExcuseInputSerializer, request)
        with parent_scope(request.user, relation_id, write=True, lock=True) as relation:
            obj = services.submit_excuse(
                relation=relation, user=request.user, request=request, **data
            )
            return Response(excuse_row(obj), status=201)


class ParentExcuseResubmitView(FamilyRequestAPIView):
    @extend_schema(request=ResubmitSerializer, responses=output.ExcuseOutputSerializer)
    def post(self, request, relation_id, request_id):
        data = _data(ResubmitSerializer, request)
        with parent_scope(request.user, relation_id, write=True, lock=True) as relation:
            obj = services.resubmit_excuse(
                obj=_excuse(relation, request_id),
                relation=relation,
                user=request.user,
                request=request,
                **data,
            )
            return Response(excuse_row(obj))


class ParentExcuseCancelView(FamilyRequestAPIView):
    @extend_schema(request=None, responses=output.ExcuseOutputSerializer)
    def post(self, request, relation_id, request_id):
        with parent_scope(request.user, relation_id, write=True, lock=True) as relation:
            obj = services.cancel_request(
                obj=_excuse(relation, request_id),
                relation=relation,
                user=request.user,
                request=request,
            )
            return Response(excuse_row(obj))


class ParentExcuseAttachmentsView(FamilyRequestAPIView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"file": {"type": "string", "format": "binary"}},
                "required": ["file"],
            }
        },
        responses={201: output.AttachmentOutputSerializer},
    )
    def post(self, request, relation_id, request_id):
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            raise ApiError("VALIDATION_ERROR", "أرفق ملفاً صالحاً.")
        with parent_scope(request.user, relation_id, write=True, lock=True) as relation:
            obj = _excuse(relation, request_id)
            attachment = services.upload_attachment(
                obj=obj,
                relation=relation,
                user=request.user,
                uploaded_file=uploaded_file,
                request=request,
            )
            return Response(attachment_row(attachment), status=201)


class ParentAttachmentDownloadView(ParentAPIView):
    @extend_schema(
        responses={
            (200, "application/pdf"): OpenApiTypes.BINARY,
            (200, "image/png"): OpenApiTypes.BINARY,
            (200, "image/jpeg"): OpenApiTypes.BINARY,
        }
    )
    def get(self, request, relation_id, request_id, attachment_id):
        with parent_scope(request.user, relation_id, lock=True) as relation:
            obj = _excuse(relation, request_id)
            attachment = obj.attachments.filter(id=attachment_id, school=relation.school).first()
            if attachment is None:
                raise not_found()
            record_event(
                "PARENT_ATTACHMENT_DOWNLOADED",
                school=relation.school,
                actor=request.user,
                request=request,
                target_type="ParentExcuseAttachment",
                target_id=attachment.id,
            )
            return _file(
                attachment.file,
                filename=attachment.original_filename,
                mime_type=attachment.mime_type,
            )


class ParentCorrectionsView(FamilyRequestAPIView):
    @extend_schema(
        responses=output.CorrectionPageOutputSerializer,
        parameters=[output.PaginationQuerySerializer],
    )
    def get(self, request, relation_id):
        with parent_scope(request.user, relation_id) as relation:
            items = (
                AttendanceCorrectionRequest.objects.filter(
                    relation=relation, requester=request.user
                )
                .select_related("session")
                .order_by("-created_at", "-id")
            )
            return _paged(items, request, correction_row)

    @extend_schema(
        request=CorrectionInputSerializer, responses={201: output.CorrectionOutputSerializer}
    )
    def post(self, request, relation_id):
        data = _data(CorrectionInputSerializer, request)
        with parent_scope(request.user, relation_id, write=True, lock=True) as relation:
            obj = services.submit_correction(
                relation=relation, user=request.user, request=request, **data
            )
            return Response(correction_row(obj), status=201)


class ParentCorrectionCancelView(FamilyRequestAPIView):
    @extend_schema(request=None, responses=output.CorrectionOutputSerializer)
    def post(self, request, relation_id, request_id):
        with parent_scope(request.user, relation_id, write=True, lock=True) as relation:
            obj = services.cancel_request(
                obj=_correction(relation, request_id),
                relation=relation,
                user=request.user,
                request=request,
            )
            return Response(correction_row(obj))


def _publication(relation, publication_id, *, lock=False):
    queryset = FamilyPublication.objects.filter(
        id=publication_id,
        school=relation.school,
        student=relation.student,
        revoked_at__isnull=True,
    )
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    obj = queryset.select_related("document__warning").first()
    if obj is None:
        raise not_found()
    if lock and obj.document_id:
        obj.document = services.lock_family_document(
            document_id=obj.document_id, school=relation.school, student=relation.student
        )
    return obj


def _available_document(publication):
    document = publication.document
    return bool(
        document
        and document.status == "READY"
        and (not document.warning_id or document.warning.status == "ISSUED")
    )


def _masked_parent_name(user):
    return f"ولي الأمر ••••{user.mobile[-4:]}" if user.mobile else "ولي الأمر"


def publication_row(obj, acknowledged_at=None, *, staff=False):
    row = {
        "id": obj.id,
        "student_id": obj.student_id,
        "title": obj.title,
        "body": obj.body,
        "required_action": obj.required_action,
        "due_at": _iso(obj.due_at),
        "published_at": _iso(obj.published_at),
        "revoked_at": _iso(obj.revoked_at),
        "acknowledged_at": _iso(acknowledged_at),
        "document": {"id": obj.document_id, "type": obj.document.document_type}
        if _available_document(obj)
        else None,
    }
    if staff:
        progress = getattr(obj, "family_action_progress", None)
        if progress is None:
            attach_family_action_progress([obj], obj.school_id)
            progress = obj.family_action_progress
        row.update(
            {
                "student_name": obj.student.full_name,
                "case_id": obj.case_id,
                "action_count": progress.get("action_count", 0),
                "completed_action_count": progress.get("completed_action_count", 0),
                "action_completed_at": _iso(progress.get("action_completed_at")),
                "action_overdue": bool(
                    not obj.revoked_at
                    and obj.due_at
                    and obj.due_at < timezone.now()
                    and progress.get("completed_action_count", 0) < progress.get("action_count", 0)
                ),
            }
        )
        acknowledgements = getattr(obj, "staff_acknowledgements", None)
        if acknowledgements is None:
            acknowledgements = list(
                obj.acknowledgements.filter(school=obj.school)
                .select_related("user")
                .order_by("-acknowledged_at", "-id")[:20]
            )
        row["ack_count"] = getattr(obj, "ack_count", None)
        if row["ack_count"] is None:
            row["ack_count"] = obj.acknowledgements.filter(school=obj.school).count()
        row["acknowledgements"] = [
            {
                "relation_id": acknowledgement.relation_id,
                "parent_name": _masked_parent_name(acknowledgement.user),
                "acknowledged_at": _iso(acknowledgement.acknowledged_at),
            }
            for acknowledgement in acknowledgements
        ]
    return row


class ParentPublicationsView(ParentAPIView):
    @extend_schema(
        responses=output.PublicationPageOutputSerializer,
        parameters=[output.PaginationQuerySerializer],
    )
    def get(self, request, relation_id):
        with parent_scope(request.user, relation_id) as relation:
            acknowledgements = dict(
                FamilyPublicationAcknowledgement.objects.filter(
                    relation=relation, user=request.user
                ).values_list("publication_id", "acknowledged_at")
            )
            items = (
                FamilyPublication.objects.filter(
                    school=relation.school, student=relation.student, revoked_at__isnull=True
                )
                .select_related("document__warning")
                .order_by("-published_at", "-id")
            )
            return _paged(
                items, request, lambda obj: publication_row(obj, acknowledgements.get(obj.id))
            )


class ParentPublicationDownloadView(ParentAPIView):
    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, relation_id, publication_id):
        with parent_scope(request.user, relation_id, lock=True) as relation:
            publication = _publication(relation, publication_id, lock=True)
            if not _available_document(publication):
                raise not_found()
            handle = open_for_download(publication.document)
            record_event(
                "PARENT_DOCUMENT_DOWNLOADED",
                school=relation.school,
                actor=request.user,
                request=request,
                target_type="GeneratedDocument",
                target_id=publication.document_id,
            )
            response = FileResponse(
                handle,
                as_attachment=True,
                filename=f"مستند-{publication.document_id}.pdf",
                content_type="application/pdf",
            )
            response["Cache-Control"] = "no-store, private"
            response["X-Content-Type-Options"] = "nosniff"
            return response


class ParentPublicationAcknowledgeView(FamilyRequestAPIView):
    @extend_schema(request=None, responses=output.AcknowledgementOutputSerializer)
    def post(self, request, relation_id, publication_id):
        with parent_scope(request.user, relation_id, write=True, lock=True) as relation:
            obj = _publication(relation, publication_id, lock=True)
            acknowledgement, created = FamilyPublicationAcknowledgement.objects.get_or_create(
                school=relation.school,
                relation=relation,
                user=request.user,
                publication=obj,
                defaults={"acknowledged_at": timezone.now()},
            )
            if created:
                record_family_case_event(obj, CaseEventType.FAMILY_CONTENT_ACKNOWLEDGED)
                record_event(
                    "FAMILY_PUBLICATION_ACKNOWLEDGED",
                    school=relation.school,
                    actor=request.user,
                    request=request,
                    target_type="FamilyPublication",
                    target_id=obj.id,
                )
            return Response({"acknowledged_at": _iso(acknowledgement.acknowledged_at)})


class ParentWarningsView(ParentAPIView):
    @extend_schema(
        responses=output.WarningPageOutputSerializer, parameters=[output.PaginationQuerySerializer]
    )
    def get(self, request, relation_id):
        with parent_scope(request.user, relation_id) as relation:
            acknowledgements = dict(
                WarningAcknowledgement.objects.filter(
                    relation=relation, user=request.user
                ).values_list("warning_id", "acknowledged_at")
            )
            publications = FamilyPublication.objects.filter(
                school=relation.school,
                student=relation.student,
                revoked_at__isnull=True,
                document__status="READY",
                document__warning__status="ISSUED",
            ).select_related("document")
            documents = {}
            for publication in publications:
                documents.setdefault(publication.document.warning_id, []).append(
                    {
                        "publication_id": publication.id,
                        "document_type": publication.document.document_type,
                        "status": publication.document.status,
                    }
                )
            items = StudentWarning.objects.filter(
                school=relation.school, student=relation.student
            ).order_by("-issued_at", "-id")
            return _paged(
                items,
                request,
                lambda obj: {
                    "id": obj.id,
                    "warning_type": obj.warning_type,
                    "level": obj.level,
                    "status": obj.status,
                    "issued_at": _iso(obj.issued_at),
                    "acknowledged_at": _iso(acknowledgements.get(obj.id)),
                    "required_action": "تأكيد الاطلاع" if obj.status == "ISSUED" else "",
                    "documents": documents.get(obj.id, []),
                },
            )


class ParentWarningAcknowledgeView(FamilyRequestAPIView):
    @extend_schema(request=None, responses=output.WarningAcknowledgementOutputSerializer)
    def post(self, request, relation_id, warning_id):
        with parent_scope(request.user, relation_id, write=True, lock=True) as relation:
            warning = (
                StudentWarning.objects.select_for_update()
                .filter(
                    id=warning_id, school=relation.school, student=relation.student, status="ISSUED"
                )
                .first()
            )
            if warning is None:
                raise not_found()
            acknowledgement, created = WarningAcknowledgement.objects.get_or_create(
                school=relation.school,
                relation=relation,
                user=request.user,
                warning=warning,
                defaults={"acknowledged_at": timezone.now()},
            )
            ParentNotification.objects.filter(
                school=relation.school,
                relation=relation,
                user=request.user,
                kind="WARNING",
                dedup_key=f"warning:{warning.id}",
                action_completed_at__isnull=True,
            ).update(action_completed_at=acknowledgement.acknowledged_at, updated_at=timezone.now())
            if created:
                record_event(
                    "PARENT_WARNING_ACKNOWLEDGED",
                    school=relation.school,
                    actor=request.user,
                    request=request,
                    target_type="StudentWarning",
                    target_id=warning.id,
                )
            return Response(
                {
                    "acknowledged_at": _iso(acknowledgement.acknowledged_at),
                    "meaning": "تأكيد الاطلاع لا يعني الموافقة على محتوى الإنذار.",
                }
            )


class ParentRequestsView(ParentAPIView):
    @extend_schema(
        responses=output.ParentRequestsPageOutputSerializer,
        parameters=[output.PaginationQuerySerializer],
    )
    def get(self, request):
        page, size, offset = _pagination_window(request)
        limit = offset + size
        items = []
        count = 0
        for index in owned_relation_index(request.user):
            if index["status"] != "ACTIVE":
                continue
            try:
                with parent_scope(request.user, index["id"]) as relation:
                    excuses = (
                        ParentExcuseRequest.objects.filter(
                            relation=relation, requester=request.user
                        )
                        .prefetch_related("attachments")
                        .order_by("-created_at", "-id")
                    )
                    corrections = (
                        AttendanceCorrectionRequest.objects.filter(
                            relation=relation, requester=request.user
                        )
                        .select_related("session")
                        .order_by("-created_at", "-id")
                    )
                    count += excuses.count() + corrections.count()
                    items.extend(excuse_row(obj) for obj in excuses[:limit])
                    items.extend(correction_row(obj) for obj in corrections[:limit])
            except ApiError as exc:
                if exc.status_code not in (403, 404):
                    raise
        return Response(_aggregate_page(request, items, count, page=page, size=size, offset=offset))


def notification_row(obj, *, relation=None):
    state = (
        "ACTION_COMPLETED"
        if obj.action_completed_at
        else "NEEDS_ACTION"
        if obj.requires_action
        else "READ"
        if obj.read_at
        else "NEW"
    )
    return {
        "id": obj.id,
        "relation_id": obj.relation_id,
        "student_name": relation.student.full_name if relation else None,
        "school_name": relation.school.name if relation else None,
        "kind": obj.kind,
        "title": obj.title,
        "body": obj.body,
        "state": state,
        "requires_action": obj.requires_action,
        "created_at": _iso(obj.created_at),
        "read_at": _iso(obj.read_at),
        "action_completed_at": _iso(obj.action_completed_at),
    }


class ParentNotificationsView(ParentAPIView):
    @extend_schema(
        responses=output.NotificationPageOutputSerializer,
        parameters=[output.NotificationQuerySerializer],
    )
    def get(self, request):
        query = output.NotificationQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        relation_id = query.validated_data.get("relation_id")
        page, size, offset = _pagination_window(request)
        limit = offset + size
        items = []
        count = 0
        index = [
            item for item in owned_relation_index(request.user)
            if relation_id is None or item["id"] == relation_id
        ]
        for school_id, group in relation_school_groups(index):
            try:
                with parent_school_read(
                    request.user, school_id, [item["id"] for item in group],
                ) as scope:
                    available = scope.current_relations()
                    initial_active = {item["id"] for item in group if item["status"] == "ACTIVE"}
                    for key, relation in available.items():
                        if key not in initial_active:
                            continue
                        services.sync_activity_notifications(relation)
                    current = scope.current_relations()
                    current = {
                        key: value for key, value in current.items() if key in initial_active
                    }
                    # Check withdrawal again in the page SQL, rather than trusting a
                    # relation object loaded before another sibling's synchronization.
                    active = Q(
                        relation_id__in=current,
                        relation__status="ACTIVE",
                        relation__student__merged_into__isnull=True,
                        relation__school__status="ACTIVE",
                    ) & (
                        Q(relation__contact_bound=False)
                        | Q(
                            relation__contact_revision=F(
                                "relation__student__guardian_contact_revision"
                            )
                        )
                    )
                    notices = (
                        ParentNotification.objects.filter(
                            relation_id__in=scope.owned_ids, user=request.user,
                            relation__user_id=request.user.pk,
                        )
                        .filter(Q(kind="RELATION_STATUS") | active)
                        .annotate(
                            parent_relation_available=Case(
                                When(active, then=Value(True)), default=Value(False),
                                output_field=BooleanField(),
                            )
                        ).order_by("-created_at", "-id")
                    )
                    count += notices.count()
                    items.extend(
                        notification_row(
                            obj,
                            relation=current.get(obj.relation_id)
                            if obj.parent_relation_available else None,
                        ) for obj in notices[:limit]
                    )
            except ApiError as exc:
                if exc.status_code not in (403, 404):
                    raise
        return Response(_aggregate_page(request, items, count, page=page, size=size, offset=offset))


class ParentNotificationReadView(FamilyRequestAPIView):
    complete_action = False

    @extend_schema(request=None, responses=output.NotificationOutputSerializer)
    def post(self, request, notification_id):
        for index in owned_relation_index(request.user):
            relation = None
            with tenant_context(school_id=index["school_id"], user_id=request.user.id):
                obj = ParentNotification.objects.filter(
                    id=notification_id, user=request.user, relation_id=index["id"]
                ).first()
                if obj is None:
                    continue
                if self.complete_action:
                    if index["status"] != "ACTIVE" or obj.kind == "RELATION_STATUS":
                        raise not_found()
                    with parent_scope(request.user, index["id"], write=True, lock=True) as relation:
                        obj = (
                            ParentNotification.objects.select_for_update()
                            .filter(id=notification_id, user=request.user, relation=relation)
                            .first()
                        )
                        if obj is None:
                            raise not_found()
                        if obj.kind == "FAMILY_PUBLICATION":
                            publication_id = obj.dedup_key.removeprefix("publication:")
                            if not publication_id.isdigit():
                                raise not_found()
                            publication = _publication(relation, int(publication_id), lock=True)
                            if not FamilyPublicationAcknowledgement.objects.filter(
                                publication=publication, relation=relation, user=request.user
                            ).exists():
                                raise ApiError(
                                    "ACKNOWLEDGEMENT_REQUIRED",
                                    "أكد الاطلاع على المحتوى المنشور أولاً.",
                                    status_code=409,
                                )
                        if obj.kind == "WARNING":
                            warning_id = obj.dedup_key.removeprefix("warning:")
                            if (
                                not warning_id.isdigit()
                                or not StudentWarning.objects.select_for_update()
                                .filter(
                                    id=int(warning_id),
                                    school=relation.school,
                                    student=relation.student,
                                    status="ISSUED",
                                )
                                .exists()
                            ):
                                raise not_found()
                            if not WarningAcknowledgement.objects.filter(
                                relation_id=index["id"],
                                user=request.user,
                                warning_id=int(warning_id),
                            ).exists():
                                raise ApiError(
                                    "ACKNOWLEDGEMENT_REQUIRED",
                                    "أكد الاطلاع على الإنذار أولاً.",
                                    status_code=409,
                                )
                        if not obj.requires_action:
                            raise ApiError("VALIDATION_ERROR", "لا يتطلب هذا التنبيه إجراءً.")
                        first_completion = obj.action_completed_at is None
                        obj.action_completed_at = obj.action_completed_at or timezone.now()
                        obj.save(update_fields=["action_completed_at", "updated_at"])
                        if obj.kind == "FAMILY_PUBLICATION" and first_completion:
                            record_family_case_event(
                                publication, CaseEventType.FAMILY_ACTION_COMPLETED
                            )
                else:
                    if index["status"] != "ACTIVE" and obj.kind != "RELATION_STATUS":
                        raise not_found()
                    if obj.kind != "RELATION_STATUS":
                        with parent_scope(request.user, index["id"], lock=True) as relation:
                            obj = (
                                ParentNotification.objects.select_for_update()
                                .filter(id=notification_id, user=request.user, relation=relation)
                                .first()
                            )
                            if obj is None:
                                raise not_found()
                            obj.read_at = obj.read_at or timezone.now()
                            obj.save(update_fields=["read_at", "updated_at"])
                    else:
                        with transaction.atomic():
                            obj = (
                                ParentNotification.objects.select_for_update()
                                .filter(
                                    id=notification_id,
                                    user=request.user,
                                    relation_id=index["id"],
                                    kind="RELATION_STATUS",
                                )
                                .first()
                            )
                            if obj is None:
                                raise not_found()
                            obj.read_at = obj.read_at or timezone.now()
                            obj.save(update_fields=["read_at", "updated_at"])
                return Response(notification_row(obj, relation=relation))
        raise not_found()


class ParentNotificationCompleteView(ParentNotificationReadView):
    complete_action = True


class StaffRequestsView(SchoolScopedAPIView):
    feature_key = "PARENT_PORTAL"
    read_roles = write_roles = REVIEW_ROLES

    @extend_schema(
        responses=output.StaffRequestsPageOutputSerializer,
        parameters=[output.PaginationQuerySerializer],
    )
    def get(self, request):
        page, size, offset = _pagination_window(request)
        limit = offset + size
        excuses = (
            ParentExcuseRequest.objects.filter(school=request.school)
            .select_related(
                "student", "requester", "reviewed_by_membership__user",
                "reviewed_by_membership__staff_profile",
            )
            .prefetch_related("attachments")
            .order_by("-created_at", "-id")
        )
        corrections = (
            AttendanceCorrectionRequest.objects.filter(school=request.school)
            .select_related(
                "student", "requester", "session", "reviewed_by_membership__user",
                "reviewed_by_membership__staff_profile",
            )
            .order_by("-created_at", "-id")
        )
        count = excuses.count() + corrections.count()
        items = [excuse_row(obj, staff=True) for obj in excuses[:limit]]
        items.extend(correction_row(obj, staff=True) for obj in corrections[:limit])
        payload = _aggregate_page(request, items, count, page=page, size=size, offset=offset)
        payload["excuses"] = [row for row in payload["items"] if row["type"] == "EXCUSE"]
        payload["corrections"] = [row for row in payload["items"] if row["type"] == "CORRECTION"]
        return Response(payload)


class StaffExcuseDetailView(SchoolScopedAPIView):
    feature_key = "PARENT_PORTAL"
    read_roles = write_roles = REVIEW_ROLES
    model = ParentExcuseRequest

    @extend_schema(responses=output.StaffExcuseOutputSerializer)
    def get(self, request, request_id):
        queryset = self.model.objects.filter(id=request_id, school=request.school).select_related(
            "student", "requester", "reviewed_by_membership__user",
            "reviewed_by_membership__staff_profile",
        )
        if self.model is ParentExcuseRequest:
            queryset = queryset.prefetch_related("attachments")
        else:
            queryset = queryset.select_related("session")
        obj = queryset.first()
        if obj is None:
            raise not_found()
        return Response(
            excuse_row(obj, staff=True)
            if isinstance(obj, ParentExcuseRequest)
            else correction_row(obj, staff=True)
        )


@extend_schema_view(get=extend_schema(responses=output.StaffCorrectionOutputSerializer))
class StaffCorrectionDetailView(StaffExcuseDetailView):
    model = AttendanceCorrectionRequest


class StaffExcuseDecisionView(SchoolScopedAPIView):
    feature_key = "PARENT_PORTAL"
    read_roles = write_roles = REVIEW_ROLES
    model = ParentExcuseRequest

    @extend_schema(request=DecisionSerializer, responses=output.ExcuseOutputSerializer)
    def post(self, request, request_id):
        data = _data(DecisionSerializer, request)
        obj = self.model.objects.filter(id=request_id, school=request.school).first()
        if obj is None:
            raise not_found()
        obj = services.decide_request(
            obj=obj, school=request.school, membership=request.membership, request=request, **data
        )
        return Response(
            excuse_row(obj) if isinstance(obj, ParentExcuseRequest) else correction_row(obj)
        )


@extend_schema_view(post=extend_schema(responses=output.CorrectionOutputSerializer))
class StaffCorrectionDecisionView(StaffExcuseDecisionView):
    model = AttendanceCorrectionRequest


class StaffAttachmentDownloadView(SchoolScopedAPIView):
    feature_key = "PARENT_PORTAL"
    read_roles = write_roles = REVIEW_ROLES

    @extend_schema(
        responses={
            (200, "application/pdf"): OpenApiTypes.BINARY,
            (200, "image/png"): OpenApiTypes.BINARY,
            (200, "image/jpeg"): OpenApiTypes.BINARY,
        }
    )
    def get(self, request, request_id, attachment_id):
        obj = ParentExcuseRequest.objects.filter(id=request_id, school=request.school).first()
        attachment = (
            obj.attachments.filter(id=attachment_id, school=request.school).first() if obj else None
        )
        if attachment is None:
            raise not_found()
        record_event(
            "PARENT_ATTACHMENT_DOWNLOADED",
            school=request.school,
            actor=request.user,
            request=request,
            target_type="ParentExcuseAttachment",
            target_id=attachment.id,
        )
        return _file(
            attachment.file, filename=attachment.original_filename, mime_type=attachment.mime_type
        )


class StaffPublicationsView(SchoolScopedAPIView):
    feature_key = "PARENT_PORTAL"
    read_roles = write_roles = (*REVIEW_ROLES, SchoolRole.COUNSELOR)

    @extend_schema(
        responses=output.StaffPublicationPageOutputSerializer,
        parameters=[output.PublicationQuerySerializer],
    )
    def get(self, request):
        items = (
            FamilyPublication.objects.filter(school=request.school)
            .select_related("document__warning", "student")
            .annotate(ack_count=Count("acknowledgements"))
            .prefetch_related(
                Prefetch(
                    "acknowledgements",
                    queryset=FamilyPublicationAcknowledgement.objects.filter(school=request.school)
                    .select_related("user")
                    .order_by("-acknowledged_at", "-id")[:20],
                    to_attr="staff_acknowledgements",
                )
            )
            .order_by("-published_at", "-id")
        )
        if not set(request.school_roles) & set(REVIEW_ROLES):
            items = items.filter(case__assigned_counselor_membership=request.membership)
        case_id = request.query_params.get("case_id")
        if case_id:
            if not case_id.isdigit() or int(case_id) < 1:
                raise ApiError("VALIDATION_ERROR", "معرف الحالة غير صحيح.")
            items = items.filter(case_id=int(case_id))
        _pagination_window(request)
        paginator = DefaultPagination()
        page_items = paginator.paginate_queryset(items, request)
        attach_family_action_progress(page_items, request.school.id)
        return Response(
            {
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "items": [publication_row(obj, staff=True) for obj in page_items],
            }
        )

    @extend_schema(
        request=PublicationSerializer, responses={201: output.StaffPublicationOutputSerializer}
    )
    def post(self, request):
        data = _data(PublicationSerializer, request)
        student = Student.objects.filter(id=data.pop("student_id"), school=request.school).first()
        if student is None:
            raise not_found()
        case_id, document_id = data.pop("case_id", None), data.pop("document_id", None)
        case = (
            CounselorCase.objects.filter(id=case_id, school=request.school, student=student).first()
            if case_id
            else None
        )
        document = (
            GeneratedDocument.objects.filter(id=document_id, school=request.school, student=student)
            .select_related("warning")
            .first()
            if document_id
            else None
        )
        if (case_id and case is None) or (document_id and document is None):
            raise not_found()
        obj = services.publish_family(
            school=request.school,
            membership=request.membership,
            student=student,
            case=case,
            document=document,
            request=request,
            **data,
        )
        return Response(publication_row(obj, staff=True), status=201)


class StaffPublicationRevokeView(SchoolScopedAPIView):
    feature_key = "PARENT_PORTAL"
    read_roles = write_roles = (*REVIEW_ROLES, SchoolRole.COUNSELOR)

    @extend_schema(request=ReasonSerializer, responses=output.StaffPublicationOutputSerializer)
    def post(self, request, publication_id):
        data = _data(ReasonSerializer, request)
        obj = FamilyPublication.objects.filter(id=publication_id, school=request.school).first()
        if obj is None:
            raise not_found()
        obj = services.revoke_publication(
            publication=obj, membership=request.membership, request=request, **data
        )
        return Response(publication_row(obj, staff=True))


class StaffAcknowledgementsView(SchoolScopedAPIView):
    feature_key = "PARENT_PORTAL"
    read_roles = write_roles = REVIEW_ROLES

    @extend_schema(
        responses=output.StaffAcknowledgementPageOutputSerializer,
        parameters=[output.PaginationQuerySerializer],
    )
    def get(self, request):
        page, size, offset = _pagination_window(request)
        limit = offset + size
        warning_acknowledgements = (
            WarningAcknowledgement.objects.filter(school=request.school)
            .select_related("relation__student", "user")
            .order_by("-acknowledged_at", "-id")
        )
        publication_acknowledgements = (
            FamilyPublicationAcknowledgement.objects.filter(school=request.school)
            .select_related("relation__student", "user")
            .order_by("-acknowledged_at", "-id")
        )

        def row(obj, kind, target_id):
            return {
                "id": obj.id,
                "type": kind,
                "target_id": target_id,
                "relation_id": obj.relation_id,
                "student_id": obj.relation.student_id,
                "student_name": obj.relation.student.full_name,
                "parent_name": _masked_parent_name(obj.user),
                "acknowledged_at": _iso(obj.acknowledged_at),
            }

        items = [row(obj, "WARNING", obj.warning_id) for obj in warning_acknowledgements[:limit]]
        items.extend(
            row(obj, "PUBLICATION", obj.publication_id)
            for obj in publication_acknowledgements[:limit]
        )
        return Response(
            _aggregate_page(
                request,
                items,
                warning_acknowledgements.count() + publication_acknowledgements.count(),
                page=page,
                size=size,
                offset=offset,
                sort_field="acknowledged_at",
            )
        )
