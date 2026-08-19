"""‏API الأعذار — كل شيء عبر request.school (لا school_id من العميل — بند 95).

الأدوار: المدير/الوكيل إدارة كاملة؛ المرشد قراءة metadata فقط (تنزيل المرفقات
مرفوض — بند 99)؛ المعلم لا وصول إطلاقًا.
"""

from datetime import date

from django.db.models import Count, Max, Min, Q
from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from attendance.services.periods import school_now
from common.errors import ApiError
from common.pagination import DefaultPagination
from excuses.api.serializers import (
    ApproveSerializer,
    DecisionReasonSerializer,
    ExcuseCreateSerializer,
    ExcusePatchSerializer,
    serialize_attachment,
    serialize_excuse_detail,
    serialize_excuse_row,
)
from excuses.models import (
    AbsenceExcuse,
    AbsenceExcuseAttachment,
    AbsenceExcuseStatus,
    ExcuseCoverageStatus,
)
from excuses.services import coverage as coverage_service
from excuses.services import excuses as excuse_service
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from students.models import Student

EXCUSE_MANAGE_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)
EXCUSE_READ_ROLES = (
    SchoolRole.SCHOOL_MANAGER,
    SchoolRole.VICE_PRINCIPAL,
    SchoolRole.COUNSELOR,
)

_NOT_FOUND = ApiError("EXCUSE_NOT_FOUND", "العذر غير موجود.", status_code=404)


def _get_excuse(school, excuse_id: int, *, for_detail: bool = False) -> AbsenceExcuse:
    queryset = AbsenceExcuse.objects.filter(school=school)
    if for_detail:
        queryset = queryset.select_related(
            "student",
            "recorded_by_membership__staff_profile",
            "recorded_by_membership__user",
            "approved_by_membership__staff_profile",
            "approved_by_membership__user",
            "rejected_by_membership__staff_profile",
            "rejected_by_membership__user",
            "cancelled_by_membership__staff_profile",
            "cancelled_by_membership__user",
        ).prefetch_related(
            "targets",
            "coverages",
            "attachments__uploaded_by_membership__staff_profile",
            "attachments__uploaded_by_membership__user",
            "student__enrollments__grade",
            "student__enrollments__section",
        )
    excuse = queryset.filter(id=excuse_id).first()
    if excuse is None:
        raise _NOT_FOUND
    return excuse


class ExcuseListCreateView(SchoolScopedAPIView):
    read_roles = EXCUSE_READ_ROLES
    write_roles = EXCUSE_MANAGE_ROLES

    @extend_schema(responses=None)
    def get(self, request):
        queryset = (
            AbsenceExcuse.objects.filter(school=request.school)
            .select_related(
                "student",
                "recorded_by_membership__staff_profile",
                "recorded_by_membership__user",
                "approved_by_membership__staff_profile",
                "approved_by_membership__user",
            )
            .prefetch_related(
                "student__enrollments__grade", "student__enrollments__section"
            )
            .annotate(
                targets_count=Count("targets", distinct=True),
                active_coverage_count=Count(
                    "coverages",
                    filter=Q(coverages__status=ExcuseCoverageStatus.ACTIVE),
                    distinct=True,
                ),
                attachments_count=Count("attachments", distinct=True),
                date_from=Min("targets__attendance_date"),
                date_to=Max("targets__attendance_date"),
            )
            .order_by("-recorded_at", "-id")
        )
        params = request.query_params
        if params.get("status") in AbsenceExcuseStatus.values:
            queryset = queryset.filter(status=params["status"])
        if params.get("reason_type"):
            queryset = queryset.filter(reason_type=params["reason_type"])
        if params.get("student"):
            queryset = queryset.filter(student_id=_int_or_none(params["student"]) or 0)
        if params.get("grade"):
            queryset = queryset.filter(
                student__enrollments__status="ACTIVE",
                student__enrollments__grade_id=_int_or_none(params["grade"]) or 0,
            ).distinct()
        if params.get("section"):
            queryset = queryset.filter(
                student__enrollments__status="ACTIVE",
                student__enrollments__section_id=_int_or_none(params["section"]) or 0,
            ).distinct()
        from_date = _date_or_error(params.get("from_date"), "from_date")
        if from_date is not None:
            queryset = queryset.filter(targets__attendance_date__gte=from_date).distinct()
        to_date = _date_or_error(params.get("to_date"), "to_date")
        if to_date is not None:
            queryset = queryset.filter(targets__attendance_date__lte=to_date).distinct()

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(
            [serialize_excuse_row(excuse) for excuse in page]
        )

    @extend_schema(request=ExcuseCreateSerializer, responses=None)
    def post(self, request):
        serializer = ExcuseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        student = Student.objects.filter(
            school=request.school, id=data["student_id"]
        ).first()
        if student is None:
            raise ApiError("NOT_FOUND", "الطالب غير موجود.", status_code=404)
        excuse = excuse_service.create_excuse(
            school=request.school,
            membership=request.membership,
            student=student,
            reason_type=data["reason_type"],
            notes=data["notes"],
            targets=data["targets"],
            request=request,
        )
        return Response(
            serialize_excuse_detail(_get_excuse(request.school, excuse.id, for_detail=True)),
            status=201,
        )


class ExcuseKpisView(SchoolScopedAPIView):
    read_roles = EXCUSE_READ_ROLES
    write_roles = EXCUSE_MANAGE_ROLES

    @extend_schema(responses=None)
    def get(self, request):
        base = AbsenceExcuse.objects.filter(school=request.school)
        now_local = school_now(request.school)
        start_of_day = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        return Response(
            {
                "pending_count": base.filter(
                    status=AbsenceExcuseStatus.PENDING
                ).count(),
                "approved_today_count": base.filter(
                    status=AbsenceExcuseStatus.APPROVED,
                    approved_at__gte=start_of_day,
                ).count(),
                "rejected_count": base.filter(
                    status=AbsenceExcuseStatus.REJECTED
                ).count(),
                "cancelled_count": base.filter(
                    status=AbsenceExcuseStatus.CANCELLED
                ).count(),
            }
        )


class ExcuseDetailView(SchoolScopedAPIView):
    read_roles = EXCUSE_READ_ROLES
    write_roles = EXCUSE_MANAGE_ROLES

    @extend_schema(responses=None)
    def get(self, request, excuse_id: int):
        excuse = _get_excuse(request.school, excuse_id, for_detail=True)
        return Response(serialize_excuse_detail(excuse))

    @extend_schema(request=ExcusePatchSerializer, responses=None)
    def patch(self, request, excuse_id: int):
        _get_excuse(request.school, excuse_id)
        serializer = ExcusePatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        excuse_service.update_excuse(
            excuse_id=excuse_id,
            school=request.school,
            membership=request.membership,
            reason_type=data.get("reason_type"),
            notes=data.get("notes"),
            targets=data.get("targets"),
            request=request,
        )
        return Response(
            serialize_excuse_detail(_get_excuse(request.school, excuse_id, for_detail=True))
        )


class ExcusePreviewView(SchoolScopedAPIView):
    read_roles = EXCUSE_MANAGE_ROLES
    write_roles = EXCUSE_MANAGE_ROLES

    @extend_schema(request=None, responses=None)
    def post(self, request, excuse_id: int):
        excuse = _get_excuse(request.school, excuse_id, for_detail=True)
        if excuse.status != AbsenceExcuseStatus.PENDING:
            raise ApiError(
                "VALIDATION_ERROR",
                "المعاينة متاحة للأعذار بانتظار الاعتماد فقط.",
                status_code=409,
            )
        plan = coverage_service.resolve_coverage_plan(excuse)
        return Response(
            {
                "excuse_id": excuse.id,
                "days": plan["days"],
                "covered_absent_periods": len(plan["covered"]),
                "already_excused_periods": len(plan["already_excused"]),
                "already_excused_dates": sorted(
                    {
                        m.session.attendance_date.isoformat()
                        for m in plan["already_excused"]
                    }
                ),
                "preview_hash": plan["preview_hash"],
            }
        )


class ExcuseApproveView(SchoolScopedAPIView):
    read_roles = EXCUSE_MANAGE_ROLES
    write_roles = EXCUSE_MANAGE_ROLES

    @extend_schema(request=ApproveSerializer, responses=None)
    def post(self, request, excuse_id: int):
        _get_excuse(request.school, excuse_id)
        serializer = ApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        coverage_service.approve_excuse(
            excuse_id=excuse_id,
            school=request.school,
            membership=request.membership,
            preview_hash=serializer.validated_data["preview_hash"],
            request=request,
        )
        return Response(
            serialize_excuse_detail(_get_excuse(request.school, excuse_id, for_detail=True))
        )


class ExcuseRejectView(SchoolScopedAPIView):
    read_roles = EXCUSE_MANAGE_ROLES
    write_roles = EXCUSE_MANAGE_ROLES

    @extend_schema(request=DecisionReasonSerializer, responses=None)
    def post(self, request, excuse_id: int):
        _get_excuse(request.school, excuse_id)
        serializer = DecisionReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        excuse_service.reject_excuse(
            excuse_id=excuse_id,
            school=request.school,
            membership=request.membership,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(
            serialize_excuse_detail(_get_excuse(request.school, excuse_id, for_detail=True))
        )


class ExcuseCancelView(SchoolScopedAPIView):
    read_roles = EXCUSE_MANAGE_ROLES
    write_roles = EXCUSE_MANAGE_ROLES

    @extend_schema(request=DecisionReasonSerializer, responses=None)
    def post(self, request, excuse_id: int):
        _get_excuse(request.school, excuse_id)
        serializer = DecisionReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        coverage_service.cancel_excuse(
            excuse_id=excuse_id,
            school=request.school,
            membership=request.membership,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(
            serialize_excuse_detail(_get_excuse(request.school, excuse_id, for_detail=True))
        )


class ExcuseAttachmentsView(SchoolScopedAPIView):
    read_roles = EXCUSE_MANAGE_ROLES
    write_roles = EXCUSE_MANAGE_ROLES

    @extend_schema(request=None, responses=None)
    def post(self, request, excuse_id: int):
        excuse = _get_excuse(request.school, excuse_id)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ApiError("VALIDATION_ERROR", "يجب إرفاق ملف.")
        attachment = excuse_service.add_attachment(
            excuse=excuse,
            school=request.school,
            membership=request.membership,
            uploaded_file=uploaded,
            request=request,
        )
        return Response(serialize_attachment(attachment), status=201)


class ExcuseAttachmentDetailView(SchoolScopedAPIView):
    # التنزيل للمدير/الوكيل فقط — المرشد يرى metadata العذر دون فتح المرفق (بند 99)
    read_roles = EXCUSE_MANAGE_ROLES
    write_roles = EXCUSE_MANAGE_ROLES

    def _get_attachment(self, request, excuse_id, attachment_id):
        attachment = (
            AbsenceExcuseAttachment.objects.filter(
                school=request.school, excuse_id=excuse_id, id=attachment_id
            )
            .select_related("excuse")
            .first()
        )
        if attachment is None:
            raise _NOT_FOUND
        return attachment

    @extend_schema(responses=None)
    def get(self, request, excuse_id: int, attachment_id: int):
        attachment = self._get_attachment(request, excuse_id, attachment_id)
        return FileResponse(
            attachment.file.open("rb"),
            as_attachment=True,
            filename=attachment.original_filename,
            content_type=attachment.mime_type,
        )

    @extend_schema(responses=None)
    def delete(self, request, excuse_id: int, attachment_id: int):
        attachment = self._get_attachment(request, excuse_id, attachment_id)
        excuse_service.remove_attachment(
            attachment=attachment,
            school=request.school,
            membership=request.membership,
            request=request,
        )
        return Response(status=204)


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _date_or_error(value, field: str) -> date | None:
    """تاريخ غير صالح يرد 400 عربيًا — تمريره للـORM كان يرفع 500."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ApiError(
            "VALIDATION_ERROR",
            "صيغة التاريخ غير صحيحة (YYYY-MM-DD).",
            details={"field": field},
        ) from None
