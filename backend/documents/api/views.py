"""واجهات المستندات المولدة (م12).

الأدوار (البنود 83-86): المدير والوكيل ينشئان ويعيدان المحاولة وينزلان؛ الإلغاء
للمدير وحده؛ **المرشد يرى البيانات الوصفية فقط ولا ينزّل**؛ المعلم محجوب كليًا.
"""

from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from common.pagination import DefaultPagination
from documents.api.serializers import (
    DocumentSerializer,
    GenerateDocumentSerializer,
    PreviewDocumentSerializer,
    VoidDocumentSerializer,
)
from documents.models import (
    RANGE_DOCUMENT_TYPES,
    WARNING_DOCUMENT_TYPES,
    DocumentStatus,
    DocumentType,
    GeneratedDocument,
)
from documents.services import generation as generation_service
from documents.services import snapshots as snapshot_service
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from student_actions.models import StudentActionType
from student_actions.services import create_student_action
from students.models import Student

DOCUMENT_WRITE_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)
DOCUMENT_READ_ROLES = (
    SchoolRole.SCHOOL_MANAGER,
    SchoolRole.VICE_PRINCIPAL,
    SchoolRole.COUNSELOR,
)
DOWNLOAD_ROLES = DOCUMENT_WRITE_ROLES  # المرشد يرى البيانات الوصفية ولا ينزّل (البند 85)
VOID_ROLES = (SchoolRole.SCHOOL_MANAGER,)

TYPE_LABELS = dict(DocumentType.choices)
STATUS_LABELS = dict(DocumentStatus.choices)

_NOT_FOUND = ApiError("DOCUMENT_NOT_FOUND", "المستند غير موجود.", status_code=404)

# التعهد يسجل معه إجراء «أخذ تعهد» بعد جاهزية المستند (البندان 68-69)
ACTION_FOR_DOCUMENT = {
    DocumentType.ATTENDANCE_COMMITMENT: StudentActionType.COMMITMENT_TAKEN,
}


def _membership_name(membership) -> str | None:
    if membership is None:
        return None
    profile = getattr(membership, "staff_profile", None)
    return profile.display_name if profile else membership.user.display_name


def _has_role(request, roles) -> bool:
    return any(role in roles for role in request.school_roles)


def document_row(document: GeneratedDocument, *, can_download: bool) -> dict:
    return {
        "id": document.id,
        "student_id": document.student_id,
        "document_type": document.document_type,
        "document_type_label": TYPE_LABELS.get(document.document_type, document.document_type),
        "status": document.status,
        "status_label": STATUS_LABELS.get(document.status, document.status),
        "template": f"{document.template_key}:{document.template_version}",
        "warning_id": document.warning_id,
        "action_id": document.action_id,
        "generated_at": document.generated_at.isoformat() if document.generated_at else None,
        "generated_by_name": _membership_name(document.generated_by_membership),
        "size_bytes": document.size_bytes,
        "checksum": document.checksum,
        "error_code": document.error_code,
        # التنزيل ممكن فقط لمستند جاهز ودور مصرح — الواجهة تخفي الزر تبعًا لذلك
        "can_download": can_download and document.status == DocumentStatus.READY,
    }


def _base_queryset(school):
    return (
        GeneratedDocument.objects.filter(school=school)
        .select_related(
            "generated_by_membership__staff_profile",
            "generated_by_membership__user",
        )
        .order_by("-created_at", "-id")
    )


def _student_or_404(request, student_id: int) -> Student:
    student = Student.objects.filter(school=request.school, id=student_id).first()
    if student is None:
        raise ApiError("NOT_FOUND", "المورد المطلوب غير موجود.", status_code=404)
    return student


def _range_from(data, school, document_type):
    from_date, to_date = data.get("from_date"), data.get("to_date")
    if document_type in RANGE_DOCUMENT_TYPES and (from_date is None or to_date is None):
        return snapshot_service.default_range(school)
    return from_date, to_date


class DocumentsView(SchoolScopedAPIView):
    read_roles = DOCUMENT_READ_ROLES
    write_roles = DOCUMENT_WRITE_ROLES

    @extend_schema(responses=DocumentSerializer(many=True))
    def get(self, request: Request) -> Response:
        queryset = _base_queryset(request.school)
        student_id = request.query_params.get("student")
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        document_type = request.query_params.get("document_type")
        if document_type:
            queryset = queryset.filter(document_type=document_type)
        warning_id = request.query_params.get("warning")
        if warning_id:
            queryset = queryset.filter(warning_id=warning_id)
        status_filter = request.query_params.get("status")
        if status_filter in DocumentStatus.values:
            queryset = queryset.filter(status=status_filter)

        can_download = _has_role(request, DOWNLOAD_ROLES)
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            [document_row(d, can_download=can_download) for d in page]
        )


class DocumentPreviewView(SchoolScopedAPIView):
    """معاينة البيانات قبل الإصدار (البند 61) — الخادم يبني اللقطة، لا الواجهة."""

    read_roles = DOCUMENT_WRITE_ROLES
    write_roles = DOCUMENT_WRITE_ROLES

    @extend_schema(request=PreviewDocumentSerializer, responses=None)
    def post(self, request: Request) -> Response:
        serializer = PreviewDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        student = _student_or_404(request, data["student_id"])
        document_type = data["document_type"]

        warning = None
        if document_type in WARNING_DOCUMENT_TYPES.values():
            warning = generation_service.resolve_warning(
                school=request.school, student=student, warning_id=data.get("warning_id")
            )
        from_date, to_date = _range_from(data, request.school, document_type)
        snapshot, template = generation_service.build_snapshot(
            school=request.school,
            membership=request.membership,
            student=student,
            document_type=document_type,
            warning=warning,
            from_date=from_date,
            to_date=to_date,
        )
        existing = GeneratedDocument.objects.filter(
            school=request.school,
            student=student,
            document_type=document_type,
            warning=warning,
            status__in=[DocumentStatus.PENDING, DocumentStatus.READY],
        ).exists()
        return Response(
            {
                "document_type": document_type,
                "document_type_label": TYPE_LABELS.get(document_type, document_type),
                "template": template.registry_id,
                "already_exists": existing,
                "snapshot": snapshot,
            }
        )


class DocumentGenerateView(SchoolScopedAPIView):
    read_roles = DOCUMENT_WRITE_ROLES
    write_roles = DOCUMENT_WRITE_ROLES

    @extend_schema(request=GenerateDocumentSerializer, responses=DocumentSerializer)
    def post(self, request: Request) -> Response:
        serializer = GenerateDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        student = _student_or_404(request, data["student_id"])
        document_type = data["document_type"]
        from_date, to_date = _range_from(data, request.school, document_type)

        document = generation_service.generate_document(
            school=request.school,
            membership=request.membership,
            student=student,
            document_type=document_type,
            warning_id=data.get("warning_id"),
            from_date=from_date,
            to_date=to_date,
            request=request,
        )

        # سياسة ثابتة (البند 69): الإجراء ينشأ **بعد** جاهزية المستند لا قبلها
        action_type = ACTION_FOR_DOCUMENT.get(document_type)
        if (
            data.get("create_action")
            and action_type is not None
            and document.status == DocumentStatus.READY
        ):
            action = create_student_action(
                school=request.school,
                membership=request.membership,
                student=student,
                action_type=action_type,
                warning_id=data.get("warning_id"),
                notes=data.get("notes", ""),
                request=request,
            )
            document.action = action
            document.save(update_fields=["action", "updated_at"])

        return Response(
            document_row(document, can_download=_has_role(request, DOWNLOAD_ROLES)),
            status=201 if document.status == DocumentStatus.READY else 202,
        )


class DocumentDetailView(SchoolScopedAPIView):
    read_roles = DOCUMENT_READ_ROLES
    write_roles = DOCUMENT_WRITE_ROLES

    @extend_schema(responses=DocumentSerializer)
    def get(self, request: Request, document_id: int) -> Response:
        document = _base_queryset(request.school).filter(id=document_id).first()
        if document is None:
            raise _NOT_FOUND
        payload = document_row(document, can_download=_has_role(request, DOWNLOAD_ROLES))
        # اللقطة تعرض للمصرح لهم بالإنشاء — المرشد يرى البيانات الوصفية فقط
        if _has_role(request, DOCUMENT_WRITE_ROLES):
            payload["snapshot"] = document.snapshot_data
        return Response(payload)


class DocumentDownloadView(SchoolScopedAPIView):
    read_roles = DOWNLOAD_ROLES
    write_roles = DOWNLOAD_ROLES

    @extend_schema(responses=None)
    def get(self, request: Request, document_id: int) -> Response:
        document = _base_queryset(request.school).filter(id=document_id).first()
        if document is None:
            raise _NOT_FOUND
        handle = generation_service.open_for_download(document)
        record_event(
            AuditAction.DOCUMENT_DOWNLOADED,
            request=request,
            actor=request.user,
            school=request.school,
            target_type="GeneratedDocument",
            target_id=document.id,
            metadata={"document_type": document.document_type},
        )
        label = TYPE_LABELS.get(document.document_type, document.document_type)
        return FileResponse(
            handle,
            as_attachment=True,
            filename=f"{label}-{document.id}.pdf",
            content_type=document.mime_type or "application/pdf",
        )


class DocumentRetryView(SchoolScopedAPIView):
    read_roles = DOCUMENT_WRITE_ROLES
    write_roles = DOCUMENT_WRITE_ROLES

    @extend_schema(request=None, responses=DocumentSerializer)
    def post(self, request: Request, document_id: int) -> Response:
        document = GeneratedDocument.objects.filter(
            school=request.school, id=document_id
        ).first()
        if document is None:
            raise _NOT_FOUND
        document = generation_service.retry_document(
            school=request.school,
            membership=request.membership,
            document=document,
            request=request,
        )
        return Response(document_row(document, can_download=_has_role(request, DOWNLOAD_ROLES)))


class DocumentVoidView(SchoolScopedAPIView):
    read_roles = VOID_ROLES
    write_roles = VOID_ROLES

    @extend_schema(request=VoidDocumentSerializer, responses=DocumentSerializer)
    def post(self, request: Request, document_id: int) -> Response:
        serializer = VoidDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = GeneratedDocument.objects.filter(
            school=request.school, id=document_id
        ).first()
        if document is None:
            raise _NOT_FOUND
        document = generation_service.void_document(
            school=request.school,
            membership=request.membership,
            document=document,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(document_row(document, can_download=False))
