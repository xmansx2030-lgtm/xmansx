"""واجهات الإجراءات الطلابية (م12).

الأدوار (البنود 83-86): المدير والوكيل ينشئان ويلغيان؛ المرشد **قراءة فقط**؛
المعلم محجوب كليًا. لا `school_id` من العميل — `request.school` حصرًا.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from common.errors import ApiError
from common.pagination import DefaultPagination
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from student_actions.api.serializers import (
    ActionSerializer,
    CancelActionSerializer,
    CreateActionSerializer,
)
from student_actions.models import StudentAction, StudentActionStatus, StudentActionType
from student_actions.services import cancel_student_action, create_student_action
from student_warnings.models import WarningLevel, WarningRuleType
from students.models import Student

ACTION_WRITE_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)
ACTION_READ_ROLES = (
    SchoolRole.SCHOOL_MANAGER,
    SchoolRole.VICE_PRINCIPAL,
    SchoolRole.COUNSELOR,
)

TYPE_LABELS = dict(StudentActionType.choices)
STATUS_LABELS = dict(StudentActionStatus.choices)
WARNING_TYPE_LABELS = dict(WarningRuleType.choices)
WARNING_LEVEL_LABELS = dict(WarningLevel.choices)

_NOT_FOUND = ApiError("STUDENT_ACTION_NOT_FOUND", "الإجراء غير موجود.", status_code=404)


def _membership_name(membership) -> str | None:
    if membership is None:
        return None
    profile = getattr(membership, "staff_profile", None)
    return profile.display_name if profile else membership.user.display_name


def _warning_label(warning) -> str | None:
    if warning is None:
        return None
    return (
        f"{WARNING_LEVEL_LABELS.get(warning.level, warning.level)}"
        f" — {WARNING_TYPE_LABELS.get(warning.warning_type, warning.warning_type)}"
    )


def action_row(action: StudentAction) -> dict:
    return {
        "id": action.id,
        "student_id": action.student_id,
        "action_type": action.action_type,
        "action_type_label": TYPE_LABELS.get(action.action_type, action.action_type),
        "status": action.status,
        "status_label": STATUS_LABELS.get(action.status, action.status),
        "warning_id": action.warning_id,
        "warning_label": _warning_label(action.warning),
        "performed_at": action.performed_at.isoformat(),
        "performed_by_name": _membership_name(action.performed_by_membership),
        "notes": action.notes,
        "cancelled_at": action.cancelled_at.isoformat() if action.cancelled_at else None,
        "cancelled_by_name": _membership_name(action.cancelled_by_membership),
        "cancellation_reason": action.cancellation_reason,
    }


def _base_queryset(school):
    return (
        StudentAction.objects.filter(school=school)
        .select_related(
            "warning",
            "performed_by_membership__staff_profile",
            "performed_by_membership__user",
            "cancelled_by_membership__staff_profile",
            "cancelled_by_membership__user",
        )
        .order_by("-performed_at", "-id")
    )


def _student_or_404(request, student_id: int) -> Student:
    student = Student.objects.filter(school=request.school, id=student_id).first()
    if student is None:
        raise ApiError("NOT_FOUND", "المورد المطلوب غير موجود.", status_code=404)
    return student


class StudentActionsView(SchoolScopedAPIView):
    read_roles = ACTION_READ_ROLES
    write_roles = ACTION_WRITE_ROLES

    @extend_schema(responses=ActionSerializer(many=True))
    def get(self, request: Request) -> Response:
        queryset = _base_queryset(request.school)
        student_id = request.query_params.get("student")
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        action_type = request.query_params.get("action_type")
        if action_type:
            queryset = queryset.filter(action_type=action_type)
        status_filter = request.query_params.get("status")
        if status_filter in StudentActionStatus.values:
            queryset = queryset.filter(status=status_filter)
        warning_id = request.query_params.get("warning")
        if warning_id:
            queryset = queryset.filter(warning_id=warning_id)

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([action_row(a) for a in page])

    @extend_schema(request=CreateActionSerializer, responses=ActionSerializer)
    def post(self, request: Request) -> Response:
        serializer = CreateActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        student = _student_or_404(request, data["student_id"])
        action = create_student_action(
            school=request.school,
            membership=request.membership,
            student=student,
            action_type=data["action_type"],
            warning_id=data.get("warning_id"),
            performed_at=data.get("performed_at"),
            notes=data.get("notes", ""),
            request=request,
        )
        return Response(action_row(action), status=201)


class StudentActionDetailView(SchoolScopedAPIView):
    read_roles = ACTION_READ_ROLES
    write_roles = ACTION_WRITE_ROLES

    @extend_schema(responses=ActionSerializer)
    def get(self, request: Request, action_id: int) -> Response:
        action = _base_queryset(request.school).filter(id=action_id).first()
        if action is None:
            raise _NOT_FOUND
        return Response(action_row(action))


class StudentActionCancelView(SchoolScopedAPIView):
    read_roles = ACTION_READ_ROLES
    write_roles = ACTION_WRITE_ROLES

    @extend_schema(request=CancelActionSerializer, responses=ActionSerializer)
    def post(self, request: Request, action_id: int) -> Response:
        serializer = CancelActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = StudentAction.objects.filter(school=request.school, id=action_id).first()
        if action is None:
            raise _NOT_FOUND
        cancelled = cancel_student_action(
            school=request.school,
            membership=request.membership,
            action=action,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(action_row(_base_queryset(request.school).get(id=cancelled.id)))
