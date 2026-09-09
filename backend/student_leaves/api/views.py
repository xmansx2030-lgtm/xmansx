"""واجهات الاستئذان: المدير والوكيل فقط، وعزل كامل حسب المدرسة النشطة."""

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response

from common.pagination import DefaultPagination
from memberships.api_base import SchoolScopedAPIView
from memberships.models import SchoolRole
from student_leaves.api.serializers import (
    CancelStudentLeaveSerializer,
    CreateStudentLeaveSerializer,
    GateStudentLeaveFilterSerializer,
    StudentLeaveFilterSerializer,
)
from student_leaves.models import StudentGateRelease, StudentLeavePermission, StudentLeaveStatus
from student_leaves.services import (
    cancel_student_leave,
    confirm_gate_release,
    record_student_leave,
)
from students.models import Student

LEAVE_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)
GATE_ROLES = (*LEAVE_ROLES, SchoolRole.GATE_GUARD)
WEEKDAY_LABELS = (
    "الاثنين",
    "الثلاثاء",
    "الأربعاء",
    "الخميس",
    "الجمعة",
    "السبت",
    "الأحد",
)


def _membership_name(membership) -> str | None:
    if membership is None:
        return None
    profile = getattr(membership, "staff_profile", None)
    return profile.display_name if profile else membership.user.display_name


def leave_row(leave: StudentLeavePermission) -> dict:
    release = getattr(leave, "gate_release", None)
    return {
        "id": leave.id,
        "student": {
            "id": leave.student_id,
            "full_name": leave.student.full_name,
            "student_number": leave.student.student_number,
            "national_id_masked": leave.student.national_id_masked,
        },
        "leave_date": leave.leave_date.isoformat(),
        "leave_time": leave.leave_time.strftime("%H:%M"),
        "weekday_label": WEEKDAY_LABELS[leave.leave_date.weekday()],
        "reason": leave.reason,
        "recipient_name": leave.recipient_name,
        "recipient_relationship": leave.recipient_relationship,
        "recipient_id_last4": leave.recipient_id_last4,
        "grade_name": leave.grade_name,
        "section_name": leave.section_name,
        "status": leave.status,
        "status_label": StudentLeaveStatus(leave.status).label,
        "recorded_by_name": _membership_name(leave.recorded_by_membership),
        "created_at": leave.created_at.isoformat(),
        "cancelled_by_name": _membership_name(leave.cancelled_by_membership),
        "cancelled_at": leave.cancelled_at.isoformat() if leave.cancelled_at else None,
        "cancellation_reason": leave.cancellation_reason,
        "gate_release": gate_release_row(release) if release else None,
    }


def gate_release_row(release: StudentGateRelease) -> dict:
    return {
        "released_at": release.released_at.isoformat(),
        "released_by_name": _membership_name(release.released_by_membership),
    }


def gate_leave_row(leave: StudentLeavePermission) -> dict:
    """الحد الأدنى اللازم للحارس؛ يتعمد حجب السبب والهوية الوطنية."""

    release = getattr(leave, "gate_release", None)
    return {
        "id": leave.id,
        "student": {
            "id": leave.student_id,
            "full_name": leave.student.full_name,
            "student_number": leave.student.student_number,
        },
        "leave_date": leave.leave_date.isoformat(),
        "leave_time": leave.leave_time.strftime("%H:%M"),
        "grade_name": leave.grade_name,
        "section_name": leave.section_name,
        "recorded_by_name": _membership_name(leave.recorded_by_membership),
        "recipient_name": leave.recipient_name,
        "recipient_relationship": leave.recipient_relationship,
        "recipient_id_last4": leave.recipient_id_last4,
        "gate_release": gate_release_row(release) if release else None,
    }


def _queryset(school):
    return StudentLeavePermission.objects.filter(school=school).select_related(
        "student",
        "recorded_by_membership__staff_profile",
        "recorded_by_membership__user",
        "cancelled_by_membership__staff_profile",
        "cancelled_by_membership__user",
        "gate_release__released_by_membership__staff_profile",
        "gate_release__released_by_membership__user",
    )


class StudentLeaveListView(SchoolScopedAPIView):
    read_roles = LEAVE_ROLES
    write_roles = LEAVE_ROLES

    def get(self, request: Request) -> Response:
        filters = StudentLeaveFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        data = filters.validated_data
        queryset = _queryset(request.school)
        student_id = data.get("student")
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        leave_date = data.get("date")
        if leave_date:
            queryset = queryset.filter(leave_date=leave_date)
        search = data.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(student__full_name__icontains=search)
                | Q(student__student_number__icontains=search)
            )

        counts = queryset.aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(status=StudentLeaveStatus.ACTIVE)),
            cancelled=Count("id", filter=Q(status=StudentLeaveStatus.CANCELLED)),
        )
        status_filter = data.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        response = paginator.get_paginated_response([leave_row(row) for row in page])
        response.data["summary"] = counts
        return response

    def post(self, request: Request) -> Response:
        serializer = CreateStudentLeaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        student = get_object_or_404(
            Student,
            id=data["student_id"],
            school=request.school,
        )
        leave = record_student_leave(
            school=request.school,
            membership=request.membership,
            student=student,
            leave_date=data["leave_date"],
            leave_time=data["leave_time"],
            reason=data["reason"],
            recipient_name=data["recipient_name"],
            recipient_relationship=data["recipient_relationship"],
            recipient_id_last4=data["recipient_id_last4"],
            request=request,
        )
        return Response(leave_row(_queryset(request.school).get(id=leave.id)), status=201)


class StudentLeaveCancelView(SchoolScopedAPIView):
    read_roles = LEAVE_ROLES
    write_roles = LEAVE_ROLES
    http_method_names = ["post", "options"]

    def post(self, request: Request, leave_id: int) -> Response:
        serializer = CancelStudentLeaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        leave = get_object_or_404(StudentLeavePermission, id=leave_id, school=request.school)
        cancelled = cancel_student_leave(
            school=request.school,
            membership=request.membership,
            leave=leave,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(leave_row(_queryset(request.school).get(id=cancelled.id)))


class GateStudentLeaveListView(SchoolScopedAPIView):
    read_roles = GATE_ROLES
    write_roles = GATE_ROLES
    http_method_names = ["get", "options"]

    def get(self, request: Request) -> Response:
        filters = GateStudentLeaveFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        queryset = _queryset(request.school).filter(
            leave_date=timezone.localdate(),
            status=StudentLeaveStatus.ACTIVE,
        )
        search = filters.validated_data.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(student__full_name__icontains=search)
                | Q(student__student_number__icontains=search)
            )
        rows = list(queryset.order_by("leave_time", "id"))
        pending = sum(1 for row in rows if getattr(row, "gate_release", None) is None)
        return Response(
            {
                "date": timezone.localdate().isoformat(),
                "summary": {
                    "total": len(rows),
                    "pending": pending,
                    "released": len(rows) - pending,
                },
                "results": [gate_leave_row(row) for row in rows],
            }
        )


class GateStudentLeaveReleaseView(SchoolScopedAPIView):
    read_roles = GATE_ROLES
    write_roles = GATE_ROLES
    http_method_names = ["post", "options"]

    def post(self, request: Request, leave_id: int) -> Response:
        leave = get_object_or_404(StudentLeavePermission, id=leave_id, school=request.school)
        confirm_gate_release(
            school=request.school,
            membership=request.membership,
            leave=leave,
            request=request,
        )
        return Response(
            gate_leave_row(_queryset(request.school).get(id=leave_id)),
            status=201,
        )
